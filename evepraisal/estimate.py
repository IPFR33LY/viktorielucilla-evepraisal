import time
import urllib2
import uuid
import xml.etree.ElementTree as ET

import evepaste

from helpers import createsession
from models import *
from parser import parse
from . import app, cache, session, g


def memcache_type_key(typeId, options=None):
    if options is None:
        options = {}
    return "prices:%s:%s" % (options.get('solarsystem_id', '-1'), typeId)


def get_cached_values(eve_types, options=None):
    "Get Cached values given the eve_types"
    found = {}
    for eve_type in eve_types:
        key = memcache_type_key(eve_type, options=options)
        obj = cache.get(key)
        if obj:
            found[eve_type] = obj
    return found


def get_market_values(eve_types, options=None):
    """
        Takes list of typeIds. Returns dict of pricing details with typeId as
        the key. Calls out to the eve-central.

        Example Return Value:
        {
            21574:{
             'all': {
                'avg': 254.83,
                'min': 254.83,
                'max': 254.83,
                'price': 254.83
             },
             'buy': {
                'avg': 5434414.43,
                'min': 5434414.43,
                'max': 5434414.43,
                'price': 5434414.43
             },
             'sell': {
                'avg': 10552957.04,
                'min': 10552957.04,
                'max': 10552957.04,
                'price': 10552957.04
             }
        }
    """
    if len(eve_types) == 0:
        return {}

    if options is None:
        options = {}

    market_prices = {}
    solarsystem_id = options.get('solarsystem_id', -1)
    for types in [eve_types[i:i + 100] for i in range(0, len(eve_types), 100)]:
        query = []
        query += ['typeid=%s' % str(type_id) for type_id in types]
        all_price_metric = 'percentile'
        if solarsystem_id == '-1':
            buy_price_metric = 'percentile'
            sell_price_metric = 'percentile'
        else:
            buy_price_metric = 'max'
            sell_price_metric = 'min'
            query += ['usesystem=%s' % solarsystem_id]
        query_str = '&'.join(query)
        url = "http://api.eve-central.com/api/marketstat?%s" % query_str
        app.logger.debug("API Call: %s", url)
        try:
            request = urllib2.Request(url)
            request.add_header('User-Agent', app.config['USER_AGENT'])
            response = urllib2.build_opener().open(request).read()
            stats = ET.fromstring(response).findall("./marketstat/type")

            for marketstat in stats:
                k = int(marketstat.attrib.get('id'))
                v = {}
                for stat_type in ['sell', 'buy', 'all']:
                    props = {}
                    for stat in marketstat.find(stat_type):
                        if not stat.tag == "generated":
                            props[stat.tag] = float(stat.text)
                    v[stat_type] = props
                v['all']['price'] = v['all'][all_price_metric]
                v['buy']['price'] = v['buy'][buy_price_metric]
                v['sell']['price'] = v['sell'][sell_price_metric]
                v['source'] = 'evecentral'
                market_prices[k] = v

        except urllib2.HTTPError:
            pass
    #: Debugging Market_Prices
    #:
    #: f = open('C:\open.txt', 'w')
    #: f.write(str(market_prices))
    #: f.close()
    return market_prices


def get_market_values_evemarketdata(eve_types, options=None):
    """
        Takes list of typeIds. Returns dict of pricing details with typeId as
        the key. Calls out to the eve-marketdata.
        Example Return Value:
        {
            21574:{
             'all': {
                'avg': 254.83,
                'min': 254.83,
                'max': 254.83,
                'price': 254.83
             },
             'buy': {
                'avg': 5434414.43,
                'min': 5434414.43,
                'max': 5434414.43,
                'price': 5434414.43
             },
             'sell': {
                'avg': 10552957.04,
                'min': 10552957.04,
                'max': 10552957.04,
                'price': 10552957.04
             }
        }
    """
    if len(eve_types) == 0:
        return {}

    if options is None:
        options = {}

    market_prices = {}
    solarsystem_id = options.get('solarsystem_id', '-1')
    for types in [eve_types[i:i + 200] for i in range(0, len(eve_types), 200)]:
        typeIds_str = 'type_ids=%s' % ','.join(str(type_id) for type_id in types)
        query = [typeIds_str]

        if solarsystem_id != '-1':
            query += ['usesystem=%s' % solarsystem_id]

            solarsystem_ids_str = ','.join(
                [str(options.get('solarsystem_id', 30000142))])
            query += ['solarsystem_ids=%s' % solarsystem_ids_str]
        query_str = '&'.join(query)

        url = "http://api.eve-marketdata.com/api/item_prices2.json?" \
              "char_name=magerawr&buysell=a&%s" % (query_str)
        app.logger.debug("API Call: %s", url)
        try:
            request = urllib2.Request(url)
            request.add_header('User-Agent', app.config['USER_AGENT'])
            response = json.loads(urllib2.build_opener().open(request).read())

            for row in response['emd']['result']:
                row = row['row']
                k = int(row['typeID'])
                if k not in market_prices:
                    market_prices[k] = {}
                if row['buysell'] == 's':
                    price = float(row['price'])
                    market_prices[k]['sell'] = {'avg': price,
                                                'min': price,
                                                'max': price}
                elif row['buysell'] == 'b':
                    price = float(row['price'])
                    market_prices[k]['buy'] = {'avg': price,
                                               'min': price,
                                               'max': price}

            for typeId, prices in market_prices.iteritems():
                avg = (prices['sell']['avg'] + prices['buy']['avg']) / 2
                market_prices[typeId]['all'] = {'avg': avg,
                                                'min': avg,
                                                'max': avg,
                                                'price': avg}
                market_prices[typeId]['buy']['price'] = \
                    market_prices[typeId]['buy']['max']
                market_prices[typeId]['sell']['price'] = \
                    market_prices[typeId]['sell']['min']
                market_prices[typeId]['source'] = 'evemarketdata'

        except urllib2.HTTPError:
            pass
        except ValueError:
            pass
    return market_prices


