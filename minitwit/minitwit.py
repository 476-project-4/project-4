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

#==============================================================================

@app.before_request
def before_request():
    g.user = None
    if 'user_id' in session:
        g.user = get_username(session['user_id'])

@app.route('/')
def timeline():
    """Shows a users timeline or if no user is logged in it will
    redirect to the public timeline.  This timeline shows the user's
    messages as well as all the messages of followed users.
    """
    if not g.user:
        return redirect(url_for('public_timeline'))
    r = requests.get("http://localhost:5001/api/users/Daniel/timeline")
    user_timeline = r.json()
    message_list_items = user_timeline[g.user + "'s timeline"]
    message_list = [0] * len(message_list_items)
    for index, x in enumerate(message_list_items):
        post = type('Post', (object,), {})()
        post.text = x['text']
        post.username = get_username(x['author_id'])
        post.email = x['email']
        post.pub_date = x['pub_date']
        message_list[index] = post
    return render_template('timeline.html', messages=message_list)

@app.route('/public')
def public_timeline():
    """Displays the latest messages of all users."""
    return render_template('timeline.html', messages=query_db('''
        select message.*, user.* from message, user
        where message.author_id = user.user_id
        order by message.pub_date desc limit ?''', [PER_PAGE]))

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
    db = get_db()
    db.execute('insert into follower (who_id, whom_id) values (?, ?)',
              [session['user_id'], whom_id])
    db.commit()
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
    db = get_db()
    db.execute('delete from follower where who_id=? and whom_id=?',
              [session['user_id'], whom_id])
    db.commit()
    flash('You are no longer following "%s"' % username)
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

#testing API endpoints
"""API Route for getting all users"""
@app.route('/api/users', methods = ['GET'])
def get_users():
    cursor = get_db().cursor()
    users = cursor.execute('''select * from user;''')
    r = [dict((cursor.description[i][0], value)
              for i, value in enumerate(row)) for row in cursor.fetchall()]
    return jsonify({'users' : r})

"""API Route for Public Timeline"""
@app.route('/api/public', methods = ['GET'])
def get_public():
    messages=query_db_json('''
        select message.*, user.username from message, user
        where message.author_id = user.user_id
        order by message.pub_date desc limit ?''', 'public timeline', [PER_PAGE])
    return messages

"""API Route for getting users timeline (All messages made by user)"""
@app.route('/api/users/<username>/timeline', methods = ['GET'])
def users_timeline(username):
    if request.method != 'GET':
        return jsonify({'status code' : '405'})
    cursor = get_db().cursor()
    cursor.execute('''select user_id from user where username="''' + str(username) + '''"''')
    user_id = cursor.fetchone()
    if user_id == None:
        return jsonify({'status code' : '404'})
    cursor.execute('''select * from message where author_id="''' + str(user_id[0]) + '''"''')
    r = [dict((cursor.description[i][0], value)
              for i, value in enumerate(row)) for row in cursor.fetchall()]
    return jsonify({str(username) + '\'s timeline' : r})

"""API Route for registering new user"""
@app.route('/api/register', methods = ['POST'])
def add_user():
    cursor = get_db().cursor()
    cursor.execute('''select user_id from user where username="''' + str(request.authorization["username"]) + '''"''')
    user_id = cursor.fetchone()
    email = request.form.get("email")
    if user_id != None:
        return jsonify({"message": "That username is already taken. Please try a different username."})
    elif email == None:
        return jsonify({"message": "There was no email for the user in the request body. Please add the user's email in the 'email' form in the request body"})
    else:
        db = get_db()
        db.execute('insert into user (username, email, pw_hash) values (?, ?, ?)',
            [request.authorization["username"], email, generate_password_hash(request.authorization["password"])])
        db.commit()
        m = "Success, user has been added."
        return jsonify({"message" : m})



"""API Route for getting users who username is followed by"""
@app.route('/api/users/<username>/followers', methods = ['GET'])
def get_followers(username):
    cursor = get_db().cursor()
    user_id = get_user_id(username)
    if user_id is None:
        return jsonify({"status code" : "404"})
    cursor.execute('''select who_id from follower where whom_id="''' + str(user_id) + '''"''')
    follower_ids = [dict((cursor.description[i][0], value)
              for i, value in enumerate(row)) for row in cursor.fetchall()]
    follower_names = []
    for i in range(len(follower_ids)):
        name = get_username(int(follower_ids[i].values()[0]))
        follower_names.append(name)
    return_dict = {}
    for i in range(0, len(follower_names)):
        return_dict[str(i + 1)] = follower_names[i]
    return jsonify({"followers" : return_dict})

