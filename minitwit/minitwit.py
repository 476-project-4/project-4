# -*- coding: utf-8 -*-
"""
    MiniTwit
    ~~~~~~~~

    A microblogging application written with Flask and sqlite3.

    :copyright: (c) 2015 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""

import time
from sqlite3 import dbapi2 as sqlite3
from hashlib import md5
from datetime import datetime
from flask import Flask, request, session, url_for, redirect, \
     render_template, abort, g, flash, _app_ctx_stack, jsonify
from werkzeug import check_password_hash, generate_password_hash
from flask_basicauth import BasicAuth

class MtAuth(BasicAuth):
    def check_credentials(self, username, password):
        cursor = get_db().cursor()
        cursor.execute('''select pw_hash from user where username="''' + str(username) + '''"''')
        data = cursor.fetchone()
        if data != None:
            print data[0]
            print password
            generate_password_hash(password)
            print
            if generate_password_hash(password) == data[0]:
                print "bar"
                return True
        return False

# configuration
DATABASE = 'minitwit.db'
PER_PAGE = 30
DEBUG = True
SECRET_KEY = b'_5#y2L"F4Q8z\n\xec]/'

# create our little application :)
app = Flask('minitwit')
basic_auth = mt_auth(app)
app.config.from_object(__name__)
app.config.from_envvar('MINITWIT_SETTINGS', silent=True)


def get_db():
    """Opens a new database connection if there is none yet for the
    current application context.
    """
    top = _app_ctx_stack.top
    if not hasattr(top, 'sqlite_db'):
        top.sqlite_db = sqlite3.connect(app.config['DATABASE'])
        top.sqlite_db.row_factory = sqlite3.Row
    return top.sqlite_db


@app.teardown_appcontext
def close_database(exception):
    """Closes the database again at the end of the request."""
    top = _app_ctx_stack.top
    if hasattr(top, 'sqlite_db'):
        top.sqlite_db.close()


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

@app.cli.command('restartdb')
def restartdb_command():
    initdb()
    popdb()
    print('Remaking the Database.')

def query_db(query, args=(), one=False):
    """Queries the database and returns a list of dictionaries."""
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    return (rv[0] if rv else None) if one else rv


def get_user_id(username):
    """Convenience method to look up the id for a username."""
    rv = query_db('select user_id from user where username = ?',
                  [username], one=True)
    return rv[0] if rv else None


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
        g.user = query_db('select * from user where user_id = ?',
                          [session['user_id']], one=True)

@app.route('/')
def timeline():
    """Shows a users timeline or if no user is logged in it will
    redirect to the public timeline.  This timeline shows the user's
    messages as well as all the messages of followed users.
    """
    if not g.user:
        return redirect(url_for('public_timeline'))
    return render_template('timeline.html', messages=query_db('''
        select message.*, user.* from message, user
        where message.author_id = user.user_id and (
            user.user_id = ? or
            user.user_id in (select whom_id from follower
                                    where who_id = ?))
        order by message.pub_date desc limit ?''',
        [session['user_id'], session['user_id'], PER_PAGE]))

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
@app.route('/api/timeline', methods = ['GET'])
def get_timeline():
    cursor = get_db().cursor()
    messages = cursor.execute('''
        select user.username, message.text, message.pub_date from message, user
        where message.author_id = user.user_id
        order by message.pub_date desc limit ?''', [PER_PAGE])
    if messages == None:
        return jsonify({'Error Code' : '404'})
    r = [dict((cursor.description[i][0], value)
              for i, value in enumerate(row)) for row in cursor.fetchall()]
    return jsonify({'timeline' : r})

@app.route('/api/users', methods = ['GET'])
def get_users():
    cursor = get_db().cursor()
    users = cursor.execute('''select * from user;''')
    r = [dict((cursor.description[i][0], value)
              for i, value in enumerate(row)) for row in cursor.fetchall()]
    return jsonify({'users' : r})


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

@app.route('/api/users', methods = ['POST'])
def add_user():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''select pw_hash from user where username="''' + request.authorization["username"] + '''";''')
    current_users = cursor.fetchall()
    if basic_auth.check_credentials(request.authorization["username"], request.authorization["password"]):
        r = [dict((cursor.description[i][0], value)
              for i, value in enumerate(row)) for row in cursor.fetchall()]
        cursor.execute('''insert into user (username, email, pw_hash)
         values (?, ?, ?)''', [request.json.get('username'), request.json.get('email'), generate_password_hash(request.json.get('password'))])
        db.commit()
        return jsonify({'status code' : '200'})
    return jsonify({'status code' : '405'})

@app.route('/api/users/<username>/followers', methods = ['GET'])
def get_followers(username):
    print "foo"
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''select user_id from user where username="''' + str(username) +'''"''')
    user_id = cursor.fetchone()
    if user_id is None:
        return jsonify({"status code" : "404"})
    cursor.execute('''select whom_id from follower where who_id="''' + str(user_id[0]) + '''"''')
    follower_ids = [dict((cursor.description[i][0], value)
              for i, value in enumerate(row)) for row in cursor.fetchall()]
    follower_names = {}
    for i in follower_ids:
        name = cursor.execute('''select username from user where user_id="''' + str(i["whom_id"]) + '''"''').fetchone()[0]
        print str(name)
        for j in range(0, len(follower_ids)):
            follower_names[j] = str(name)
    return_dict = {}
    for i in range(0, len(follower_names)):
        return_dict[str(i + 1)] = follower_names[i]
    return jsonify({"followers" : return_dict})

@app.route('/api/users/<username>/following', methods = ['GET'])
def get_following(username):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''select user_id from user where username="''' + str(username) +'''"''')
    user_id = cursor.fetchone()
    if user_id is None:
        return jsonify({"status code" : "404"})
    cursor.execute('''select whom_id from follower where who_id="''' + str(user_id[0]) + '''"''')
    follower_ids = [dict((cursor.description[i][0], value)
              for i, value in enumerate(row)) for row in cursor.fetchall()]
    follower_names = {}
    for i in follower_ids:
        name = cursor.execute('''select username from user where user_id="''' + str(i["whom_id"]) + '''"''').fetchone()[0]
        print str(name)
        for j in range(0, len(follower_ids)):
            follower_names[j] = str(name)
    return_dict = {}
    for i in range(0, len(follower_names)):
        return_dict[str(i + 1)] = follower_names[i]
    return jsonify({"followers" : return_dict})


@app.route('/api/messages/<username>/<text>', methods = ['POST'])
def insert_message(username, text):
    cursor = get_db.cursor()
    current_time = int(round(time.time() * 1000))


# add some filters to jinja
app.jinja_env.filters['datetimeformat'] = format_datetime
app.jinja_env.filters['gravatar'] = gravatar_url
