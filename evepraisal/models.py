import json

from sqlalchemy import types
from sqlalchemy.exc import OperationalError

from helpers import iter_types
from . import db


class JsonType(types.TypeDecorator):
    impl = types.VARCHAR

    def process_bind_param(self, value, engine):
        return json.dumps(value)

    def process_result_value(self, value, engine):
        return json.loads(value)


class Appraisals(db.Model):
    __tablename__ = 'Appraisals'

    Id = db.Column(db.Integer(), primary_key=True)
    #: Unique Random Identifier
    rID = db.Column(db.Text(), unique=True, nullable=True)
    #: Bad Lines
    Kind = db.Column(db.Text(), index=True)
    #: Raw Input taken from the user
    RawInput = db.Column(db.Text())
    #: JSON as a result of the parser (evepaste)
    Parsed = db.Column(JsonType())
    #: Parsed result Version
    ParsedVersion = db.Column(db.Integer())
    #: Prices
    Prices = db.Column(JsonType())
    #: Bad Lines
    BadLines = db.Column(JsonType())
    Market = db.Column(db.Integer())
    Created = db.Column(db.Integer(), index=True)
    Public = db.Column(db.Boolean(), index=True, default=True)
    UserId = db.Column(db.Integer(), db.ForeignKey('Users.Id'), index=True)
    SessionId = db.Column(db.Text(), nullable=True, index=True)


    def totals(self):
        total_sell = total_buy = total_volume = total_repackaged = 0

        for item in self.iter_types():
            # Don't factor blueprint copies into the total
            if item.get('bpc'):
                continue

            if not item.get('market'):
                continue

            quantity = item.get('quantity') or 1
            if item['prices']:
                total_sell += item['prices']['sell']['price'] * quantity
                total_buy += item['prices']['buy']['price'] * quantity
            if item.get('volume'):
                total_volume += item['volume'] * quantity
                if item.get('repackaged_volume'):
                    total_repackaged += item['repackaged_volume'] * quantity
                else:
                    total_repackaged += item['volume'] * quantity

        return {'sell': total_sell, 'buy': total_buy, 'volume': total_volume, 'repackaged' : total_repackaged}

    def result_list(self):
        """ Returns a structure that looks like this:
            [[kind, result], [kind, result]]

        """
        if self.ParsedVersion == 1:
            return self.Parsed

        return [[self.Kind, self.Parsed]]

    def iter_types(self):
        price_map = dict(self.Prices)
        for kind, parsed in self.result_list():
            for item in iter_types(kind, parsed):
                details = get_type_by_name(item['name'])
                item['prices'] = None
                if details:
                    item.update(details)
                    item['prices'] = price_map.get(item['typeID'])

                if 'BLUEPRINT COPY' in item.get('details', ''):
                    item['bpc'] = True
                    item['prices'] = None

                item['quantity'] = item.get('quantity', 1)
                yield item


class Users(db.Model):
    __tablename__ = 'Users'

    Id = db.Column(db.Integer(), primary_key=True)
    OpenId = db.Column(db.String(200))
    Options = db.Column(db.Text())
    SecretKey = db.Column(db.Text())

def appraisal_count():
    # Postresql counts are slow.
    try:
        res = db.engine.execute("""SELECT reltuples
                                   FROM pg_class r
                                   WHERE relkind = 'r'
                                   AND relname = 'Appraisals';""")
        count = int(res.fetchone()[0])
    except OperationalError:
        count = Appraisals.query.count()
    return count


def row_to_dict(row):
    return dict((col, getattr(row, col))
                for col in row.__table__.columns.keys())


def update_types_repackaged(types):
    """Updates a set of items to have a repackaged size where applicable."""
    for t in types:
        rpkg_volume = get_repackaged_volume(t['groupID'])
        if rpkg_volume > -1:
            t['repackaged_volume'] = rpkg_volume

def get_repackaged_volume(groupId):
    """ This returns the repackaged size for a particular group."""
    shiptype = ''

    if groupId in [31]:
        shiptype = 'shuttle'
    elif groupId in [25, 237, 324, 830, 831, 834, 893, 1283, 1527]:
        shiptype = 'frigate'
    elif groupId in [463, 543]:
        shiptype = 'mining'
    elif groupId in [420, 541, 963, 1305, 1534]:
        shiptype = 'destroyer'
    elif groupId in [26, 358, 832, 833, 894, 906]:
        shiptype = 'cruiser'
    elif groupId in [419, 540, 1201]:
        shiptype = 'bcruiser'
    elif groupId in [28, 380, 1202]:
        shiptype = 'industrial'
    elif groupId in [27, 898, 900]:
        shiptype = 'bship'

    return {
        'shuttle' : 500,
        'frigate' : 2500,
        'mining' : 3750,
        'destroyer' : 5000,
        'cruiser' : 10000,
        'bcruiser' : 15000,
        'industrial' : 20000,
        'bship' : 50000,
        '' : -1
    }[shiptype]

TYPES = json.loads(open('data/types.json').read())
update_types_repackaged(TYPES)
TYPES_BY_NAME = dict((t['typeName'].lower(), t) for t in TYPES)
TYPES_BY_ID = dict((t['typeID'], t) for t in TYPES)

def get_type_by_name(name):
    if not name:
        return
    s = name.lower().strip()
    return (TYPES_BY_NAME.get(s.rstrip('*')) or TYPES_BY_NAME.get(s))


def get_type_by_id(typeID):
    if not typeID:
        return
    return TYPES_BY_ID.get(typeID)
