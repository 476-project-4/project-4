"""
Made by Kazander Antonio and Daniel Sollis
To use, in the folder containing mt_api.py, run the command
export FLASK_APP=./mt_api.py
Usage of each of the endpoints is explained in the comment above the endpoint.
"""

import time
from sqlite3 import dbapi2 as sqlite3
from flask import Flask, request, session,_app_ctx_stack, jsonify
from werkzeug import check_password_hash, generate_password_hash
from flask_basicauth import BasicAuth
from uuid import UUID, uuid4

sqlite3.register_converter('GUID', lambda b: UUID(bytes_le=b))
sqlite3.register_adapter(UUID, lambda u: buffer(u.bytes_le))

class MtAuth(BasicAuth):
    def check_credentials(self, username, password):
        shard_server = int(get_user_id(username)) % 3
        cursor = get_db()[shard_server].cursor()
        cursor.execute('''select pw_hash from user where username="''' + str(username) + '''"''')
        data = cursor.fetchone()
        if data is not None:
            if check_password_hash(data[0], password):
                return True
        return False


# configuration
SERVER_1 = 'server_1.db'
SERVER_2 = 'server_2.db'
SERVER_3 = 'server_3.db'
USERNAME_SERVER = 'username_server.db'
PER_PAGE = 30
DEBUG = True
SECRET_KEY = b'_5#y2L"F4Q8z\n\xec]/'

# create our little application :)
app = Flask('minitwit')
basic_auth = MtAuth(app)
app.config.from_object(__name__)
app.config.from_envvar('MINITWIT_SETTINGS', silent=True)


def get_db():
    """Opens a new database connection if there is none yet for the
    current application context.
    """
    top = _app_ctx_stack.top
    db_array = [None] * 3
    for i in range(0, 3):
        top.sqlite_db = sqlite3.connect(app.config['SERVER_' + str(i + 1)], detect_types=sqlite3.PARSE_DECLTYPES)
        top.sqlite_db.row_factory = sqlite3.Row
        db_array[i] = top.sqlite_db
    return db_array


def close_databases(db_array):
    """Closes the database again at the end of the request."""
    for db in db_array:
        db.close()


def init_db():
    """Initializes the database."""
    db_array = get_db()
    sqlite3.register_converter('GUID', lambda b: UUID(bytes_le=b))
    sqlite3.register_adapter(UUID, lambda u: buffer(u.bytes_le))
    for i in range(0, 3):
        db = db_array[i]
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()
    close_databases(db_array)


def get_username_db():
    top = _app_ctx_stack.top
    top.sqlite_db = sqlite3.connect(app.config['USERNAME_SERVER'], detect_types=sqlite3.PARSE_DECLTYPES)
    top.sqlite_db.row_factory = sqlite3.Row
    return top.sqlite_db


def init_username_db():
    db = get_username_db()
    db.execute('''DROP TABLE IF EXISTS id;''')
    db.execute('''CREATE TABLE id(
                  username text PRIMARY KEY,
                  user_id GUID NOT NULL);''')
    db.commit()
    db.close()


@app.cli.command('initdb')
def initdb_command():
    """Creates the database tables."""
    init_db()
    init_username_db()
    print('Database Initialized.')


def pop_db():
    """Populates the database"""
    db_array = get_db()
    user_inserts(db_array)
    message_inserts(db_array)
    follower_inserts(db_array)
    for db in db_array:
        db.commit()
    close_databases(db_array)


def user_inserts(db_array):
    insert_user(db_array, "Daniel", "foo@bar.com", "foobar")
    insert_user(db_array, "Sollis", "bar@foo.com", "barfoo")
    insert_user(db_array, "Kaz", "foo@foo.com", "foofoo")
    insert_user(db_array, "Antonio", "bar@bar.com", "barbar")
    insert_user(db_array, "slut", "test@bar.com", "barbar")


def message_inserts(db_array):
    populate_message(db_array, "Daniel", "I", 6)
    populate_message(db_array, "Daniel", "CAN", 5)
    populate_message(db_array, "Kaz", "CODE", 4)
    populate_message(db_array, "Daniel", "I'M", 3)
    populate_message(db_array, "Sollis", "Not a", 2)
    populate_message(db_array, "Daniel", "Moron", 1)
    populate_message(db_array, "Sollis", "Oy", 0)
    populate_message(db_array, "Daniel", "Yo", 0)


