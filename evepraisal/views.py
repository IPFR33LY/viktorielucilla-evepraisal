# -*- coding: utf-8 -*-
"""
    An Eve Online Cargo Scanner
"""
import base64
import json
import uuid

from flask import (
    g, flash, request, render_template, url_for, redirect, session,
    send_from_directory)
from sqlalchemy import desc

from evepraisal.api import estimate_retrieve
from evepraisal.estimate import create_appraisal
from evepraisal.helpers import login_required, login_required_if_config
from evepraisal.models import Appraisals, Users, appraisal_count
from . import app, db, cache, evesso


@login_required_if_config
def estimate_cost():
    """ Estimate Cost of pasted stuff result given by POST[raw_paste].
        Renders HTML """
    raw_paste = request.form.get('raw_paste', '')
    solar_system = request.form.get('market', '30000142')

    appraisal = create_appraisal(raw_paste, solar_system)

    # Yes, this returns a string on exception. I really don't care.
    if not isinstance(appraisal, basestring):
        return render_template('results.html', appraisal=appraisal)
    else:
        return render_template('error.html', error='Error when parsing input: ' + str(appraisal))

@login_required_if_config
def display_result(result_id):
    message, status = estimate_retrieve(result_id)
    if not status == 200:
        return message, status
    return redirect(url_for(display_result, appraisal=message,result_id=message.id, full_page=True))

    #render_template('results.html', appraisal=message, full_page=True)

 #appraisal=message, full_page=True
@login_required
def options():
    if request.method == 'POST':
        autosubmit = True if request.form.get('autosubmit') == 'on' else False
        paste_share = True if request.form.get('share') == 'on' else False

        enable_api = True if request.form.get('enablekey') == 'on' else False
        disable_api = True if request.form.get('disablekey') == 'on' else False

        new_options = {
            'autosubmit': autosubmit,
            'share': paste_share,
        }
        session['options'] = new_options
        g.user.Options = json.dumps(new_options)

        if disable_api:
            g.user.SecretKey = None
        elif enable_api:
            g.user.SecretKey = str(uuid.uuid4()).replace('-', '')

        db.session.add(g.user)
        db.session.commit()
        flash('Successfully saved options.')

    combinedKey = None
    if g.user.SecretKey is not None:
        combinedKey = base64.b64encode(g.user.OpenId + ':' + g.user.SecretKey)

    return render_template('options.html', characterid=session['character']['CharacterID'], secretkey=g.user.SecretKey,
                           combinedkey=combinedKey)


@login_required_if_config
def history():
    q = Appraisals.query

    if g.user:
        q = q.filter(Appraisals.UserId == g.user.Id)
    elif 'epsessionid' in session:
        q = q.filter(Appraisals.SessionId == session['epsessionid'])
    else:
        q = q.filter(1 == 2)

    q = q.order_by(desc(Appraisals.Created))
    q = q.limit(100)
    appraisals = q.all()

    return render_template('history.html', appraisals=appraisals)


@login_required_if_config
def latest():
    cache_key = "latest:%s" % request.args.get('kind', 'all')
    body = cache.get(cache_key)
    if body:
        return body
    q = Appraisals.query
    q = q.filter_by(Public=True)  # NOQA
    if request.args.get('kind'):
        q = q.filter_by(Kind=request.args.get('kind'))  # NOQA
    q = q.order_by(desc(Appraisals.Created))
    q = q.limit(200)
    appraisals = q.all()
    body = render_template('latest.html', appraisals=appraisals)
    cache.set(cache_key, body, timeout=30)
    return body


def index():
    "Index. Renders HTML."

    count = cache.get("stats:appraisal_count")
    if not count:
        count = appraisal_count()
        cache.set("stats:appraisal_count", count, timeout=60)

    if not g.user and app.config["REQUIRE_LOGIN"]:
        flash('Login Required.', 'warning')

    return render_template('index.html', appraisal_count=count,
                           require_login=False if g.user else app.config["REQUIRE_LOGIN"])


def legal():
    return render_template('legal.html')


def freighter():
    return render_template("freighter.html")


def static_from_root():
    return send_from_directory(app.static_folder, request.path[1:])


def login():
    # if we are already logged in, go back to were we came from
    if 'character' in session:
        return redirect(url_for('index'))
    elif request.args.get('required', '') == 'yes':
        return render_template('requirelogin.html');
    else:
        return evesso.authorize(callback=url_for('openauth_callback', _external=True, _scheme="https"))


def openauth_callback():
    resp = evesso.authorized_response()
    if resp is None:
        return 'Access denied: reason=%s error=%s' % (
            request.args['error_reason'],
            request.args['error_description']
        ), 500
    if isinstance(resp, Exception):
        return 'Access denied: error=%s' % str(resp), 500

    session['evesso_token'] = (resp['access_token'], '')

    verify = evesso.get("verify")
    session['character'] = verify.data
    characterId = verify.data['CharacterID']

    user = Users.query.filter_by(OpenId=characterId).first()
    if user is None:
        user = Users(OpenId=characterId, Options=json.dumps(app.config['USER_DEFAULT_OPTIONS']))
        db.session.add(user)
        db.session.commit()

    g.user = user

    reclaimscans()

    flash(u'Logged in')
    return redirect(url_for("index"))


def reclaimscans():
    """ this method takes all scans associated with the current session and
        associates them with the user account instead. This way if you login after
        a scan, you don't lose it, it is associated with your user.
    """
    if 'character' not in session:
        return

    if 'epsessionid' not in session:
        return

    sessionid = session['epsessionid']

    Appraisals.query.filter_by(SessionId=sessionid).update({"UserId": g.user.Id, "SessionId": None},
                                                           synchronize_session=False)
    db.session.commit()


@evesso.tokengetter
def get_evesso_oauth_token():
    return session.get('evesso_token')


def logout():
    session.clear()
    flash(u'You have been signed out')
    return redirect(url_for('index'))
