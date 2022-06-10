#!flask/bin/python
#
# DPO QC System for Digitization Projects
#
#
# Import flask
from flask import Flask
from flask import Response
from flask import render_template
from flask import request
from flask import jsonify
# from flask import session
from flask import redirect
from flask import url_for

import logging
import locale
import simplejson as json
# from psycopg2.extensions import AsIs
import os

import psycopg2
import psycopg2.extras
from flask_login import LoginManager
from flask_login import login_required
from flask_login import login_user
from flask_login import logout_user
from flask_login import UserMixin
from flask_login import current_user

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField
from wtforms.validators import DataRequired

import settings

site_ver = "0.1"

cur_path = os.path.abspath(os.getcwd())

# Logging
logging.basicConfig(filename='app.log',
                    level=logging.DEBUG,
                    filemode='a',
                    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                    datefmt='%y-%m-%d %H:%M:%S'
                    )
# define a Handler which writes INFO messages or higher to the sys.stderr
console = logging.StreamHandler()
console.setLevel(logging.INFO)
# set a format which is simpler for console use
formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
# tell the handler to use this format
console.setFormatter(formatter)
# add the handler to the root logger
logging.getLogger('').addHandler(console)
# Set locale for number format
locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')

app = Flask(__name__)
app.secret_key = b'a40dceb6ed968dc4263a20e9107b4532eeff613875dbb7982d09aeaa37a5e6bb'


# From http://flask.pocoo.org/docs/1.0/patterns/apierrors/
class InvalidUsage(Exception):
    status_code = 400

    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['error'] = self.message
        return rv


@app.errorhandler(InvalidUsage)
def handle_invalid_usage(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response


@app.errorhandler(404)
def page_not_found(e):
    logging.error(e)
    data = json.dumps({'error': "route not found"})
    return Response(data, mimetype='application/json'), 404


@app.errorhandler(500)
def page_not_found(e):
    logging.error(e)
    data = json.dumps({'error': "system error"})
    return Response(data, mimetype='application/json'), 500


# Needed for OpenRefine
# Based on https://github.com/mphilli/AAT-reconcile
def jsonpify(obj):
    """
    Like jsonify but wraps result in a JSONP callback if a 'callback'
    query param is supplied.
    """
    try:
        callback = request.args['callback']
        response = app.make_response("%s(%s)" % (callback, json.dumps(obj)))
        response.mimetype = "text/javascript"
        return response
    except KeyError:
        return jsonify(obj)


def preprocess(token):
    tokens = token.split(" ")
    for i, t in enumerate(tokens):
        if ")" in t or "(" in t:
            tokens[i] = ''
    token = " ".join(tokens)
    if token.endswith("."):
        token = token[:-1]
    return token.lower().lstrip().rstrip()


def query_database(query, parameters=""):
    try:
        conn = psycopg2.connect(host=settings.host,
                                    database=settings.database,
                                    user=settings.user,
                                    password=settings.password)
    except psycopg2.Error as e:
        logging.error(e)
        raise InvalidUsage('System error', status_code=500)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    logging.info("parameters: {}".format(parameters))
    logging.info("query: {}".format(query))
    # Run query
    try:
        cur.execute(query, parameters)
        logging.info("cur.query: {}".format(cur.query))
    except:
        logging.error("cur.query: {}".format(cur.query))
    logging.info(cur.rowcount)
    if cur.rowcount == -1:
        data = None
    else:
        data = cur.fetchall()
    cur.close()
    conn.close()
    return data





class LoginForm(FlaskForm):
    username    = StringField  (u'Username'  , validators=[DataRequired()])
    password    = PasswordField(u'Password'  , validators=[DataRequired()])


login_manager = LoginManager()
login_manager.init_app(app)


class User(UserMixin):
    def __init__(self, name, id, active=True):
        self.name = name
        self.id = id
        self.active = active

    def is_active(self):
        user = query_database("SELECT user_active FROM qc_users WHERE username = %(username)s",
                              {'username': name})
        return user

    def is_anonymous(self):
        return False

    def is_authenticated(self):
        return True


@login_manager.user_loader
def load_user(username):
    u = query_database("SELECT username, user_id, user_active "
                       "FROM qc_users "
                       "WHERE username = %(username)s",
                        {'username': username})
    return User(u[0]['username'], u[0]['user_id'], u[0]['user_active'])


###################################
# System routes
###################################
@app.route('/', methods=['GET', 'POST'])
def login():
    """Main homepage for the system"""
    # Declare the login form
    form = LoginForm(request.form)

    # Flask message injected into the page, in case of any errors
    msg = None

    # check if both http method is POST and form is valid on submit
    if form.validate_on_submit():

        # assign form data to variables
        username = request.form.get('username', '', type=str)
        password = request.form.get('password', '', type=str)

        user = query_database("SELECT user_id, username, user_active FROM qc_users "
                              "WHERE username = %(username)s AND pass = MD5(%(password)s)",
                              {'username': username, 'password': password})

        if user:
            user_obj = User(user[0]['user_id'], user[0]['username'], user[0]['user_active'])
            login_user(user_obj)
            return redirect(url_for('qc'))
        else:
            msg = "Error, user not known or password was incorrect"
    return render_template('login.html', form=form, msg=msg, site_ver=site_ver)


@app.route('/qc', methods=['POST', 'GET'])
@login_required
def qc():
    """Search the whole system"""
    folder_id = request.values.get('folder_id')
    if folder_id is None:
        projects = query_database("select p.project_title, p.project_id, p.filecheck_link, json_agg(t) as "
                                  "folders "
                                  "from " 
                                  " (SELECT * FROM folders WHERE project_id IN  " 
                                  " (SELECT p.project_id FROM qc_projects p, qc_users u where p.user_id = "
                                  "p.user_id AND u.username = %(username)s) ORDER BY date "
                                  "DESC) t, "
                                  "projects p " 
                                  "     where t.project_id = p.project_id " 
                                  "group by p.project_title, p.project_id " 
                                  "ORDER BY p.projects_order DESC",
                                  {'username': current_user.name})
    else:
        fld = query_database("UPDATE folders SET qc_status = 0, qc_by = %(qc_by)s, qc_date = NOW(), qc_ip = %(qc_ip)s "
                             "WHERE folder_id = %(folder_id)s RETURNING folder_id",
                             {'qc_by': current_user.name, 'qc_ip': request.environ['REMOTE_ADDR'], 'folder_id':
                                 folder_id})
        return redirect(url_for('qc'))
    return render_template('qc.html', project_list=projects, site_ver=site_ver, user_name=current_user.name)


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('login'))


# @app.route('/login', methods=['GET', 'POST'])
# def login():
#     # Declare the login form
#     form = LoginForm(request.form)
#
#     # Flask message injected into the page, in case of any errors
#     msg = None
#
#     # check if both http method is POST and form is valid on submit
#     if form.validate_on_submit():
#
#         # assign form data to variables
#         username = request.form.get('username', '', type=str)
#         password = request.form.get('password', '', type=str)
#
#         user = query_database("SELECT user_id, username, user_active FROM qc_users "
#                               "WHERE username = %(username)s AND pass = MD5(%(password)s)",
#                        {'username': username, 'password': password})
#
#         if user:
#             user_obj = User(user[0]['user_id'], user[0]['username'], user[0]['user_active'])
#             login_user(user_obj)
#             return redirect(url_for('qc'))
#         else:
#             msg = "Error, user not known or password was incorrect"
#     return render_template('login.html', form=form, msg=msg)


#####################################
if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
