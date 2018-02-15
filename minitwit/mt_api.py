import time
from sqlite3 import dbapi2 as sqlite3
from hashlib import md5
from datetime import datetime
from flask import Flask, request, session, url_for, redirect, \
     render_template, abort, g, flash, _app_ctx_stack
from werkzeug import check_password_hash, generate_password_hash
from flask_basicauth import BasicAuth

def check_credentials(username, password):
    cursor = get_db()
    cursor.execute('''select pw_hash from user where user="''' + str(username) + '''"''')
    data = cursor.fetchall()
    if data != None:
        if generate_password_hash(password) == data[0][0]:
            return True
    return False

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
