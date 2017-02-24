""" This module contains methods primarily called through the API
"""
import csv
import io

from flask import jsonify, url_for, redirect, request
from sqlalchemy import desc

from evepraisal.estimate import create_appraisal
from evepraisal.filters import get_market_name
from evepraisal.helpers import login_required_if_config
from evepraisal.models import Appraisals
from . import cache, g, session


def estimate_create(version):
    """ Creates an estimate for the selected version of the estimator.
    """
    redirect_versions = {
        1: {"json": "estimate_v1"},
        2: {"json": "estimate_v2", "csv": "estimate_csv_v2"}
    }

    return_format = request.form.get('format', 'json').lower()
    no_redirect = request.form.get('redirect', 'yes').lower()

    if version not in redirect_versions:
        version = max(redirect_versions.keys(), key=int)

    if return_format not in redirect_versions[version]:
        return_format = "json"

    redirect_string = redirect_versions[version][return_format]

    raw_paste = request.form.get('raw_paste', '')
    solar_system = request.form.get('market', '30000142')

    appraisal = create_appraisal(raw_paste, solar_system)

    if no_redirect == "no":
        if return_format == "csv":
            return estimate_csv(appraisal.Id, version)
        if return_format == "json":
            return estimate_json(appraisal.Id, version)

    return redirect(url_for(redirect_string, result_id=appraisal.Id), code=302)


def estimate_history(version, request_format='json'):
    """Provides a list of historical estimates for the current user.
    """
    appraisals_query = Appraisals.query

    if g.user:
        appraisals_query = appraisals_query.filter(Appraisals.UserId == g.user.Id)
    elif 'epsessionid' in session:
        appraisals_query = appraisals_query.filter(Appraisals.SessionId == session['epsessionid'])
    else:
        appraisals_query = appraisals_query.filter(1 == 2)

    json_url = 'estimate_v1' if version == 1 else 'estimate_v2'
    appraisals_query = appraisals_query.order_by(desc(Appraisals.Created))
    appraisals_query = appraisals_query.limit(100)
    appraisals = appraisals_query.all()

    output = []
    for appraisal in appraisals:
        value = {
            'id': appraisal.Id,
            'kind': appraisal.Kind,
            'created': appraisal.Created,
            'jsonurl': url_for(json_url, result_id=appraisal.Id, _external=True),
            'url': url_for('display_result', result_id=appraisal.Id, _external=True),
            'market_id': appraisal.Market,
            'market_name': get_market_name(appraisal.Market),
            'totals': appraisal.totals()
        }

        if version < 2:
            value['items'] = list(appraisal.iter_types())
            request_format = 'json'

        if version > 1 and request_format == 'csv':
            del value['jsonurl']
            value['csvurl'] = url_for(
                'estimate_csv_v2', result_id=appraisal.Id, _external=True
            )
            value['buy'] = value['totals']['buy']
            value['sell'] = value['totals']['sell']
            value['volume'] = value['totals']['volume']
            value['repackaged'] = value['totals']['repackaged']
            del value['totals']


        output.append(value)

    return output


def estimate_retrieve(result_id):
    """Returns Appraisals data.
    On success, returns an Appraisals object and status code 200.
    On error, returns a string and a non-200 status code.
    """
    cache_key = "api:appraisal:%s" % result_id
    result = cache.get(cache_key)

    if not result:
        appraisals_query = Appraisals.query.filter(Appraisals.Id == result_id)
        appraisal = appraisals_query.first()
        if appraisal:
            cache.set(cache_key, appraisal, timeout=30)
            result = appraisal

    if result:
        if not result.Public:
            if not g.user or not g.user.Id == result.UserId:
                return "Forbidden", 403
        return result, 200

    return "Not Found", 404


def dict_to_csv_string(list_dicts, field_names=None):
    """Takes in a list of dicts, returns a csv-formatted string.
    """

    string_io = io.BytesIO()
    if field_names is None:
        field_names = list_dicts[0].keys()

    csv_writer = csv.DictWriter(string_io, field_names, list_dicts)
    csv_writer.writeheader()
    for indv_dict in list_dicts:
        row = {}
        for key in indv_dict:
            row[key] = indv_dict[key]

        csv_writer.writerow(row)

    return string_io.getvalue().strip('\r\n')