def price_volume_statistics(pricevolumedict):
    """ Calculates pricing statistics given a list of dicts
        containing { "price": price, "volume": volume }
    """
    pricevolumedict = sorted(pricevolumedict, key=lambda k: k['price'])
    if len(pricevolumedict) == 0:
        return {'avg': 0, 'max': 0, 'min': 0, 'bottom5pct': 0, 'top5pct': 0, 'volume': 0}

    maxprice = pricevolumedict[0]['price']
    minprice = pricevolumedict[0]['price']
    totalvolume = 0
    totalprice = 0

    for item in pricevolumedict:
        totalvolume += item['volume']
        totalprice += (item['price'] * item['volume'])
        minprice = min(minprice, item['price'])
        maxprice = max(maxprice, item['price'])

    fivepctvolume = totalvolume * 0.05
    currentvolume = 0.00
    top5pct = 0.00
    bottom5pct = 0.00
    volumetouse = 0.00

    for item in pricevolumedict:
        if currentvolume < fivepctvolume:
            if (currentvolume + item['volume']) <= fivepctvolume:
                volumetouse = item['volume']
            else:
                volumetouse = fivepctvolume - currentvolume
            bottom5pct += (item['price'] * volumetouse)

        if (currentvolume + item['volume']) > (totalvolume - fivepctvolume):
            if currentvolume > (totalvolume - fivepctvolume):
                volumetouse = item['volume']
            else:
                volumetouse = ((currentvolume + item['volume']) - (totalvolume - fivepctvolume))
            top5pct += (item['price'] * volumetouse)

        currentvolume = currentvolume + item['volume']

    avg = totalprice / totalvolume
    bottom5pct = bottom5pct / fivepctvolume
    top5pct = top5pct / fivepctvolume

    return {
        "avg": avg,
        "max": maxprice,
        "min": minprice,
        "bottom5pct": bottom5pct,
        "top5pct": top5pct,
        "volume": totalvolume
    }


def get_market_values_crest(eve_types, options=None):
    """ Takes list of typeIds. Returns dict of pricing details with typeId as
        the key. Calls out to EVE CREST.

        This will do an entire region, and will default to The Forge(JITA) if
        the region is not specified in the dictionary below.
    """
    if len(eve_types) == 0:
        return {}

    if options is None:
        options = {}

    market_prices = {}

    regions = {
        "30000142": "10000002",  # JITA
        "30002187": "10000043",  # AMARR
        "30002659": "10000032",  # DODIXIE
        "30002510": "10000030",  # RENS
        "30002053": "10000042",  # HEK
    }

    solarsystem_id = options.get('solarsystem_id', '-1')

    if solarsystem_id not in regions:
        solarsystem_id = "30000142"

    region = regions[solarsystem_id]

    for types in [eve_types[i:i + 200] for i in range(0, len(eve_types), 200)]:
        for type_id in types:
            url = "https://crest-tq.eveonline.com/market/%s/orders/?type=https://crest-tq.eveonline.com/inventory/types/%s/" % (
                region, type_id)
            app.logger.debug("API Call: %s", url)
            try:
                request = urllib2.Request(url)
                request.add_header('User-Agent', app.config['USER_AGENT'])
                response = json.loads(urllib2.build_opener().open(request).read())
                buy = []
                sell = []
                all = []

                i = 0
                for item in response["items"]:
                    i = i + 1
                    if item["buy"]:
                        buy.append({"i": i, "volume": item["volume"], "price": item["price"]})
                    else:
                        sell.append({"i": i, "volume": item["volume"], "price": item["price"]})

                    all.append({"i": i, "volume": item["volume"], "price": item["price"]})

                output_all = price_volume_statistics(all)
                output_buy = price_volume_statistics(buy)
                output_sell = price_volume_statistics(sell)

                output = {
                    "all": {"avg": output_all['avg'], "max": output_all['max'], "min": output_all['min'],
                            "volume": output_all['volume']},
                    "buy": {"avg": output_buy['avg'], "max": output_buy['max'], "min": output_buy['min'],
                            "volume": output_buy['volume']},
                    "sell": {"avg": output_sell['avg'], "max": output_sell['max'], "min": output_sell['min'],
                             "volume": output_sell['volume']},
                    "source": "crest"
                }

                output["all"]["price"] = output_all['avg']
                output["buy"]["price"] = output_buy['top5pct']
                output["sell"]["price"] = output_sell['bottom5pct']

                market_prices[type_id] = output

            except urllib2.HTTPError:
                pass
    #: Debugging market_prices
    #: f = open('C:\open.txt', 'w')
    #: f.write(str(market_prices))
    #: f.close()
    return market_prices