def follower_inserts(db_array):
    insert_followers(db_array, "Daniel", "Kaz")
    insert_followers(db_array, "Kaz", "Daniel")
    insert_followers(db_array, "Sollis", "Antonio")
    insert_followers(db_array, "Antonio", "Daniel")


def insert_user(db_array, username, email, pw):
    user_id = uuid4()
    shard_server = int(user_id) % 3
    user_id_db = get_username_db()
    user_id_db.execute('''INSERT INTO id (user_id, username)
      VALUES (?, "''' + username + '''")''', (user_id, ))
    db_array[shard_server].execute('''INSERT INTO user (user_id, username, email, pw_hash)
      VALUES (?, "''' + username + '''", "''' + email + '''", "''' +
        str(generate_password_hash(pw)) + '''")''', (user_id, ))
    db_array[shard_server].commit()
    user_id_db.commit()
    user_id_db.close()


def populate_message(db_array, username, text, pub_date):
    user_id = get_user_id(username)
    message_id = uuid4()
    shard_server = int(user_id) % 3
    db_array[shard_server].execute('''INSERT INTO message (author_id, message_id, text, pub_date)
      VALUES(?, ?, "''' + text + '''", "''' + str(pub_date) + '''")''', (user_id, message_id))
    db_array[shard_server].commit()


def insert_followers(db_array, username, follower):
    user_id = get_user_id(username)
    follower_id = get_user_id(follower)
    shard_server = int(user_id) % 3
    db_array[shard_server].execute('''INSERT INTO follower (who_id, whom_id)
      VALUES (?, ?)''', (user_id, follower_id))


@app.cli.command('popdb')
def popdb_command():
    """adds predefined users to database"""
    pop_db()
    print('Database Populated.')


@app.cli.command('newdb')
def restartdb_command():
    init_db()
    init_username_db()
    pop_db()
    print('Database Remade.')


def get_user_id(username):
    """Convenience method to look up the id for a username."""
    db = get_username_db()
    db_array = get_db()
    result = db.execute('''SELECT user_id FROM id WHERE username="''' + username + '''";''')
    user_id = result.fetchone()[0]
    return user_id


def get_username(user_id):
    """Convenience method to look up the id for a username."""
    db = get_username_db()
    result = db.execute('''SELECT username FROM id WHERE user_id=?''', (user_id,))
    username = result.fetchone()[0]
    return username


# ===============================================================================
# testing API endpoints


"""
API Route for getting all users
Just send a GET request to /api/users to get all users back in a json.
"""

#DONE
@app.route('/api/users', methods=['GET'])
def get_users():
    db_array = get_db()
    results = []
    for db in db_array:
        user_rows = db.execute('''SELECT email, pw_hash, user_id, username FROM user''')
        if user_rows is not None:
            for row in user_rows:
                key = user_rows.description
                results.append({key[0][0]: row[0], key[1][0]: row[1], key[2][0]: row[2], key[3][0]: row[3]})
    results = sorted(results, key=lambda k: k['user_id'])
    return jsonify({'Users': results})

#DONE
"""
API Route for Public Timeline
Just send a GET request to /api/public to get all of the public timeline back in a json.
"""
@app.route('/api/public', methods = ['GET'])
def get_public():
    db_array = get_db()
    results = []
    for db in db_array:
        user_rows = db.execute('''
             select message.*, user.username, user.email from message, user
             where message.author_id = user.user_id
             order by message.pub_date desc limit ?''', [PER_PAGE])
        if user_rows is not None:
            for row in user_rows:
                key = user_rows.description
                results.append({key[0][0]: row[0], key[1][0]: row[1], key[2][0]: row[2], key[3][0]: row[3], key[4][0]: row[4], key[5][0]: row[5]})
    sorted_results = sorted(results, key=lambda k: k['pub_date'])
    return jsonify({'public timeline': sorted_results})