def estimate_csv(result_id, version):
    """ Retrieves an estimate and returns the item rows as a CSV formatted string.
    Returns a message (string), and an HTTP status code (int)
    """
    cache_key = "api:appraisal:csv:%s:%s" % (version, result_id)

    # This object should be a dict in the following format:
    # { data: { csv (string) formatted item data }, private: { user.Id } }
    #
    # private is populated if the appraisal is set to private with the owning user.Id
    result = cache.get(cache_key)
    if result:
        if "private" in result:
            if not g.user or not g.user.Id == result["private"]:
                return "Forbidden", 403
        return result["data"], 200, {'Content-Type': 'text/plain'}

    message, status = estimate_retrieve(result_id)

    if not status == 200:
        return message, status

    if isinstance(message, Appraisals):
        appraisals_items = message.iter_types()

        string_io = io.BytesIO()
        field_names = [
            'id', 'kind', 'created', 'market_id', 'market_name',
            'item_typeID', 'item_name', 'item_quantity', 'item_all', 'item_buy', 'item_sell',
            'item_volume', 'item_repackaged_volume'
        ]

        csv_writer = csv.DictWriter(string_io, field_names, message)
        csv_writer.writeheader()
        for item in appraisals_items:
            row = {
                'id': message.Id,
                'kind': message.Kind,
                'created': message.Created,
                'market_id': message.Market,
                'market_name': get_market_name(message.Market),
                'item_typeID': item["typeID"],
                'item_name': item["name"],
                'item_quantity': item["quantity"],
                'item_all': item["prices"]["all"]["price"],
                'item_buy': item["prices"]["buy"]["price"],
                'item_sell': item["prices"]["sell"]["price"],
                'item_volume': item["volume"]
            }

            rpkg = item["volume"]
            if "repackaged_volume" in item:
                rpkg = item["repackaged_volume"]

            row["item_repackaged_volume"] = rpkg

            csv_writer.writerow(row)
        output = {"data": string_io.getvalue().strip('\r\n')}
        if not message.Public:
            output["private"] = message.UserId

        cache.set(cache_key, output, timeout=30)
        return output["data"], 200, {'Content-Type': 'text/plain'}

    return "No Appraisal Found", 500


def estimate_json(result_id, version):
    """ Retrieves an estimate and returns the item rows as a json formatted string.
    Returns a message (string), and an HTTP status code (int)
    """
    cache_key = "api:appraisal:json:%s:%s" % (version, result_id)

    # This object should be a dict in the following format:
    # { data: { json (string) formatted item data }, private: { user.Id } }
    #
    # private is populated if the appraisal is set to private with the owning user.Id
    result = cache.get(cache_key)
    if result:
        if "private" in result:
            if not g.user or not g.user.Id == result["private"]:
                return "Forbidden", 403
        return result["data"], 200, {'Content-Type': 'application/json'}

    message, status = estimate_retrieve(result_id)

    if not status == 200:
        return message, status

    if isinstance(message, Appraisals):
        data = {
            'id': message.Id,
            'kind': message.Kind,
            'created': message.Created,
            'market_id': message.Market,
            'market_name': get_market_name(message.Market),
            'items': list(message.iter_types()),
            'totals': message.totals()
        }
        if version > 1:
            data_v2 = {
                'raw': message.RawInput,
                'jsonurl': url_for('estimate_v2', result_id=message.Id, _external=True),
                'url': url_for('display_result', result_id=message.Id, _external=True)
            }
            data.update(data_v2)
        output = {}
        output["data"] = jsonify(data)
        if not message.Public:
            output["private"] = message.UserId

        cache.set(cache_key, output, timeout=30)
        return output["data"], 200, {'Content-Type': 'application/json'}

    return "No Appraisal Found", 500

@login_required_if_config
def estimate_create_v1():
    """Creates an estimate, and redirects to JSON formatted result.
    """
    return estimate_create(1)

@login_required_if_config
def estimate_create_v2():
    """Creates an estimate, and redirects to JSON formatted result.
    """
    return estimate_create(2)

@login_required_if_config
def estimate_history_v1():
    """Returns a JSON formatted list of appraisals from history, including item data.
    """
    return jsonify({'appraisals': estimate_history(1)}), 200, {'Content-Type': 'application/json'}

@login_required_if_config
def estimate_history_csv_v2():
    """Returns a CSV formatted list of historical estimates.
    """
    return dict_to_csv_string(
        estimate_history(2, 'csv'), [
            'id', 'kind', 'created', 'url', 'csvurl', 'market_id', 'market_name',
            'buy', 'sell', 'volume', 'repackaged'
        ]
    ), 200, {'Content-Type': 'text/plain'}

@login_required_if_config
def estimate_history_v2():
    """Returns a JSON formatted list of appraisals from history, without item data.
    """
    return jsonify({'appraisals': estimate_history(2)}), 200, {'Content-Type': 'application/json'}

@login_required_if_config
def estimate_csv_v2(result_id):
    """Returns an appraisal result as a csv formatted string.
    Includes id, kind, created, market_id, market_name,
    item typeId, item name, item all price, item buy price, item sell price
    """
    return estimate_csv(result_id, 2)

@login_required_if_config
def estimate_v2(result_id):
    """Returns an appraisal result as a JSON formatted string.
    Includes id, kind, created, market_id, market_name, items, totals, raw, jsonurl, url
    """
    return estimate_json(result_id, 2)

@login_required_if_config
def estimate_v1(result_id):
    """Returns an appraisal result as a JSON formatted string.
    Includes id, kind, created, market_id, market_name, items, totals
    """
    return estimate_json(result_id, 1)