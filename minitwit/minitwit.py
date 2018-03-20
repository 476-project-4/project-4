# -*- coding: utf-8 -*-
"""
    MiniTwit
    ~~~~~~~~

    A microblogging application written with Flask and sqlite3.

    :copyright: (c) 2015 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""

import time
import datetime
import json
import requests
from sqlite3 import dbapi2 as sqlite3
from hashlib import md5
from datetime import datetime
from flask import Flask, request, session, url_for, redirect, \
     render_template, abort, g, flash, _app_ctx_stack, jsonify
from werkzeug import check_password_hash, generate_password_hash
from flask_basicauth import BasicAuth
from mt_api import get_username, get_user_id, query_db, \
    query_db_json, get_db, close_database, get_g_user, restartdb_command

# configuration
PER_PAGE = 30
DEBUG = True
SECRET_KEY = b'_5#y2L"F4Q8z\n\xec]/'

# create our little application :)
app = Flask('minitwit')
#app.run(debug=True, use_debugger=False, use_reloader=False)
app.config.from_object(__name__)
app.config.from_envvar('MINITWIT_SETTINGS', silent=True)


def format_datetime(timestamp):
    """Format a timestamp for display."""
    return datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d @ %H:%M')


def gravatar_url(email, size=80):
    """Return the gravatar image for the given email address."""
    return 'https://www.gravatar.com/avatar/%s?d=identicon&s=%d' % \
        (md5(email.strip().lower().encode('utf-8')).hexdigest(), size)

def get_timeline_message(x):
    post = type('Post', (object,), {})()
    post.text = x['text']
    post.username = get_username(x['author_id'])
    post.email = x['email']
    post.pub_date = x['pub_date']
    return post

def convert_user(x):
    user = type('User', (object,), {})()
    user.username = x['username']
    user.email = x['email']
    return user

#==============================================================================

@app.before_request
def before_request():
    g.user = None
    if 'user_id' in session:
        g.user = get_g_user()

@app.route('/')
def timeline():
    """Shows a users timeline or if no user is logged in it will
    redirect to the public timeline.  This timeline shows the user's
    messages as well as all the messages of followed users.
    """
    if not g.user:
        return redirect(url_for('public_timeline'))
    r = requests.get("http://localhost:5001/api/users/" + g.user.username + "/dashboard", auth=(g.user.username, session['pass']))
    user_timeline_messages = r.json()
    message_list_items = user_timeline_messages['dashboard']
    message_list = [0] * len(message_list_items)
    for index, x in enumerate(message_list_items):
        message_list[index] = get_timeline_message(x)
    return render_template('timeline.html', messages=message_list)

@app.route('/public')
def public_timeline():
    """Displays the latest messages of all users."""
    r = requests.get("http://localhost:5001/api/public")
    public_message_list = r.json()["public timeline"]
    public_messages = [0] * len(public_message_list)
    for index, x in enumerate(public_message_list):
        public_messages[index] = get_timeline_message(x)
    return render_template('timeline.html', messages=public_messages)

@app.route('/<username>')
def user_timeline(username):
    """Display's a users tweets."""
    profile_user = requests.get("http://localhost:5001/api/users/" + username).json()['user']
    if not profile_user:
        abort(404)
    followed = False
    if g.user:
        followed_request = requests.get("http://localhost:5001/api/users/" +
                                        g.user.username + "/following")
        for x in followed_request.json()["following"]:
            if get_username(x) == username:
                followed = True
    r = requests.get("http://localhost:5001/api/users/" + username + "/timeline")
    user_timeline_items = r.json()[str(username) + '\'s timeline']
    user_messages = [0] * len(user_timeline_items)
    if "status_code" in user_timeline_items:
        return r.json()
    for index, x in enumerate(user_timeline_items):
        user_messages[index] = get_timeline_message(x)

    user_messages.reverse()

    return render_template('timeline.html', messages=user_messages,
                           followed=followed, profile_user=convert_user(profile_user[0]))


@app.route('/<username>/follow')
def follow_user(username):
    """Adds the current user as follower of the given user."""
    if not g.user:
        abort(401)
    whom = requests.get("http://localhost:5001/api/users/" + username).json()['user']
    if not whom:
        abort(404)
    r = requests.post("http://localhost:5001/api/users/" +
                      g.user.username +
                      "/follow/" + username, auth=(g.user.username, session['pass']))
    if 'Error' in r.json():
        flash(r.json()['Error'])
    else:
        flash('You are now following "%s"' % username)
    return redirect(url_for('user_timeline', username=username))


@app.route('/<username>/unfollow')
def unfollow_user(username):
    """Removes the current user as follower of the given user."""
    if not g.user:
        abort(401)
    whom_id = get_user_id(username)
    if whom_id is None:
        abort(404)
    r = requests.delete("http://localhost:5001/api/users/" + g.user.username +
                      "/unfollow/" + username, auth=(g.user.username, session['pass']))
    if 'message' in r.json():
        flash(r.json()['message'])
    return redirect(url_for('user_timeline', username=username))


@app.route('/add_message', methods=['POST'])
def add_message():
    """Registers a new message for the user."""
    if 'user_id' not in session:
        abort(401)
    if request.form['text']:
        message = request.form['text']
        message_header = {'message' : message}
        r = requests.post("http://localhost:5001/api/users/" + g.user.username +
                          "/post", auth=(g.user.username, session['pass']), data=message_header)
        if 'message' in r.json():
            flash(r.json()['message'])
        elif 'Error' in r.json():
            flash(r.json()['Error'])
        elif 'status code' in r.json():
            return r.json()
    return redirect(url_for('timeline'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Logs the user in."""
    if g.user:
        return redirect(url_for('timeline'))
    error = None
    if request.method == 'POST':
        user = requests.get("http://localhost:5001/api/users/" + request.form['username']).json()['user']
        if not user:
            error = 'Invalid username'
        elif not check_password_hash(user[0]['pw_hash'],
                                     request.form['password']):
            error = 'Invalid password'
        else:
            flash('You were logged in')
            session['user_id'] = user[0]['user_id']
            session['pass'] = request.form['password']
            return redirect(url_for('timeline'))

    return render_template('login.html', error=error)

#Need to do
@app.route('/register', methods=['GET', 'POST'])
def register():
    """Registers the user."""
    if g.user:
        return redirect(url_for('timeline'))
    error = None
    if request.method == 'POST':
        if not request.form['username']:
            error = 'You have to enter a username'
        elif not request.form['email'] or \
                '@' not in request.form['email']:
            error = 'You have to enter a valid email address'
        elif not request.form['password']:
            error = 'You have to enter a password'
        elif request.form['password'] != request.form['password2']:
            error = 'The two passwords do not match'
        elif get_user_id(request.form['username']) is not None:
            error = 'The username is already taken'
        else:
            email_header = {'email' : request.form['email']}
            response = requests.post("http://localhost:5001/api/register", auth=(request.form['username'], request.form['password']), data=email_header).json()
            flash(response['message'])
            return redirect(url_for('login'))
    return render_template('register.html', error=error)


@app.route('/logout')
def logout():
    """Logs the user out."""
    flash('You were logged out')
    session.pop('user_id', None)
    return redirect(url_for('public_timeline'))

# add some filters to jinja
app.jinja_env.filters['datetimeformat'] = format_datetime
app.jinja_env.filters['gravatar'] = gravatar_url