"""
API Route for getting users timeline (All messages made by user)
Send a GET request to "/api/users/<username>/timeline" (replacing <username> with desired username)
to get back all of that users posts in a json.
"""
#DONE
@app.route('/api/users/<username>/timeline', methods = ['GET'])
def users_timeline(username):
    db_array = get_db()
    user_id = get_user_id(username)
    shard_server = int(user_id) % 3
    info_query = db_array[shard_server].execute('''select email from user where username=?''', (username,))
    email = info_query.fetchone()[0]
    message_rows = db_array[shard_server].execute('''
         select * from message where author_id=?''', (user_id,))
    results = []
    if message_rows is not None:
        for row in message_rows:
            key = message_rows.description
            results.append({key[0][0]: row[0], key[1][0]: row[1], key[2][0]: row[2], key[3][0]: row[3], 'email': email})
    sorted_results = sorted(results, key=lambda k: k['pub_date'])
    return jsonify({username + '\'s timeline': sorted_results})

"""
API Route for registering new user
This route only takes POST requests.
A new user requires a new username, password, and email.
This route doesn't actually require authentication, but still uses those fields.
The username and password should be put into the authorization form of the request, using Basic Authentication.
The email of the user should be put into the request body under the key "email"
"""
#DONE
@app.route('/api/register', methods = ['POST'])
def add_user():
    cursor = get_username_db().cursor()
    cursor.execute('''select user_id from id where username="''' + str(request.authorization["username"]) + '''"''')
    user_id = cursor.fetchone()
    email = request.form.get("email")
    if user_id != None:
        return jsonify({"message": "That username is already taken. Please try a different username."})
    elif email == None:
        return jsonify({"message": "There was no email for the user in the request body. Please add the user's \
         email in the 'email' form in the request body"})
    else:
        db = get_db()
        insert_user(db, str(request.authorization["username"]), str(email), str(request.authorization["password"]))
        m = "Success, user has been added."
        return jsonify({"message" : m})

#DONE
@app.route('/api/users/<username>', methods = ['GET'])
def get_user(username):
    db_array = get_db()
    results = []
    shard_server = int(get_user_id(username)) % 3
    user_rows = db_array[shard_server].execute('''SELECT * FROM user where username=?''', (username,))
    if user_rows is not None:
        for row in user_rows:
            key = user_rows.description
            results.append({key[0][0]: row[0], key[1][0]: row[1], key[2][0]: row[2], key[3][0]: row[3]})
    return jsonify({'user': results})


"""
API Route for getting users who username is followed by
Send a GET request to "/api/users/<username>/followers" (replacing <username> with desired username)
to get back all of the users following that user in a json.
"""
@app.route('/api/users/<username>/followers', methods = ['GET'])
def get_followers(username):
    user_id = get_user_id(username)
    if user_id is None:
        return jsonify({"status code" : "404"})
    cursor = get_db()[int(user_id) % 3].cursor()
    cursor.execute('''select who_id from follower where whom_id=?''', (user_id,))
    follower_ids = [dict((cursor.description[i][0], value)
             for i, value in enumerate(row)) for row in cursor.fetchall()]
    follower_names = []
    for i in range(len(follower_ids)):
        name = get_username(follower_ids[i].values()[0])
        follower_names.append(name)
    return_dict = {}
    for i in range(0, len(follower_names)):
        return_dict[str(i + 1)] = follower_names[i]
    return jsonify({"followers" : return_dict})

"""
API Route for getting users who username is following
end a GET request to "/api/users/<username>/following" (replacing <username> with desired username)
to get back all of the users that user is following in a json."""
@app.route('/api/users/<username>/following', methods = ['GET'])
def get_following(username):
    user_id = get_user_id(username)
    if user_id is None:
        return jsonify({"status code" : "404"})
    cursor = get_db()[int(user_id) % 3].cursor()
    cursor.execute('''select whom_id from follower where who_id=?''', (user_id,))
    follower_ids = [dict((cursor.description[i][0], value)
              for i, value in enumerate(row)) for row in cursor.fetchall()]
    follower_names = []
    for i in range(len(follower_ids)):
        name = get_username(follower_ids[i].values()[0])
        follower_names.append(name)
    return_dict = {}
    for i in range(0, len(follower_names)):
        return_dict[str(i + 1)] = follower_names[i]
    return jsonify({"following" : return_dict})

