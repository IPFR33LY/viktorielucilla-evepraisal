# -*- coding: utf-8 -*-
"""
    Evepraisal
"""
import base64
import json
import locale
import os
import sys

from flask import Flask, g, session, request
from flask_babel import Babel
from flask_cache import Cache
from flask_oauthlib.client import OAuth
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
# app.run(DEBUG=True)
# configuration
CONFIG_EVEPRAISAL_DEBUG = os.environ.get("CONFIG_EVEPRAISAL_DEBUG", "False")
USE_ANGULAR = True
app.config['DEBUG'] = CONFIG_EVEPRAISAL_DEBUG.lower() == "true"
app.config['VALID_SOLAR_SYSTEMS'] = {
    '-1': 'Universe',
    '30000142': 'Jita',
    '30002187': 'Amarr',
    '30002659': 'Dodixie',
    '30002510': 'Rens',
    '30002053': 'Hek',
}
app.config['USER_AGENT'] = 'Evepraisal/1.0 +http://roflcows.com/'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# no memcached support for windows, and we need to flip slashes. deal with it.
if sys.platform == 'win32':
    app.config['CACHE_TYPE'] = 'memcached'
    app.config['SQLALCHEMY_DATABASE_URI'] = (
        'sqlite:///%s\data\scans.db' % os.getcwd()
    )
else:
    app.config['CACHE_TYPE'] = 'memcached'
    app.config['SQLALCHEMY_DATABASE_URI'] = (
        'sqlite:////%s/data/scans.db' % os.getcwd()
    )

ads = os.environ.get("CONFIG_GOOGLE_ADS", "")
if ads == "":
    ads = {
        'enabled': False,
        'style': 'display:inline-block;width:728px;height:90px',
        'client': 'ca-pub-9783525020998199',
        'slot': '5763357268'
    }
else:
    ads = json.loads(ads)

ga = os.environ.get("CONFIG_GOOGLE_ANALYTICS", "")
if ga == "":
    ga = {
        'enabled': False,
        'account': 'UA-12594271-4',
        'domain': 'evepraisal.com'
    }
else:
    ga = json.loads(ga)

app.config['CACHE_KEY_PREFIX'] = 'evepraisal'
app.config['CACHE_MEMCACHED_SERVERS'] = ['127.0.0.1:11211']
app.config['CACHE_DEFAULT_TIMEOUT'] = 10 * 60
app.config['TEMPLATE'] = 'sudorandom'
app.config['SECRET_KEY'] = os.environ.get(
    "FLASK_SECRET_KEY",
    "SET ME TO SOMETHING SECRET IN THE APP CONFIG!"
)
app.config['USER_DEFAULT_OPTIONS'] = {'autosubmit': False, 'share': True}
app.config['REQUIRE_LOGIN'] = os.environ.get("REQUIRE_LOGIN", "false").lower() == "true"
app.config['CONFIG_GOOGLE_ADS'] = ads
app.config['CONFIG_GOOGLE_ANALYTICS'] = ga

app.config['EVESSO'] = dict(
    consumer_key=os.environ.get("EVESSO_CLIENT_ID", "CLIENT_ID"),
    consumer_secret=os.environ.get("EVESSO_SECRET_KEY", "SECRET_KEY"),
    base_url='https://login.eveonline.com/oauth/',
    access_token_url='https://login.eveonline.com/oauth/token',
    access_token_method='POST',
    authorize_url='https://login.eveonline.com/oauth/authorize',
)

app.config.from_pyfile('../application.cfg', silent=True)

locale.setlocale(locale.LC_ALL, '')

oauth = OAuth()
evesso = oauth.remote_app('evesso', app_key='EVESSO')
oauth.init_app(app)
db = SQLAlchemy(app)
babel = Babel(app)
cache = Cache()
cache.init_app(app)

# Late import so modules can import their dependencies properly
from evepraisal import models, views, routes, filters

__all__ = ['models', 'views', 'routes', 'filters', 'app', 'db', 'cache']


@app.before_first_request
def before_first_request():
    try:
        db.create_all()
    except Exception as e:
        app.logger.error(str(e))


@app.before_request
def before_request():
    g.user = None

    if 'character' in session:
        g.user = models.Users.query.filter_by(OpenId=session['character']['CharacterID']).first()
        if g.user is None:
            # Fix for users with old session cookie that doesn't match a DB entry.
            session.clear()

    elif request.headers.get('Authorization', '') != '':
        auth = request.headers.get('Authorization')
        if auth.startswith("Basic "):
            try:
                auth = auth[6:]
                complete = str(base64.decodestring(auth))
                pieces = complete.split(':')
                tuser = models.Users.query.filter_by(OpenId=pieces[0], SecretKey=pieces[1]).first()
                g.user = tuser
            except:
                pass

    if g.user and not session.get('loaded_options'):
        # Decode options if there are any
        if g.user.Options:
            options = json.loads(g.user.Options)
            session['options'] = options

        session['loaded_options'] = True

    if 'options' not in session:
        session['options'] = app.config['USER_DEFAULT_OPTIONS']
