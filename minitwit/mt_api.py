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

@app.route('/api/user', methods = ['GET'])
def user_timeline():
    cursor = get_db()
    username = request.json.get('username')
    cursor.execute('''select user_id from user where user="''' + str(username) + '''"''')
    user_id = cursor.fetchall()[0][0]
    cursor.execute('''select * from message where author_id="''' + str(user_id) + '''"''')
    r = [dict((cursor.description[i][0], value)
              for i, value in enumerate(row)) for row in cursor.fetchall()]
    return jsonify({'messages' : r})