"""
API Route for posting
This route requires authentication, the fields must be filled out accordingly in the request.
In the request body, put the desired text of the post under the "message" form.
"""
@app.route('/api/users/<username>/post', methods = ['POST'])
@basic_auth.required
def insert_message(username):
    post_message = request.form.get("message")
    if post_message == None:
        return jsonify({"Error" : "There was no message in the request body."
                                  " Please add what you would like to post under"
                                  " the 'message' form in the request body"})
    if request.authorization["username"] == username:
        db = get_db()
        populate_message(db, username, post_message, time.time())
        m = "Success, you've made a post."
        return jsonify({"message" : m})
    else:
        return jsonify({"status code" : "403 Forbidden: You cannot post to a user that isn't you"})

"""
API route for getting a users Dashboard (Timeline of followed users)
This route requires authentication, the fields must be filled out accordingly in the request.
Sending a GET request returns the dashboard for that user, which is all the messages of all the
users that the authenticated user follows.
"""
@app.route('/api/users/<username>/dashboard', methods = ['GET'])
@basic_auth.required
def get_dash(username):
    if request.authorization["username"] == username:
    db_array = get_db()
    user_id = get_user_id(username)
    followers_list = []
    for db in db_array:
        server_followers = db.execute('''SELECT who_id FROM follower WHERE whom_id = ?''', [user_id])
        for follower in server_followers:
            followers_list.append(follower[0])
    follower_messages = []
    for follower_id in followers_list:
        for db in db_array:
            messages = db.execute('''SELECT message.author_id, message.message_id, message.pub_date,
             message.text, user.username FROM message, user WHERE message.author_id=? 
             AND user.user_id=?''', (follower_id, follower_id))
            if messages is not None:
                for row in messages:
                    key = messages.description
                    follower_messages.append({key[4][0]: row[4], key[3][0]: row[3],
                                              key[2][0]: row[2], key[1][0]: row[1],
                                              key[0][0]: row[0]})
    follower_messages = sorted(follower_messages, key=lambda k: k['pub_date'])
    return jsonify({'dashboard': follower_messages})

"""
Route for Api Follow
This route requires authentication, the fields must be filled out accordingly in the request.
Sending an authenticated POST request to this endpoint makes the follower user follow the followee user.
Ex.
/api/users/Daniel/follow/Kaz
With authenticated Daniel login would make the user Daniel follow the user Kaz
"""
@app.route('/api/users/<follower>/follow/<followee>', methods = ['POST'])
@basic_auth.required
def api_follow(follower, followee):
    follower_id = get_user_id(follower)
    followee_id = get_user_id(followee)
    if request.authorization["username"] == follower:
       if follower_id == followee_id:
           return jsonify({"Error" : "You can't follow yourself"})
       if followee_id is None or follower_id is None:
           return jsonify({"status code" : "404: User not found."})
       db_array = get_db()
       shard_server = int(follower_id) % 3
       db = db_array[shard_server]
       db.execute('''INSERT INTO follower (who_id, whom_id) VALUES(?, ?)''', (follower_id, follower_id))
       m = "Success, you unfollowed " + followee
       return jsonify({"message": m})
    else:
        return jsonify({"status code": "403 Forbidden: You're trying to make someone who isn't you unfollow someone else."})
"""
Route for Api Unfollow
This route requires authentication, the fields must be filled out accordingly in the request.
Sending an authenticated DELETE request to this endpoint makes the follower user unfollow the followee user.
Ex.
/api/users/Daniel/follow/Kaz
With authenticated Daniel login would make the user Daniel unfollow the user Kaz
"""
@app.route('/api/users/<follower>/unfollow/<followee>', methods = ['DELETE'])
@basic_auth.required
def api_unfollow(follower, followee):
    follower_id = get_user_id(follower)
    followee_id = get_user_id(followee)
    if request.authorization["username"] == follower:
        if follower_id == followee_id:
            return jsonify({"Error" : "You can't unfollow yourself"})
        if follower_id is None or followee_id is None:
            return jsonify({"status code" : "404: User not found."})
        db_array = get_db()
        shard_server = int(follower_id) % 3
        db = db_array[shard_server]
        db.execute('''DELETE FROM follower WHERE who_id = ? AND whom_id = ?''', [follower_id, followee_id])
        db.commit()
        m = "Success, you unfollowed " + followee
        return jsonify({"message" : m})
    else:
        return jsonify({"status code" : "403 Forbidden: You're trying to make someone who isn't you unfollow someone else."})
