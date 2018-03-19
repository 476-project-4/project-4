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
from mt_api import get_username, get_user_id, query_db, query_db_json, get_db, close_database

class MtAuth(BasicAuth):
    def check_credentials(self, username, password):
        cursor = get_db().cursor()
        cursor.execute('''select pw_hash from user where username="''' + str(username) + '''"''')
        data = cursor.fetchone()
        if data != None:
            if check_password_hash(data[0], password):
                return True
        return False

# configuration
DATABASE = 'minitwit.db'
PER_PAGE = 30
DEBUG = True
SECRET_KEY = b'_5#y2L"F4Q8z\n\xec]/'

# create our little application :)
app = Flask('minitwit')
basic_auth = MtAuth(app)
app.config.from_object(__name__)
app.config.from_envvar('MINITWIT_SETTINGS', silent=True)

def init_db():
    """Initializes the database."""
    db = get_db()
    with app.open_resource('schema.sql', mode='r') as f:
        db.cursor().executescript(f.read())
    db.commit()

@app.cli.command('initdb')
def initdb_command():
    """Creates the database tables."""
    init_db()
    print('Initialized the database.')

def pop_db():
    """Populates the database"""
    db = get_db()
    user_inserts(db)
    with app.open_resource('population.sql', mode='r') as otherf:
        db.executescript(otherf.read())
        db.commit()

def user_inserts(db):
    db.execute('''INSERT INTO user (username, email, pw_hash)
    VALUES ("Daniel", "foo@bar.com", ?)''', [generate_password_hash('foobar')])
    db.execute('''INSERT INTO user (username, email, pw_hash)
    VALUES ("Sollis", "bar@foo.com", ?)''', [generate_password_hash('barfoo')])
    db.execute('''INSERT INTO user (username, email, pw_hash)
    VALUES ("Kaz", "foo@foo.com", ?)''', [generate_password_hash('foofoo')])
    db.execute('''INSERT INTO user (username, email, pw_hash)
    VALUES ("Antonio", "bar@bar.com", ?)''', [generate_password_hash('barbar')])

@app.cli.command('popdb')
def popdb_command():
    """adds predefined users to database"""
    pop_db()
    print('Populating the Database.')

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

#==============================================================================

@app.before_request
def before_request():
    g.user = None
    if 'user_id' in session:
        g.user = get_username(session['user_id'])
        g.user_id = session['user_id']
        g.password = session['pass_hash']

@app.route('/')
def timeline():
    """Shows a users timeline or if no user is logged in it will
    redirect to the public timeline.  This timeline shows the user's
    messages as well as all the messages of followed users.
    """
    if not g.user:
        return redirect(url_for('public_timeline'))
    r = requests.get("http://localhost:5001/api/users/" + g.user + "/timeline")
    user_timeline_messages = r.json()
    message_list_items = user_timeline_messages[g.user + "'s timeline"]
    message_list = [0] * len(message_list_items)
    for index, x in enumerate(message_list_items):
        message_list[index] = get_timeline_message(x)
    return render_template('timeline.html', messages=message_list)

@app.route('/public')
def public_timeline():
    """Displays the latest messages of all users."""
    r = requests.get("http://localhost:5001/api/public")
    public_timeline = r.json()
    public_message_list = public_timeline["public timeline"]
    public_messages = [0] * len(public_message_list)
    for index, x in enumerate(public_message_list):
        public_messages[index] = get_timeline_message(x)
    return render_template('timeline.html', messages=public_messages)

@app.route('/<username>')
def user_timeline(username):
    """Display's a users tweets."""
    profile_user = query_db('select * from user where username = ?',
                            [username], one=True)
    if profile_user is None:
        abort(404)
    followed = False
    if g.user:
        followed = query_db('''select 1 from follower where
            follower.who_id = ? and follower.whom_id = ?''',
            [session['user_id'], profile_user['user_id']],
            one=True) is not None
    return render_template('timeline.html', messages=query_db('''
            select message.*, user.* from message, user where
            user.user_id = message.author_id and user.user_id = ?
            order by message.pub_date desc limit ?''',
            [profile_user['user_id'], PER_PAGE]), followed=followed,
            profile_user=profile_user)


@app.route('/<username>/follow')
def follow_user(username):
    """Adds the current user as follower of the given user."""
    if not g.user:
        abort(401)
    whom_id = get_user_id(username)
    if whom_id is None:
        abort(404)
    r = requests.post("http://localhost:5001/api/users/" +
                  g.user + "/follow/" + username, auth=(g.user, g.password))
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
    r = requests.post("http://localhost:5001/api/users/" +
                      g.user + "/unfollow/" + username, auth=(g.user, g.password))
    if 'message' in r.json():
        flash(r.json()['message'])
    return redirect(url_for('user_timeline', username=username))


@app.route('/add_message', methods=['POST'])
def add_message():
    """Registers a new message for the user."""
    if 'user_id' not in session:
        abort(401)
    if request.form['text']:
        db = get_db()
        db.execute('''insert into message (author_id, text, pub_date)
          values (?, ?, ?)''', (session['user_id'], request.form['text'],
                                int(time.time())))
        db.commit()
        flash('Your message was recorded')
    return redirect(url_for('timeline'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Logs the user in."""
    if g.user:
        return redirect(url_for('timeline'))
    error = None
    if request.method == 'POST':
        user = query_db('''select * from user where
            username = ?''', [request.form['username']], one=True)
        if user is None:
            error = 'Invalid username'
        elif not check_password_hash(user['pw_hash'],
                                     request.form['password']):
            error = 'Invalid password'
        else:
            flash('You were logged in')
            session['user_id'] = user['user_id']
            session['pass'] = request.form['password']
            return redirect(url_for('timeline'))

    return render_template('login.html', error=error)


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
            db = get_db()
            db.execute('''insert into user (
              username, email, pw_hash) values (?, ?, ?)''',
              [request.form['username'], request.form['email'],
               generate_password_hash(request.form['password'])])
            db.commit()
            flash('You were successfully registered and can login now')
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