"""API Route for getting users who username is following"""
@app.route('/api/users/<username>/following', methods = ['GET'])
def get_following(username):
    cursor = get_db().cursor()
    user_id = get_user_id(username)
    if user_id is None:
        return jsonify({"status code" : "404"})
    cursor.execute('''select whom_id from follower where who_id="''' + str(user_id) + '''"''')
    follower_ids = [dict((cursor.description[i][0], value)
              for i, value in enumerate(row)) for row in cursor.fetchall()]
    follower_names = []
    for i in range(len(follower_ids)):
        name = get_username(int(follower_ids[i].values()[0]))
        follower_names.append(name)
    return_dict = {}
    for i in range(0, len(follower_names)):
        return_dict[str(i + 1)] = follower_names[i]
    return jsonify({"following" : return_dict})

"""API Route for posting"""
@app.route('/api/users/<username>/post', methods = ['POST'])
@basic_auth.required
def insert_message(username):
    post_message = request.form.get("message")
    if post_message == None:
        return jsonify({"Error" : "There was no message in the request body. Please add what you would like to post under the 'message' form in the request body"})
    if request.authorization["username"] == username:
        db = get_db()
        db.execute('insert into message (author_id, text, pub_date) values (?, ?, ?)',
            [get_user_id(username), post_message, time.time()])
        db.commit()
        m = "Success, you've made a post."
        return jsonify({"message" : m})
    else:
        return jsonify({"status code" : "403 Forbidden: You cannot post to a user that isn't you"})

"""API route for getting a users Dashboard (Timeline of followed users)"""
@app.route('/api/users/<username>/dashboard', methods = ['GET'])
@basic_auth.required
def get_dash(username):
    if request.authorization["username"] == username:
        messages = query_db_json('''
            select message.*, user.username from message, user
            where message.author_id = user.user_id and (
                user.user_id = ? or
                user.user_id in (select whom_id from follower
                                    where who_id = ?))
                order by message.pub_date desc limit ?''', 'dashboard',
                [get_user_id(username), get_user_id(username), PER_PAGE])
        return messages
    else:
        return jsonify({"status code" : "403 Forbidden: This dashboard doesn't belong to you"})

"""Route for Api Follow"""
@app.route('/api/users/<follower>/follow/<followee>', methods = ['POST'])
@basic_auth.required
def api_follow(follower, followee):
    if request.authorization["username"] == follower:
        if(get_user_id(follower) == get_user_id(followee)):
            return jsonify({"Error" : "You can't follow yourself"})
        followee_id = get_user_id(followee)
        follower_id = get_user_id(follower)
        if followee_id is None or follower_id is None:
            return jsonify({"status code" : "404: User not found."})
        db = get_db()
        db.execute('insert into follower (who_id, whom_id) values (?, ?)',
            [get_user_id(follower), get_user_id(followee)])
        db.commit()
        m = "Success, You are now following " + followee
        return jsonify({"message" : m})
    else:
        return jsonify({"status code" : "403 Forbidden: You're trying to make someone who isn't you follow someone else."})

"""Route for Api Unfollow"""
@app.route('/api/users/<follower>/unfollow/<followee>', methods = ['DELETE'])
@basic_auth.required
def api_unfollow(follower, followee):
    if request.authorization["username"] == follower:
        if(get_user_id(follower) == get_user_id(followee)):
            return jsonify({"Error" : "You can't unfollow yourself"})
        followee_id = get_user_id(followee)
        follower_id = get_user_id(follower)
        if followee_id is None or follower_id is None:
            return jsonify({"status code" : "404: User not found."})
        db = get_db()
        db.execute('delete from follower where who_id=? and whom_id=?',
                  [followee_id, follower_id])
        db.commit()
        m = "Success, you unfollowed " + followee
        return jsonify({"message" : m})
    else:
        return jsonify({"status code" : "403 Forbidden: You're trying to make someone who isn't you unfollow someone else."})



# add some filters to jinja
app.jinja_env.filters['datetimeformat'] = format_datetime
app.jinja_env.filters['gravatar'] = gravatar_url
