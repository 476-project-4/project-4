import time
from sqlite3 import dbapi2 as sqlite3
from hashlib import md5
from datetime import datetime
from flask import Flask, request, session, url_for, redirect, \
     render_template, abort, g, flash, _app_ctx_stack
from werkzeug import check_password_hash, generate_password_hash
from flask_basicauth import BasicAuth

class MtAuth(BasicAuth):
    def __init__(self):
        BasicAuth.__init__(self)
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

app = Flask('minitwit')
basic_auth = MtAuth(app)

def get_db():
    """Opens a new database connection if there is none yet for the
    current application context.
    """
    top = _app_ctx_stack.top
    if not hasattr(top, 'sqlite_db'):
        top.sqlite_db = sqlite3.connect(app.config['DATABASE'])
        top.sqlite_db.row_factory = sqlite3.Row
    return top.sqlite_db

def query_db(query, args=(), one=False):
    """Queries the database and returns a list of dictionaries."""
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    return (rv[0] if rv else None) if one else rv


@app.teardown_appcontext
def close_database(exception):
    """Closes the database again at the end of the request."""
    top = _app_ctx_stack.top
    if hasattr(top, 'sqlite_db'):
        top.sqlite_db.close()

@app.route('/api/timeline', methods = ['GET'])
@basic_auth.required
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
    return jsonify({"following" : return_dict})

@app.route('/api/users/<username>/<passw>/<email>', methods = ['POST'])
def add_user(username, passw, email):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''select username from user;''')
    current_users = cursor.fetchall()
    for i in range(0, len(current_users)):
        if username == current_users[i][0]:
            return jsonify({'status code' : 'BAD'})
    cursor.execute('''insert into user (username, email, pw_hash)
     values (?, ?, ?)''', [username, email, generate_password_hash(passw)])
    db.commit()
    return jsonify({'status code' : '200'})

@app.route('/api/messages/<username>/<text>', methods = ['POST'])
def insert_message(username, text):
    cursor = get_db.cursor()


#need to make a follow api route requires auth

#'''select message.*, user.* from message, user where message.author_id = user.user_id and (user.user_id = ? or user.user_id in (select whom_id from follower where who_id = ?)) order by message.pub_date desc limit ?'''
@app.route('/api/<username>/dashboard', methods = ['GET'])
def get_dash(username):
    messages = query_db('''
        select message.*, user.* from message, user
        where message.author_id = user.user_id and (
            user.user_id = ? or
            user.user_id in (select whom_id from follower
                                    where who_id = ?))
        order by message.pub_date desc limit ?''',
        [5, 5, PER_PAGE])
    return jsonify(messages)