def get_invalid_values(eve_types, options=None):
    invalid_items = {}
    for eve_type in eve_types:
        type_details = get_type_by_id(eve_type)
        if type_details and type_details.get('market') is False:
            zeroed_price = {'avg': 0, 'min': 0, 'max': 0, 'price': 0}
            price_info = {
                'buy': zeroed_price.copy(),
                'sell': zeroed_price.copy(),
                'all': zeroed_price.copy(),
            }
            invalid_items[eve_type] = price_info
    return invalid_items


def get_componentized_values(eve_types, options=None):
    componentized_items = {}
    for eve_type in eve_types:
        type_details = get_type_by_id(eve_type)
        if type_details and 'components' in type_details:
            component_types = dict((c['materialTypeID'], c['quantity'])
                                   for c in type_details['components'])

            component_prices = get_market_prices(component_types.keys(),
                                                 options=options)
            price_map = dict(component_prices)
            zeroed_price = {'avg': 0, 'min': 0, 'max': 0, 'price': 0}
            complete_price_data = {
                'buy': zeroed_price.copy(),
                'sell': zeroed_price.copy(),
                'all': zeroed_price.copy(),
            }
            for component, quantity in component_types.items():
                for market_type in ['buy', 'sell', 'all']:
                    for stat in ['avg', 'min', 'max', 'price']:
                        _price = price_map.get(component)
                        if _price:
                            complete_price_data[market_type][stat] += (
                                _price[market_type][stat] * quantity)
            componentized_items[eve_type] = complete_price_data

    return componentized_items


def get_market_prices(modules, options=None):
    unpriced_modules = modules[:]
    nmv = {}
    prices = {}
    for pricing_method in [get_invalid_values,
                           get_cached_values,
                           get_componentized_values,
                           get_market_values_crest,
                           get_market_values,
                           get_market_values_evemarketdata
                           ]:
        if len(modules) == len(prices):
            break
        # each pricing_method returns a dict with {type_id: pricing_info}
        _prices = pricing_method(unpriced_modules, options=options)
        app.logger.debug("Found %s/%s items using method: %s",
                         len(_prices), len(modules), pricing_method)
        for type_id, pricing_info in _prices.items():
            if type_id in unpriced_modules:
                # We only care if there is a non-zero price. If the price is 0, keep going.
                if pricing_info['buy']['price'] > 0 or pricing_info['sell']['price'] > 0 or pricing_info['all'][
                    'price'] > 0:
                    if pricing_method not in [get_invalid_values, get_cached_values]:
                        # And only cache things which come from an actual provider.
                        cache.set(memcache_type_key(type_id, options=options), pricing_info, timeout=10 * 60 * 60)
                    prices[type_id] = pricing_info
                    unpriced_modules.remove(type_id)
                    if type_id in nmv:
                        del nmv[type_id]
                elif pricing_info['buy']['price'] == 0 and type_id not in nmv:
                    # If we get a match with no volume, we hold on to it to see if we find one that does.
                    # If we won't, we'll use this info.
                    nmv[type_id] = pricing_info
            else:
                app.logger.debug("[Method: %s] A price was returned which "
                                 "wasn't asked for", pricing_method)

    # If we don't find a price, but, we got a hit with 0 volume, use that instead since
    # no volume shows differently in the UI from not found at all.
    for type_id in nmv:
        if type_id not in prices:
            prices[type_id] = nmv[type_id]

    return prices.items()


def create_appraisal(raw_paste, solar_system):
    if solar_system not in app.config['VALID_SOLAR_SYSTEMS'].keys():
        abort(400)

    try:
        parse_results = parse(raw_paste)
    except evepaste.Unparsable as ex:
        if raw_paste:
            app.logger.warning("User input invalid data: %s", raw_paste)
        return str(ex)

    # Populate types with pricing data
    prices = get_market_prices(list(parse_results['unique_items']), options={'solarsystem_id': solar_system})

    # create a session if we need one
    createsession()

    appraisal = Appraisals(Created=int(time.time()),
                           rID=uuid.uuid4().hex,
                           RawInput=raw_paste,
                           Kind=parse_results['representative_kind'],
                           Prices=prices,
                           Parsed=parse_results['results'],
                           ParsedVersion=1,
                           BadLines=parse_results['bad_lines'],
                           Market=solar_system,
                           Public=bool(session['options'].get('share')),
                           UserId=g.user.Id if g.user else None,
                           SessionId=None if g.user else session['epsessionid'])
    db.session.add(appraisal)
    db.session.commit()

    app.logger.debug("New Appraisal [%s]: %s",
                     appraisal.Id,
                     parse_results['representative_kind'])

    return appraisal
