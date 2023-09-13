#!flask/bin/python
#
# DPO Osprey Dashboard
#
# Import flask
from flask import Flask
from flask import render_template
from flask import request
from flask import jsonify
from flask import redirect
from flask import url_for
from flask import send_file

# caching
from flask_caching import Cache

import logging
import locale
import os
import math
import pandas as pd
import json
import time
from uuid import UUID

# MySQL
import pymysql

from flask_login import LoginManager
from flask_login import login_required
from flask_login import login_user
from flask_login import logout_user
from flask_login import UserMixin
from flask_login import current_user

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField
from wtforms.validators import DataRequired

from datetime import datetime
from PIL import Image

# Plotly
import plotly
import plotly.express as px

import settings

# Profile app
# from werkzeug.middleware.profiler import ProfilerMiddleware


site_ver = "2.6.0"
site_env = settings.env
site_net = settings.site_net

cur_path = os.path.abspath(os.getcwd())

# Logging
current_time = time.strftime("%Y%m%d_%H%M%S", time.localtime())
logfile = '{}/app_{}.log'.format(settings.log_folder, current_time)
logging.basicConfig(filename=logfile, filemode='a', level=logging.DEBUG,
                    format='%(levelname)s | %(asctime)s | %(filename)s:%(lineno)s | %(message)s',
                    datefmt='%y-%b-%d %H:%M:%S')
logger = logging.getLogger("web_osprey")

logging.info("site_ver = {}".format(site_ver))
logging.info("site_env = {}".format(site_env))
logging.info("site_net = {}".format(site_net))


# Set locale for number format
locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')


# Remove DecompressionBombWarning due to large files
# by using a large threshold
# https://github.com/zimeon/iiif/issues/11
Image.MAX_IMAGE_PIXELS = 1000000000


# Cache config
config = {
    "DEBUG": True,  # some Flask specific configs
    "CACHE_TYPE": "FileSystemCache",  # Flask-Caching related configs
    "CACHE_DIR": "{}/cache".format(os.getcwd()),
    "CACHE_DEFAULT_TIMEOUT": 60
}
app = Flask(__name__)
app.secret_key = settings.secret_key
app.config.from_mapping(config)
cache = Cache(app)
# app.wsgi_app = ProfilerMiddleware(app.wsgi_app, profile_dir="profile", restrictions=('app.py',))



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
    error_msg = "Error: {}".format(e)
    # Declare the login form
    form = LoginForm(request.form)
    return render_template('error.html', form=form, error_msg=error_msg, project_alias=None, site_env=site_env), 404


@app.errorhandler(500)
def sys_error(e):
    logging.error(e)
    error_msg = "System error: {}".format(e)
    # Declare the login form
    form = LoginForm(request.form)
    return render_template('error.html', form=form, error_msg=error_msg, project_alias=None, site_env=site_env), 500


def validate_api_key(api_key, cur=None):
    logging.info("api_key: {}".format(api_key))
    try:
        api_key_check = UUID(api_key)
    except ValueError:
        logging.info("Invalid UUID: {}".format(api_key))
        return False
    # Run query
    query = ("SELECT api_key from api_keys WHERE api_key = %(api_key)s")
    parameters = {'api_key': api_key}
    logging.info("query: {}".format(query))
    logging.info("parameters: {}".format(parameters))
    result = cur.execute(query, parameters)
    data = cur.fetchall()
    if len(data) == 1:
        if data[0]['api_key'] == api_key:
            return True
        else:
            return False
    else:
        return False


def run_query(query, parameters=None, api=False, return_val=True, cur=None):
    logging.info("parameters: {}".format(parameters))
    logging.info("query: {}".format(query))
    # Run query
    try:
        if parameters is None:
            results = cur.execute(query)
        else:
            results = cur.execute(query, parameters)
    except pymysql.Error as error:
        logging.error("Error: {}".format(error))
        if api:
            return jsonify(None)
        else:
            raise InvalidUsage(error, status_code=500)
    if return_val:
        data = cur.fetchall()
        logging.info("No of results: ".format(len(data)))
        return data
    else:
        return True


def query_database_insert(query, parameters, return_res=False, cur=None):
    logging.info("query: {}".format(query))
    logging.info("parameters: {}".format(parameters))
    # Run query
    data = False
    try:
        results = cur.execute(query, parameters)
    except Exception as error:
        logging.error("Error: {}".format(error))
        return False
    data = cur.fetchall()
    logging.info("No of results: ".format(len(data)))
    if len(data) == 0:
        data = False
    return data


def query_database_insert_multi(query, parameters, return_res=False, cur=None):
    logging.info("query: {}".format(query))
    logging.info("parameters: {}".format(parameters))
    # Run query
    data = False
    try:
        results = cur.executemany(query, parameters)
    except Exception as error:
        logging.error("Error_insert_multi: {}".format(error))
        return False
    data = cur.fetchall()
    logging.info("No of results: ".format(len(data)))
    if len(data) == 0:
        data = False
    return data


@cache.memoize()
def project_alias_exists(project_alias=None, cur=None):
    if project_alias is None:
        return False
    else:
        project_id = run_query("SELECT project_id FROM projects WHERE project_alias = %(project_alias)s",
                                    {'project_alias': project_alias}, cur=cur)
        if len(project_id) == 0:
            return False
        else:
            return project_id[0]['project_id']


def check_file_id(file_id=None, cur=None):
    if file_id is None:
        return False, False
    if cur is None:
        return False, False
    else:
        try:
            file_id = int(file_id)
            file_id_type = "int"
        except ValueError:
            try:
                file_uid = UUID(file_id, version=4)
                file_id_type = "uuid"
            except ValueError:
                return False, False

    if file_id_type == "uuid":
        file_id = run_query("SELECT file_id FROM files WHERE uid = %(uid)s", {'uid': file_uid}, cur=cur)
        if len(file_id) == 0:
            return False, False
        else:
            return file_id[0]['file_id'], file_uid
    else:
        file_uid = run_query("SELECT uid FROM files WHERE file_id = %(file_id)s", {'file_id': file_id}, cur=cur)
        if len(file_uid) == 0:
            return False, False
        else:
            return file_id, file_uid[0]['uid']


@cache.memoize()
def user_perms(project_id, user_type='user'):
    try:
        user_name = current_user.name
    except:
        return False
    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logging.error(e)
        raise InvalidUsage('System error')
    val = False
    if user_type == 'user':
        query = ("SELECT COUNT(*) as is_user FROM qc_projects p, users u "
                 " WHERE p.user_id = u.user_id AND p.project_id = %(project_id)s AND u.username = %(user_name)s")
        is_user = run_query(query, {'project_id': project_id, 'user_name': user_name}, cur=cur)
        val = is_user[0]['is_user'] == 1
    if user_type == 'admin':
        query = "SELECT is_admin FROM users WHERE username = %(user_name)s"
        is_admin = run_query(query, {'user_name': user_name}, cur=cur)
        val = is_admin[0]['is_admin'] == 1
    cur.close()
    conn.close()
    return val


class LoginForm(FlaskForm):
    username = StringField(u'Username', validators=[DataRequired()])
    password = PasswordField(u'Password', validators=[DataRequired()])


login_manager = LoginManager()
login_manager.init_app(app)


class User(UserMixin):
    def __init__(self, name, id, full_name, active=True):
        self.name = name
        self.id = id
        self.full_name = full_name
        self.active = active

    def is_active(self):
        # Connect to db
        try:
            conn = pymysql.connect(host=settings.host,
                                   user=settings.user,
                                   passwd=settings.password,
                                   database=settings.database,
                                   port=settings.port,
                                   charset='utf8mb4',
                                   cursorclass=pymysql.cursors.DictCursor,
                                   autocommit=True)
            cur = conn.cursor()
        except pymysql.Error as e:
            logging.error(e)
            raise InvalidUsage('System error')
        query = "SELECT user_active FROM users WHERE username = %(username)s"
        user = cur.execute(query, {'username': name})
        cur.close()
        conn.close()
        return user

    def is_anonymous(self):
        return False

    def is_authenticated(self):
        return True


@login_manager.user_loader
def load_user(username):
    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logging.error(e)
        raise InvalidUsage('System error')
    query = "SELECT username, user_id, user_active, full_name FROM users WHERE username = %(username)s"
    res = cur.execute(query, {'username': username})
    u = cur.fetchall()
    cur.close()
    conn.close()
    if len(u) == 1:
        return User(u[0]['username'], u[0]['user_id'], u[0]['full_name'], u[0]['user_active'])
    else:
        return User(None, None, None, False)


@cache.memoize()
def kiosk_mode(request, kiosks):
    # User IP, for kiosk mode
    request_address = request.remote_addr
    if request_address in kiosks:
        return True, request_address
    else:
        return False, request_address


###################################
# System routes
###################################
@cache.memoize()
@app.route('/team/<team>', methods=['GET', 'POST'], strict_slashes=False)
@app.route('/', methods=['GET', 'POST'], strict_slashes=False)
def login(team=None):
    """Main homepage for the system"""
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Declare the login form
    form = LoginForm(request.form)

    # Flask message injected into the page, in case of any errors
    msg = None

    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logging.error(e)
        raise InvalidUsage('System error')

    # check if both http method is POST and form is valid on submit
    if form.validate_on_submit():

        # assign form data to variables
        username = request.form.get('username', '', type=str)
        password = request.form.get('password', '', type=str)
        query = "SELECT user_id, username, user_active, full_name FROM users WHERE username = %(username)s AND pass = MD5(%(password)s)"
        user = run_query(query, {'username': username, 'password': password}, cur=cur)
        logging.info(user)
        if len(user) == 1:
            logging.info(user[0]['user_active'])
            if user[0]['user_active']:
                user_obj = User(user[0]['user_id'], user[0]['username'], user[0][
                    'full_name'],
                                user[0]['user_active'])
                login_user(user_obj)
                return redirect(url_for('home'))
            else:
                # msg = "Error, user not known or password was incorrect"
                return redirect(url_for('not_user'))
        else:
            # msg = "Error, user not known or password was incorrect"
            return redirect(url_for('not_user'))

    # Last update
    last_update = run_query("SELECT date_format(MAX(updated_at), '%d-%b-%Y') AS updated_at FROM projects_stats",
                            cur=cur)

    # Summary table
    # query = ("with d as ( "
    #          "   select stat_date, sum(images_captured) as images_captured, sum(objects_digitized) as objects_digitized "
    #          " from projects_stats_detail where time_interval ='monthly' group by stat_date) "
    #          " select date_format(d1.stat_date, '%b %Y') as Date, "
    #          "   sum(d1.images_captured) over (order by d1.stat_date asc rows between unbounded preceding and current row) as Images, "
    #          "   sum(d2.objects_digitized) over (order by d2.stat_date asc rows between unbounded preceding and current row) as Objects "
    #          " FROM d d1, d d2 "
    #          " WHERE d1.stat_date = d2.stat_date "
    #          " order by d1.stat_date DESC ")
    # df = pd.DataFrame(run_query(query, cur=cur))
    # df = df.rename(columns={"stat_date": "date"})
    # summary_datatable = pd.DataFrame(df)
    # columns = summary_datatable.columns
    # summary_datatable.columns = [x.title() for x in columns]

    if team is None:
        team = "summary"
        team_heading = "Summary Statistics for Collections Digitization"

        # Summary chart
        query = ("with d as ("
                 "   SELECT stat_date, sum(images_captured) as images_captured, sum(objects_digitized) as objects_digitized "
                 "     FROM projects_stats_detail where time_interval ='monthly' group by stat_date)"
                 "   SELECT stat_date, 'Images' as itype, "
                 "            sum(images_captured) over (order by stat_date asc rows between unbounded preceding and current row)  as no_images"
                 "          FROM d "
                 "         UNION "
                 "        SELECT stat_date, 'Objects' as itype,"
                 "        sum(objects_digitized) over (order by stat_date asc rows between unbounded preceding and current row) as no_images"
                 "      FROM d "
                 "     ORDER BY stat_date")
        df = pd.DataFrame(run_query(query, cur=cur))
        df = df.rename(columns={"stat_date": "date"})
        fig = px.line(df, x="date", y="no_images", color='itype',
                      labels=dict(date="Date", no_images="Cumulative Count", itype="Count"),
                      markers=True)
        fig.update_layout(legend=dict(
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01
        ))
        fig.update_layout(height=580)
        graphJSON_summary = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

        # Summary stats
        summary_stats = {
            'objects_digitized': "{:,}".format(run_query(("SELECT SUM(objects_digitized) as total "
                       " from projects_stats where project_id NOT IN (SELECT project_id FROM projects WHERE skip_project IS True)"),
                      cur=cur)[0]['total']),
            'images_captured': "{:,}".format(run_query(("SELECT SUM(images_taken) as total "
                     " from projects_stats where project_id NOT IN (SELECT project_id FROM projects WHERE skip_project IS True)"),
                    cur=cur)[0]['total']),
            'digitization_projects': "{:,}".format(
                     run_query(("SELECT COUNT(*) as total FROM projects WHERE skip_project IS NOT True"),
                        cur=cur)[0]['total']),
            'active_projects': "{:,}".format(run_query(("SELECT COUNT(*) as total "
                       " FROM projects WHERE skip_project IS NOT True AND project_status='Ongoing'"),
                      cur=cur)[0]['total']),
            'images_public': "{:,}".format(run_query(("SELECT SUM(images_public) as total "
                       " FROM projects_stats WHERE project_id NOT IN (SELECT project_id FROM projects WHERE skip_project IS True)"),
                      cur=cur)[0]['total'])
        }
    elif team == "md":
        graphJSON_summary = None
        team_heading = "Statistics of the Mass Digitization Team"
        # MD stats
        summary_stats = {
            'objects_digitized': "{:,}".format(run_query(
                    "SELECT SUM(objects_digitized) as total "
                    "from projects_stats where project_id IN "
                    "   (SELECT project_id FROM projects WHERE project_section = 'MD' AND skip_project IS NOT True)",
                        cur=cur)[0]['total']),
            'images_captured': "{:,}".format(run_query(
                "SELECT SUM(images_taken) as total "
                "from projects_stats WHERE project_id IN "
                "   (SELECT project_id FROM projects WHERE project_section = 'MD' AND skip_project IS NOT True)",
                cur=cur)[0]['total']),
            'digitization_projects': "{:,}".format(run_query(
                "SELECT COUNT(*) as total "
                "FROM projects WHERE project_section = 'MD' AND "
                " skip_project IS NOT True", cur=cur)[0]['total']),
            'active_projects': "{:,}".format(run_query(
                "SELECT COUNT(*) as total "
                "FROM projects WHERE project_section = 'MD' AND skip_project IS NOT True AND "
                " project_status='Ongoing'", cur=cur)[0]['total']),
            'images_public': "{:,}".format(run_query(("SELECT SUM(images_public) as total "
                      " FROM projects_stats WHERE project_id IN (SELECT project_id "
                      " FROM projects WHERE skip_project IS NOT True AND project_section = 'MD')"),
                     cur=cur)[0]['total'])
        }

    elif team == "is":
        graphJSON_summary = None
        team_heading = "Statistics of the Imaging Services Team"
        # IS stats
        summary_stats = {
            'objects_digitized': "{:,}".format(run_query(
                    "SELECT SUM(objects_digitized) as total "
                    "from projects_stats where project_id IN "
                    "   (SELECT project_id FROM projects WHERE project_section = 'IS' AND skip_project IS NOT True)",
                    cur=cur)[0]['total']),
            'images_captured': "{:,}".format(run_query(
                    "SELECT SUM(images_taken) as total "
                    "from projects_stats where project_id IN "
                    "   (SELECT project_id FROM projects WHERE project_section = 'IS' AND skip_project IS NOT True)",
                    cur=cur)[0]['total']),
            'digitization_projects': "{:,}".format(
                        run_query(
                            "SELECT COUNT(*) as total "
                            "FROM projects WHERE project_section = 'IS' AND "
                            " skip_project IS NOT True", cur=cur)[0]['total']),
            'active_projects': "{:,}".format(run_query(("SELECT COUNT(*) as total "
                            "FROM projects WHERE project_section = 'IS' AND "
                            " skip_project IS NOT True AND project_status='Ongoing'"),
                           cur=cur)[0]['total']),
            'images_public': "{:,}".format(run_query(("SELECT SUM(images_public) as total "
                          " FROM projects_stats WHERE project_id IN "
                          "   (SELECT project_id FROM projects WHERE skip_project IS NOT True AND project_section = 'IS')"),
                         cur=cur)[0]['total'])
        }

    elif team == "inf":
        graphJSON_summary = None
        team_heading = "Statistics of the Informatics Team"
        summary_stats = None

    section_query = (" SELECT "
                     " p.projects_order, "
                     " CONCAT('<abbr title=\"', u.unit_fullname, '\">', p.project_unit, '</abbr>') as project_unit, "
                     " CASE WHEN p.project_alias IS NULL THEN p.project_title ELSE CONCAT('<a href=\"/dashboard/', p.project_alias, '\">', p.project_title, '</a>') END as project_title, "
                     " p.project_status, "
                     " p.project_manager, "
                     " CASE WHEN date_format(p.project_start, '%%Y-%%c') = date_format(p.project_end, '%%Y-%%c') "
                     "       THEN CONCAT(date_format(p.project_start, '%%d'), '-', date_format(p.project_end, '%%d %%b %%Y')) "
                     "      WHEN p.project_end IS NULL THEN CONCAT(date_format(p.project_start, '%%d %%b %%Y'), ' -') "
                     "      ELSE CONCAT(date_format(p.project_start, '%%d %%b %%Y'), ' to ', date_format(p.project_end, '%%d %%b %%Y')) END"
                     "         as project_dates, "
                     " CASE WHEN p.objects_estimated IS True THEN CONCAT(coalesce(format(ps.objects_digitized, 0), 0), '*') ELSE "
                     " coalesce(format(ps.objects_digitized, 0), 0) END as objects_digitized, "
                     " CASE WHEN p.images_estimated IS True THEN CONCAT(coalesce(format(ps.images_taken, 0), 0), '*') ELSE coalesce(format(ps.images_taken, 0), 0) END as images_taken, "
                     " CASE WHEN p.images_estimated IS True THEN CONCAT(coalesce(format(ps.images_public, 0), 0), '*') ELSE coalesce(format(ps.images_public, 0), 0) END as images_public "
                     " FROM projects p LEFT JOIN projects_stats ps ON (p.project_id = ps.project_id) LEFT JOIN si_units u ON (p.project_unit = u.unit_id) "
                     " WHERE p.skip_project = 0 AND p.project_section = %(section)s "
                     " GROUP BY "
                     "        p.project_id, p.project_title, p.project_unit, p.project_status, p.project_description, "
                     "        p.project_method, p.project_manager, p.project_start, p.project_end, p.updated_at, p.projects_order, p.project_type, "
                     "        ps.collex_to_digitize, p.images_estimated, p.objects_estimated, ps.images_taken, ps.objects_digitized, ps.images_public"
                     " ORDER BY p.projects_order DESC")
    list_projects_md = pd.DataFrame(run_query(section_query, {'section': 'MD'}, cur=cur))
    list_projects_md = list_projects_md.rename(columns={
        "project_unit": "Unit",
        "project_title": "Title",
        "project_status": "Status",
        "project_manager": "PM",
        "project_dates": "Dates",
        "project_progress": "Project Progress<sup>*</sup>",
        "objects_digitized": "Objects Digitized",
        "images_taken": "Images Captured",
        "images_public": "Public Images"
    })

    list_projects_is = pd.DataFrame(run_query(section_query, {'section': 'IS'}, cur=cur))
    list_projects_is = list_projects_is.rename(columns={
        "project_unit": "Unit",
        "project_title": "Title",
        "project_status": "Status",
        "project_manager": "PM",
        "project_dates": "Dates",
        "project_progress": "Project Progress<sup>*</sup>",
        "objects_digitized": "Objects Digitized",
        "images_taken": "Images Captured",
        "images_public": "Public Images"
    })

    cur.close()
    conn.close()

    # kiosk mode
    kiosk, user_address = kiosk_mode(request, settings.kiosks)

    return render_template('home.html',
                           form=form,
                           msg=msg,
                           user_exists=user_exists,
                           username=username,
                           graphJSON_summary=graphJSON_summary,
                           summary_stats=summary_stats,
                           team=team,
                           tables_md=[list_projects_md.to_html(table_id='list_projects_md', index=False,
                                                               border=0, escape=False,
                                                               classes=["display", "table-striped",
                                                                        "w-100"])],
                           tables_is=[list_projects_is.to_html(table_id='list_projects_is', index=False,
                                                               border=0, escape=False,
                                                               classes=["display", "table-striped",
                                                                        "w-100"])],
                           asklogin=True,
                           site_env=site_env,
                           site_net=site_net,
                           last_update=last_update[0]['updated_at'],
                           kiosk=kiosk,
                           user_address=user_address,
                           team_heading=team_heading
                           )


@cache.memoize()
@app.route('/dashboard/<project_alias>/<folder_id>/', methods=['POST', 'GET'], strict_slashes=False)
def dashboard_f(project_alias=None, folder_id=None):
    """Dashboard for a project"""
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logging.error(e)
        raise InvalidUsage('System error')

    # Declare the login form
    form = LoginForm(request.form)

    # Check if project exists
    if project_alias_exists(project_alias, cur=cur) is False:
        error_msg = "Project was not found."
        return render_template('error.html', form=form, error_msg=error_msg,
                                project_alias=project_alias, site_env=site_env), 404

    project_id_check = run_query("SELECT project_id FROM projects WHERE project_alias = %(project_alias)s",
                                      {'project_alias': project_alias}, cur=cur)
    if len(project_id_check) == 0:
        error_msg = "Project was not found."
        return render_template('error.html', form=form, error_msg=error_msg,
                               project_alias=project_alias, site_env=site_env), 404
    else:
        project_id = project_id_check[0]['project_id']

    # Check if folder exists
    folder_check = run_query(
        ("SELECT folder_id FROM folders "
         " WHERE folder_id = %(folder_id)s AND project_id = %(project_id)s"),
        {'folder_id': folder_id, 'project_id': project_id}, cur=cur)
    if len(folder_check) == 0:
        error_msg = ("Folder was not found. It may have been deleted. "
                     "Please click the link below to go to the main page of the dashboard.")
        return render_template('error.html', form=form, error_msg=error_msg,
                               project_alias=project_alias, site_env=site_env), 404

    tab = request.values.get('tab')
    if tab is None or tab == '':
        tab = 0
    else:
        try:
            tab = int(tab)
        except:
            error_msg = "Invalid tab ID."
            return render_template('error.html', form=form, error_msg=error_msg,
                                   project_alias=project_alias, site_env=site_env), 400
    page = request.values.get('page')
    if page is None or page == '':
        page = 1
    else:
        try:
            page = int(page)
        except:
            error_msg = "Invalid page number."
            return render_template('error.html', form=form, error_msg=error_msg,
                                   project_alias=project_alias, site_env=site_env), 400
    project_stats = {}
    if project_alias is None:
        error_msg = "Project is not available."
        return render_template('error.html', form=form, error_msg=error_msg,
                               project_alias=project_alias, site_env=site_env), 404

    if current_user.is_authenticated:
        username = current_user.name
        project_admin = run_query(("SELECT count(*) as no_results FROM users u, qc_projects p "
                                        " WHERE u.username = %(username)s "
                                        " AND p.project_id = %(project_id)s "
                                        " AND u.user_id = p.user_id"),
                                       {'username': username, 'project_id': project_id}, cur=cur)[0]
        if project_admin['no_results'] > 0:
            project_admin = True
        else:
            project_admin = False
        logging.info("project_admin: {} - {}".format(username, project_admin))
    else:
        project_admin = False
    project_info = run_query("SELECT *, "
                             "      CONCAT(date_format(project_start, '%%d-%%b-%%Y'), "
                             "          CASE WHEN project_end IS NULL THEN '' ELSE CONCAT(' to ', date_format(project_end, '%%d-%%b-%%Y')) END "
                             "          ) as pdates "
                             " FROM projects WHERE project_alias = %(project_alias)s",
                                  {'project_alias': project_alias}, cur=cur)[0]

    project_managers = run_query("SELECT project_manager FROM projects WHERE project_alias = %(project_alias)s",
                                  {'project_alias': project_alias}, cur=cur)[0]

    project_manager_link = project_managers['project_manager']
    if project_managers['project_manager'] == "Jeanine Nault":
        project_manager_link = "<a href=\"https://dpo.si.edu/jeanine-nault\">Jeanine Nault</a>"
    elif project_managers['project_manager'] == "Nathan Ian Anderson":
        project_manager_link = "<a href=\"https://dpo.si.edu/nathan-ian-anderson\">Nathan Ian Anderson</a>"
    elif project_managers['project_manager'] == "Erin M. Mazzei":
        project_manager_link = "<a href=\"https://dpo.si.edu/erin-mazzei\">Erin M. Mazzei</a>"

    projects_links = run_query("SELECT * FROM projects_links WHERE project_id = %(project_id)s ORDER BY table_id",
                                  {'project_id': project_info['project_id']}, cur=cur)

    filechecks_list_temp = run_query(
        ("SELECT settings_value as file_check FROM projects_settings "
         " WHERE project_setting = 'project_checks' and project_id = %(project_id)s"),
        {'project_id': project_info['project_id']}, cur=cur)
    filechecks_list = []
    for fcheck in filechecks_list_temp:
        filechecks_list.append(fcheck['file_check'])
    logging.info("filechecks_list:{}".format(filechecks_list_temp))
    project_postprocessing_temp = run_query(
        ("SELECT settings_value as file_check FROM projects_settings "
         " WHERE project_setting = 'project_postprocessing' and project_id = %(project_id)s ORDER BY table_id"),
        {'project_id': project_info['project_id']}, cur=cur)
    project_postprocessing = []
    if project_postprocessing_temp is not None:
        for fcheck in project_postprocessing_temp:
            project_postprocessing.append(fcheck['file_check'])
    project_statistics = run_query(("SELECT * FROM projects_stats WHERE project_id = %(project_id)s"), {'project_id': project_id}, cur=cur)[0]
    # project_total = run_query(("SELECT count(*) as no_files "
    #                     "    FROM files WHERE folder_id IN "
    #                     "       (SELECT folder_id FROM folders WHERE project_id = %(project_id)s"
    #                     "   )"),
    #                     {'project_id': project_id}, cur=cur)
    project_stats['total'] = format(int(project_statistics['images_taken']), ',d')
    project_ok = run_query(("WITH "
                                 " folders_q as (SELECT folder_id from folders WHERE project_id = %(project_id)s),"
                                 " files_q as (SELECT file_id FROM files f, folders_q fol WHERE f.folder_id = fol.folder_id),"
                                 " checks as (select settings_value as file_check from projects_settings where project_setting = 'project_checks' AND project_id = %(project_id)s),"
                                 " checklist as (select c.file_check, f.file_id from checks c, files_q f),"
                                 " data AS ("
                                 "SELECT c.file_id, sum(coalesce(f.check_results, 9)) as check_results"
                                 " FROM"
                                 " checklist c left join files_checks f on (c.file_id = f.file_id and c.file_check = f.file_check)"
                                 " group by c.file_id)"
                                 "SELECT count(file_id) as no_files FROM data WHERE check_results = 0"),
                                {'project_id': project_id}, cur=cur)

    project_stats['ok'] = format(int(project_ok[0]['no_files']), ',d')
    project_err = run_query(("WITH "
                                  " folders_q as (SELECT folder_id from folders WHERE project_id = %(project_id)s),"
                                  " files_q as (SELECT file_id FROM files f, folders_q fol WHERE f.folder_id = fol.folder_id),"
                                  " checks as (select settings_value as file_check from projects_settings where project_setting = 'project_checks' AND project_id = %(project_id)s),"
                                  " checklist as (select c.file_check, f.file_id from checks c, files_q f),"
                                  " data AS ("
                                  "SELECT c.file_id, sum(coalesce(f.check_results, 9)) as check_results"
                                  " FROM"
                                  " checklist c left join files_checks f on (c.file_id = f.file_id and c.file_check = f.file_check)"
                                  "      WHERE check_results = 1"
                                  " group by c.file_id)"
                                  "SELECT count(file_id) as no_files FROM data WHERE check_results != 0"),
                                 {'project_id': project_id}, cur=cur)

    project_stats['errors'] = format(int(project_err[0]['no_files']), ',d')
    # project_pending = run_query(("WITH "
    #                                   " folders_q as (SELECT folder_id from folders WHERE project_id = %(project_id)s),"
    #                                   " files_q as (SELECT file_id FROM files f, folders_q fol WHERE f.folder_id = fol.folder_id),"
    #                                   " checks as (select settings_value as file_check from projects_settings where project_setting = 'project_checks' AND project_id = %(project_id)s),"
    #                                   " checklist as (select c.file_check, f.file_id from checks c, files_q f),"
    #                                   " data AS ("
    #                                   "SELECT c.file_id, coalesce(f.check_results, 9) as check_results"
    #                                   " FROM"
    #                                   " checklist c left join files_checks f on (c.file_id = f.file_id and c.file_check = f.file_check))"
    #                                   " SELECT count(distinct file_id) as no_files FROM data where check_results = 9"),
    #                                  {'project_id': project_id}, cur=cur)
    # project_stats['pending'] = format(int(project_pending[0]['no_files']), ',d')
    # project_public = run_query(("SELECT COALESCE(images_public, 0) as no_files FROM projects_stats WHERE "
    #                                  " project_id = %(project_id)s"),
    #                                 {'project_id': project_id}, cur=cur)
    # project_stats['public'] = format(int(project_public[0]['no_files']), ',d')

    project_folders = run_query(("SELECT f.project_folder, f.folder_id, coalesce(b1.badge_text, concat(0, ' files')) as no_files, "
                                      "f.file_errors, f.status, f.error_info, "
                                      "f.delivered_to_dams, "
                                      " COALESCE(CASE WHEN qcf.qc_status = 0 THEN 'QC Passed' "
                                      "              WHEN qcf.qc_status = 1 THEN 'QC Failed' "
                                      "              WHEN qcf.qc_status = 9 THEN 'QC Pending' END,"
                                      "          'QC Pending') as qc_status,"
                                      "   b.badge_text "
                                      "FROM folders f "
                                      "     LEFT JOIN qc_folders qcf ON (f.folder_id = qcf.folder_id) "
                                      "     LEFT JOIN folders_badges b ON (f.folder_id = b.folder_id AND b.badge_type = 'verification') "
                                      "     LEFT JOIN folders_badges b1 ON (f.folder_id = b1.folder_id AND b1.badge_type = 'no_files') "
                                      " WHERE f.project_id = %(project_id)s "
                                      " ORDER BY f.date DESC, f.project_folder DESC"),
                                     {'project_id': project_id}, cur=cur)

    # Get objects
    proj_obj = run_query(("SELECT COALESCE(objects_digitized, 0) as no_objects FROM projects_stats WHERE "
                          " project_id = %(project_id)s"),
                         {'project_id': project_id}, cur=cur)
    project_stats['objects'] = format(int(proj_obj[0]['no_objects']), ',d')

    project_folders_badges = run_query("SELECT b.folder_id, b.badge_type, b.badge_css, b.badge_text FROM folders_badges b, folders f WHERE b.folder_id = f.folder_id and f.project_id = %(project_id)s and b.badge_type != 'no_files'", {'project_id': project_id}, cur=cur)
    folder_name = None
    folder_qc = {
        'qc_status': "QC Pending",
        'qc_by': "",
        'updated_at': "",
        'qc_ip': ""
    }
    if folder_id is not None and folder_id != '':
        folder_name = run_query(("SELECT project_folder FROM folders "
                                 "WHERE folder_id = %(folder_id)s and project_id = %(project_id)s"),
                                     {'folder_id': folder_id, 'project_id': project_id}, cur=cur)
        logging.info("folder_name: {}".format(len(folder_name)))
        if len(folder_name) == 0:
            error_msg = "Folder does not exist in this project."
            return render_template('error.html', form=form, error_msg=error_msg, project_alias=project_alias,
                                   site_env=site_env), 404
        else:
            folder_name = folder_name[0]
        folder_files_df = pd.DataFrame(
            run_query("SELECT file_id, file_name FROM files WHERE folder_id = %(folder_id)s",
                           {'folder_id': folder_id}, cur=cur))
        no_items = 25
        if page == 1:
            offset = 0
        else:
            offset = (page - 1) * no_items
        files_df = run_query((
                          "WITH data AS (SELECT file_id, COALESCE(preview_image, CONCAT('/preview_image/', file_id, '/?')) as preview_image, "
                          "         folder_id, file_name FROM files "
                          "WHERE folder_id = %(folder_id)s)"
                          " SELECT file_id, preview_image, folder_id, file_name"
                          " FROM data "
                          " ORDER BY file_name "
                          "LIMIT {no_items} OFFSET {offset}").format(offset=offset, no_items=no_items),
                          {'folder_id': folder_id}, cur=cur)
        files_count = run_query("SELECT count(*) as no_files FROM files WHERE folder_id = %(folder_id)s",
                                     {'folder_id': folder_id}, cur=cur)[0]
        files_count = files_count['no_files']
        if files_count == 0:
            folder_files_df = pd.DataFrame()
            pagination_html = ""
            files_df = ""
            files_count = ""
            folder_stats = {
                'no_files': 0,
                'no_errors': 0
            }
            post_processing_df = pd.DataFrame()
        else:
            for fcheck in filechecks_list:
                logging.info("fcheck: {}".format(fcheck))
                list_files = pd.DataFrame(run_query(("SELECT f.file_id, "
                                                          "   CASE WHEN check_results = 0 THEN 'OK' "
                                                          "       WHEN check_results = 9 THEN 'Pending' "
                                                          "       WHEN check_results = 1 THEN 'Failed' "
                                                          "       ELSE 'Pending' END as {fcheck} "
                                                          " FROM files f LEFT JOIN files_checks c ON (f.file_id=c.file_id AND c.file_check = %(file_check)s) "
                                                          "  where f.folder_id = %(folder_id)s").format(fcheck=fcheck),
                                                         {'file_check': fcheck, 'folder_id': folder_id}, cur=cur))
                logging.info("list_files.size: {}".format(list_files.shape[0]))
                if list_files.shape[0] > 0:
                    folder_files_df = folder_files_df.merge(list_files, how='outer', on='file_id')
            preview_files = pd.DataFrame(run_query(("SELECT f.file_id, "
                                                         "  COALESCE(f.preview_image, CONCAT('/preview_image/', f.file_id, '/?')) as preview_image "
                                                         " FROM files f where f.folder_id = %(folder_id)s"),
                                                        {'folder_id': folder_id}, cur=cur))
            folder_files_df = folder_files_df.sort_values(by=['file_name'])
            folder_files_df = folder_files_df.sort_values(by=filechecks_list)
            folder_files_df = folder_files_df.merge(preview_files, how='outer', on='file_id')
            folder_files_df['file_name'] = '<a href="/file/' \
                                           + folder_files_df['file_id'].astype(str) + '/" title="File Details">' \
                                           + folder_files_df['file_name'].astype(str) \
                                           + '</a> ' \
                                           + '<button type="button" class="btn btn-light btn-sm" ' \
                                           + 'data-bs-toggle="modal" data-bs-target="#previewmodal1" ' \
                                           + 'data-bs-info="' + folder_files_df['preview_image'] \
                                           + '" data-bs-link = "/file/' + folder_files_df['file_id'].astype(str) \
                                           + '" data-bs-text = "Details of the file ' + folder_files_df[
                                               'file_name'].astype(str) \
                                           + '" title="Image Preview">' \
                                           + '<i class="fa-regular fa-image"></i></button>'
            folder_files_df = folder_files_df.drop(['file_id'], axis=1)
            folder_files_df = folder_files_df.drop(['preview_image'], axis=1)
            # Pagination
            pagination_html = "<nav aria-label=\"pages\"><ul class=\"pagination float-end\">"
            no_pages = math.ceil(files_count / no_items)
            logging.info("no_pages: {}".format(no_pages))
            if page == 1:
                pagination_html = pagination_html + "<li class=\"page-item disabled\"><a class=\"page-link\" href=\"#\" " \
                                                    "tabindex=\"-1\">Previous</a></li>"
            else:
                pagination_html = pagination_html + "<li class=\"page-item\"><a class=\"page-link\" " \
                                                    "href=\"" + url_for('dashboard_f', project_alias=project_alias,
                                                                        folder_id=folder_id) \
                                  + "?tab=1&page={}\">Previous</a></li>".format(page - 1)
            # Ellipsis for first pages
            if page > 5:
                pagination_html = pagination_html + "<li class=\"page-item\"><a class=\"page-link\" " \
                                  + "href=\"" + url_for('dashboard_f', project_alias=project_alias, folder_id=folder_id) \
                                  + "?tab=1&page=1\">1</a></li>"
                pagination_html = pagination_html + "<li class=\"page-item disabled\"><a class=\"page-link\" " \
                                                    "href=\"#\">...</a></li>"
            for i in range(1, no_pages + 1):
                if ((page - i) < 4) and ((i - page) < 4):
                    if i == page:
                        pagination_html = pagination_html + "<li class=\"page-item active\">"
                    else:
                        pagination_html = pagination_html + "<li class=\"page-item\">"
                    pagination_html = pagination_html + "<a class=\"page-link\" " \
                                      + "href=\"" \
                                      + url_for('dashboard_f', project_alias=project_alias, folder_id=folder_id) \
                                      + "?tab=1&page={}\">{}</a>".format(i, i) \
                                      + "</li>"
            if (no_pages - page) > 4:
                pagination_html = pagination_html + "<li class=\"page-item disabled\"><a class=\"page-link\" " \
                                                    "href=\"#\">...</a></li>"
                pagination_html = pagination_html + "<li class=\"page-item\"><a class=\"page-link\" " \
                                  + "href=\"" + url_for('dashboard_f', project_alias=project_alias, folder_id=folder_id) \
                                  + "?tab=1&page={last}\">{last}</a></li>".format(last=no_pages)
            if page == no_pages:
                pagination_html = pagination_html + "<li class=\"page-item disabled\"><a class=\"page-link\" " \
                                                    "href=\"#\">Next</a></li>"
            else:
                if no_pages == 0:
                    pagination_html = pagination_html + "<li class=\"page-item disabled\"><a class=\"page-link\" " \
                                                        "href=\"#\">Next</a></li>"
                else:
                    pagination_html = pagination_html + "<li class=\"page-item\"><a class=\"page-link\" " \
                                      + "href=\"" + url_for('dashboard_f', project_alias=project_alias,
                                                            folder_id=folder_id) \
                                      + "?tab=1&page={}\">".format(page + 1) \
                                      + "Next</a></li>"
            pagination_html = pagination_html + "</ul></nav>"
            folder_stats1 = run_query(("SELECT coalesce(f.no_files, 0) as no_files "
                                            " FROM folders f WHERE folder_id = %(folder_id)s"),
                                           {'folder_id': folder_id}, cur=cur)
            folder_stats2 = run_query(("SELECT count(DISTINCT c.file_id) as no_errors "
                                            " FROM files_checks c WHERE file_id IN (SELECT file_id from files WHERE"
                                            "   folder_id = %(folder_id)s) AND check_results = 1"),
                                           {'folder_id': folder_id}, cur=cur)
            folder_stats = {
                'no_files': folder_stats1[0]['no_files'],
                'no_errors': folder_stats2[0]['no_errors']
            }
            post_processing_df = pd.DataFrame(run_query(("SELECT file_id, file_name FROM files "
                                                  " WHERE folder_id = %(folder_id)s ORDER BY file_name"),
                                                 {'folder_id': folder_id}, cur=cur))
            logging.info("project_postprocessing {}".format(project_info['project_postprocessing']))
            post_processing_df['file_name'] = '<a href="/file/' \
                                              + post_processing_df['file_id'].astype(str) + '/" title="File Details">' \
                                              + post_processing_df['file_name'].astype(str) \
                                              + '</a>'
            if len(project_postprocessing) > 0:
                for fcheck in project_postprocessing:
                    logging.info("fcheck: {}".format(fcheck))
                    list_files = pd.DataFrame(run_query(("SELECT f.file_id, "
                                                              "   CASE WHEN post_step = 0 THEN 'Completed' "
                                                              "       WHEN post_step = 9 THEN 'Pending' "
                                                              "       WHEN post_step = 1 THEN 'Failed' "
                                                              "       ELSE 'Pending' END as {fcheck} "
                                                              " FROM files f LEFT JOIN file_postprocessing c ON (f.file_id=c.file_id AND c.post_step = %(file_check)s) "
                                                              "  where f.folder_id = %(folder_id)s").format(
                        fcheck=fcheck),
                                                             {'file_check': fcheck, 'folder_id': folder_id}, cur=cur))
                    logging.info("list_files.size: {}".format(list_files.shape[0]))
                    if list_files.shape[0] > 0:
                        post_processing_df = post_processing_df.merge(list_files, how='outer', on='file_id')
                post_processing_df = post_processing_df.drop(['file_id'], axis=1)
            else:
                post_processing_df = pd.DataFrame()
    else:
        folder_files_df = pd.DataFrame()
        pagination_html = ""
        files_df = ""
        files_count = ""
        folder_stats = {
            'no_files': 0,
            'no_errors': 0
        }
        post_processing_df = pd.DataFrame()
    if current_user.is_authenticated:
        user_name = current_user.name
        is_admin = user_perms('', user_type='admin')
    else:
        user_name = ""
        is_admin = False
    folder_links = run_query("SELECT * FROM folders_links WHERE folder_id = %(folder_id)s",
                                  {'folder_id': folder_id}, cur=cur)
    logging.info("folder_links: {}".format(folder_links))

    # Reports
    reports = run_query("SELECT * FROM data_reports WHERE project_id = %(project_id)s ORDER BY report_title_brief",
                             {'project_id': project_id}, cur=cur)

    if len(reports) > 0:
        proj_reports = True
    else:
        proj_reports = False

    # QC folder status
    qc_check = run_query("SELECT * FROM qc_folders WHERE folder_id = %(folder_id)s AND qc_status = 1",
                        {'folder_id': folder_id}, cur=cur)
    if len(qc_check) > 0:
        qc_check = True
        qc_details = pd.DataFrame(run_query(("SELECT f.file_id, f.file_name, q.qc_info, "
                                             "      CASE "
                                             "           WHEN q.file_qc = 1 THEN '<span class=\"badge bg-danger\">Critical Issue</span>'"
                                             "           WHEN q.file_qc = 2 THEN '<span class=\"badge bg-warning\">Major Issue</span>'"
                                             "           WHEN q.file_qc = 3 THEN '<span class=\"badge bg-warning\">Minor Issue</span>' END as file_qc "
                                             "FROM qc_files q, files f WHERE q.folder_id = %(folder_id)s and q.file_qc != 0 AND q.file_id = f.file_id "
                                             "ORDER BY q.file_qc DESC"),
                            {'folder_id': folder_id}, cur=cur))
        qc_details['file_name'] = '<a href="/file/' \
                                          + qc_details['file_id'].astype(str) + '/" title="File Details" target="_blank">' \
                                          + qc_details['file_name'].astype(str) \
                                          + '</a>'
        qc_details = qc_details.drop(['file_id'], axis=1)
    else:
        qc_check = False
        qc_details = pd.DataFrame()

    # Disk space
    project_disks = run_query(("SELECT FORMAT_BYTES(sum(filesize)) as filesize, UPPER(filetype) as filetype "
                               "    FROM files_size "
                               "    WHERE file_id IN (SELECT file_id from files WHERE folder_id IN (SELECT folder_id "
                               "                        FROM folders WHERE project_id = %(project_id)s)) GROUP BY filetype"),
                              {'project_id': project_id}, cur=cur)

    i = 0
    project_disk = "NA"
    for disk in project_disks:
        if i > 0:
            project_disk = "{} / {}: {}".format(project_disk, disk['filetype'], disk['filesize'])
        else:
            project_disk = "{}: {}".format(disk['filetype'], disk['filesize'])
        i += 1

    cur.close()
    conn.close()

    # kiosk mode
    kiosk, user_address = kiosk_mode(request, settings.kiosks)

    return render_template('dashboard.html',
                           project_id=project_id,
                           project_info=project_info,
                           project_alias=project_alias,
                           project_stats=project_stats,
                           project_folders=project_folders,
                           files_df=files_df,
                           folder_id=folder_id,
                           folder_name=folder_name,
                           tables=[folder_files_df.to_html(table_id='files_table',
                                                           index=False,
                                                           border=0,
                                                           escape=False,
                                                           classes=["display", "compact", "table-striped", "w-100"])],
                           titles=[''],
                           username=user_name,
                           project_admin=project_admin,
                           is_admin=is_admin,
                           tab=tab,
                           files_count=files_count,
                           pagination_html=pagination_html,
                           pagination_html2=pagination_html,
                           folder_stats=folder_stats,
                           post_processing=[post_processing_df.to_html(table_id='post_processing_table',
                                                                       index=False,
                                                                       border=0,
                                                                       escape=False,
                                                                       classes=["display", "compact", "table-striped",
                                                                                "w-100"])],
                           folder_links=folder_links,
                           project_folders_badges=project_folders_badges,
                           form=form,
                           proj_reports=proj_reports,
                           reports=reports,
                           site_env=site_env,
                           site_net=site_net,
                           kiosk=kiosk,
                           user_address=user_address,
                           qc_check=qc_check,
                           qc_details=[qc_details.to_html(table_id='qc_details_table',
                                                                       index=False,
                                                                       border=0,
                                                                       escape=False,
                                                                       classes=["display", "compact", "table-striped",
                                                                                "w-100"])],
                           project_disk=project_disk,
                           projects_links=projects_links,
                           project_manager_link=project_manager_link
                           )


@cache.memoize()
@app.route('/dashboard/<project_alias>/', methods=['GET', 'POST'], strict_slashes=False)
def dashboard(project_alias=None):
    """Dashboard for a project"""
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logging.error(e)
        raise InvalidUsage('System error')

    # Declare the login form
    form = LoginForm(request.form)

    project_stats = {}

    # Check if project exists
    project_id = project_alias_exists(project_alias, cur=cur)
    if project_id is False:
        error_msg = "Project was not found."
        return render_template('error.html', form=form, error_msg=error_msg, project_alias=project_alias,
                               site_env=site_env), 404

    logging.info("project_id: {}".format(project_id))
    logging.info("project_alias: {}".format(project_alias))
    if current_user.is_authenticated:
        username = current_user.name
        project_admin = run_query(("SELECT count(*) as no_results FROM users u, qc_projects p "
                                        " WHERE u.username = %(username)s "
                                        " AND p.project_id = %(project_id)s AND u.user_id = p.user_id"),
                                       {'username': username, 'project_id': project_id}, cur=cur)[0]
        if project_admin['no_results'] > 0:
            project_admin = True
        else:
            project_admin = False
        logging.info("project_admin: {} - {}".format(username, project_admin))
    else:
        project_admin = False
    project_info = run_query("SELECT *, CONCAT('https://dpo.si.edu/', lower(replace(project_manager, ' ', '-'))) as project_manager_link, "
                             "      CONCAT(date_format(project_start, '%%d-%%b-%%Y'), "
                             "          CASE WHEN project_end IS NULL THEN '' ELSE CONCAT(' to ', date_format(project_end, '%%d-%%b-%%Y')) END "
                             "          ) as pdates "
                             "   FROM projects WHERE project_id = %(project_id)s",
                                  {'project_id': project_id}, cur=cur)[0]

    project_managers = run_query("SELECT project_manager FROM projects WHERE project_alias = %(project_alias)s",
                                 {'project_alias': project_alias}, cur=cur)[0]

    project_manager_link = project_managers['project_manager']
    if project_managers['project_manager'] == "Jeanine Nault":
        project_manager_link = "<a href=\"https://dpo.si.edu/jeanine-nault\">Jeanine Nault</a>"
    elif project_managers['project_manager'] == "Nathan Ian Anderson":
        project_manager_link = "<a href=\"https://dpo.si.edu/nathan-ian-anderson\">Nathan Ian Anderson</a>"
    elif project_managers['project_manager'] == "Erin M. Mazzei":
        project_manager_link = "<a href=\"https://dpo.si.edu/erin-mazzei\">Erin M. Mazzei</a>"


    projects_links = run_query("SELECT * FROM projects_links WHERE project_id = %(project_id)s ORDER BY table_id",
                               {'project_id': project_info['project_id']}, cur=cur)

    try:
        filechecks_list = project_info['project_checks'].split(',')
    except:
        error_msg = "Project is not available."
        return render_template('error.html', form=form, error_msg=error_msg, project_alias=project_alias,
                               site_env=site_env), 404

    project_statistics = run_query(("SELECT COALESCE(images_taken, 0) as images_taken, COALESCE(objects_digitized, 0) as objects_digitized"
                                    "  FROM projects_stats WHERE project_id = %(project_id)s"),
                                   {'project_id': project_id}, cur=cur)[0]
    # project_total = run_query(("SELECT count(*) as no_files "
    #                                 "    FROM files "
    #                                 "    WHERE folder_id IN (SELECT folder_id "
    #                                 "                        FROM folders WHERE project_id = %(project_id)s)"),
    #                                {'project_id': project_id}, cur=cur)
    project_stats['total'] = format(int(project_statistics['images_taken']), ',d')
    project_ok = run_query(("WITH "
                                 " folders_q as (SELECT folder_id from folders WHERE project_id = %(project_id)s),"
                                 " files_q as (SELECT file_id FROM files f, folders_q fol WHERE f.folder_id = fol.folder_id),"
                                 " checks as (select settings_value as file_check from projects_settings where project_setting = 'project_checks' AND project_id = %(project_id)s),"
                                 " checklist as (select c.file_check, f.file_id from checks c, files_q f),"
                                 " data AS ("
                                 "SELECT c.file_id, sum(coalesce(f.check_results, 9)) as check_results"
                                 " FROM checklist c left join files_checks f on (c.file_id = f.file_id and c.file_check = f.file_check)"
                                 " group by c.file_id)"
                                 "SELECT count(file_id) as no_files FROM data WHERE check_results = 0"),
                                {'project_id': project_id}, cur=cur)
    project_stats['ok'] = format(int(project_ok[0]['no_files']), ',d')
    project_err = run_query(("WITH "
                                  " folders_q as (SELECT folder_id from folders WHERE project_id = %(project_id)s),"
                                  " files_q as (SELECT file_id FROM files f, folders_q fol WHERE f.folder_id = fol.folder_id),"
                                  " checks as (select settings_value as file_check from projects_settings where project_setting = 'project_checks' AND project_id = %(project_id)s),"
                                  " checklist as (select c.file_check, f.file_id from checks c, files_q f),"
                                  " data AS ("
                                  "SELECT c.file_id, sum(coalesce(f.check_results, 9)) as check_results"
                                  " FROM checklist c left join files_checks f on (c.file_id = f.file_id and c.file_check = f.file_check)"
                                  "      WHERE check_results = 1 "
                                  " group by c.file_id)"
                                  "SELECT count(file_id) as no_files FROM data WHERE check_results != 0"),
                                 {'project_id': project_id}, cur=cur)
    project_stats['errors'] = format(int(project_err[0]['no_files']), ',d')
    # project_pending = run_query(("WITH "
    #                                   " folders_q as (SELECT folder_id from folders WHERE project_id = %(project_id)s),"
    #                                   " files_q as (SELECT file_id FROM files f, folders_q fol WHERE f.folder_id = fol.folder_id),"
    #                                   " checks as (select settings_value as file_check from projects_settings where project_setting = 'project_checks' AND project_id = %(project_id)s),"
    #                                   " checklist as (select c.file_check, f.file_id from checks c, files_q f),"
    #                                   " data AS ("
    #                                   "SELECT c.file_id, coalesce(f.check_results, 9) as check_results"
    #                                   " FROM checklist c left join files_checks f on (c.file_id = f.file_id and c.file_check = f.file_check))"
    #                                   " SELECT count(distinct file_id) as no_files FROM data where check_results = 9"),
    #                                  {'project_id': project_id}, cur=cur)
    # project_stats['pending'] = format(int(project_pending[0]['no_files']), ',d')
    # project_public = run_query(("SELECT COALESCE(images_public, 0) as no_files FROM projects_stats WHERE "
    #                                  " project_id = %(project_id)s"),
    #                                 {'project_id': project_id}, cur=cur)
    # project_stats['public'] = format(int(project_public[0]['no_files']), ',d')

    project_folders = run_query(("SELECT f.project_folder, f.folder_id, coalesce(b1.badge_text, 0) as no_files, "
                                      "f.file_errors, f.status, f.error_info, COALESCE(mt.md5, 9) as md5_tif, COALESCE(mr.md5, 9) as md5_raw, "
                                      "f.delivered_to_dams, "
                                      " COALESCE(CASE WHEN qcf.qc_status = 0 THEN 'QC Passed' "
                                      "              WHEN qcf.qc_status = 1 THEN 'QC Failed' "
                                      "              WHEN qcf.qc_status = 9 THEN 'QC Pending' END,"
                                      "          'QC Pending') as qc_status "
                                      "FROM folders f "
                                      " LEFT JOIN folders_md5 mt ON (f.folder_id = mt.folder_id and mt.md5_type = 'tif') "
                                      " LEFT JOIN folders_md5 mr ON (f.folder_id = mr.folder_id and mr.md5_type = 'raw') "
                                      " LEFT JOIN qc_folders qcf ON (f.folder_id = qcf.folder_id) "
                                      " LEFT JOIN folders_badges b1 ON (f.folder_id = b1.folder_id AND b1.badge_type = 'no_files') "
                                      "WHERE f.project_id = %(project_id)s ORDER BY "
                                      "f.date DESC, f.project_folder DESC"),
                                     {'project_id': project_id}, cur=cur)

    # Get objects
    # proj_obj = run_query(("SELECT COALESCE(objects_digitized, 0) as no_objects FROM projects_stats WHERE "
    #            " project_id = %(project_id)s"),
    #           {'project_id': project_id}, cur=cur)
    project_stats['objects'] = format(int(project_statistics['objects_digitized']), ',d')

    folder_name = None
    folder_qc = {
        'qc_status': "QC Pending",
        'qc_by': "",
        'updated_at': "",
        'qc_ip': ""
    }
    folder_files_df = pd.DataFrame()
    pagination_html = ""
    files_df = ""
    files_count = ""
    folder_stats = {
        'no_files': 0,
        'no_errors': 0
    }
    post_processing_df = pd.DataFrame()
    project_folders_badges = run_query(
        "SELECT b.folder_id, b.badge_type, b.badge_css, b.badge_text "
        " FROM folders_badges b, folders f WHERE b.folder_id = f.folder_id and f.project_id = %(project_id)s and b.badge_type != 'no_files'",
        {'project_id': project_id}, cur=cur)
    if current_user.is_authenticated:
        user_name = current_user.name
        is_admin = user_perms('', user_type='admin')
    else:
        user_name = ""
        is_admin = False
    folder_links = None
    folder_id = None
    tab = None
    folder_name = None
    folder_qc = None

    # Reports
    reports = run_query("SELECT * FROM data_reports "
                        " WHERE project_id = %(project_id)s ORDER BY report_title_brief",
                             {'project_id': project_id}, cur=cur)

    if len(reports) > 0:
        proj_reports = True
    else:
        proj_reports = False

    # kiosk mode
    kiosk, user_address = kiosk_mode(request, settings.kiosks)

    # Disk space
    project_disks = run_query(("SELECT FORMAT_BYTES(sum(filesize)) as filesize, UPPER(filetype) as filetype "
                               "    FROM files_size "
                               "    WHERE file_id IN (SELECT file_id from files WHERE folder_id IN (SELECT folder_id "
                               "                        FROM folders WHERE project_id = %(project_id)s)) GROUP BY filetype"),
                              {'project_id': project_id}, cur=cur)

    project_disk = "NA"
    i = 0
    for disk in project_disks:
        if i > 0:
            project_disk = "{} / {}: {}".format(project_disk, disk['filetype'], disk['filesize'])
        else:
            project_disk = "{}: {}".format(disk['filetype'], disk['filesize'])
        i += 1

    cur.close()
    conn.close()

    return render_template('dashboard.html',
                           project_id=project_id,
                           project_info=project_info,
                           project_alias=project_alias,
                           project_stats=project_stats,
                           project_folders=project_folders,
                           files_df=files_df,
                           folder_id=folder_id,
                           folder_name=folder_name,
                           folder_qc=folder_qc,
                           tables=[folder_files_df.to_html(table_id='files_table',
                                                           index=False,
                                                           border=0,
                                                           escape=False,
                                                           classes=["display", "compact", "table-striped"])],
                           titles=[''],
                           username=user_name,
                           project_admin=project_admin,
                           is_admin=is_admin,
                           tab=tab,
                           files_count=files_count,
                           pagination_html=pagination_html,
                           pagination_html2=pagination_html,
                           folder_stats=folder_stats,
                           post_processing=[post_processing_df.to_html(table_id='post_processing_table',
                                                                       index=False,
                                                                       border=0,
                                                                       escape=False,
                                                                       classes=["display", "compact",
                                                                                "table-striped"])],
                           folder_links=folder_links,
                           project_folders_badges=project_folders_badges,
                           form=form,
                           proj_reports=proj_reports,
                           reports=reports,
                           site_env=site_env,
                           site_net=site_net,
                           kiosk=kiosk,
                           user_address=user_address,
                           project_disk=project_disk,
                           projects_links=projects_links,
                           project_manager_link=project_manager_link
                           )


@cache.memoize()
@app.route('/about/', methods=['GET'], strict_slashes=False)
def about():
    """About page for the system"""
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # kiosk mode
    kiosk, user_address = kiosk_mode(request, settings.kiosks)

    # Declare the login form
    form = LoginForm(request.form)
    return render_template('about.html', site_ver=site_ver, form=form, site_env=site_env, kiosk=kiosk,
                           user_address=user_address)


@app.route('/qc/<project_alias>/', methods=['POST', 'GET'], strict_slashes=False)
@login_required
def qc(project_alias=None):
    """List the folders and QC status"""
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logging.error(e)
        raise InvalidUsage('System error')

    # Declare the login form
    form = LoginForm(request.form)

    # Get project info
    project = run_query("SELECT * FROM projects WHERE project_alias = %(project_alias)s ",
                             {'project_alias': project_alias}, cur=cur)[0]
    project_id = project['project_id']

    username = current_user.name
    project_admin = run_query(("SELECT count(*) as no_results "
                                    "    FROM users u, qc_projects qp, projects p "
                                    "    WHERE u.username = %(username)s "
                                    "        AND p.project_alias = %(project_alias)s "
                                    "        AND qp.project_id = p.project_id "
                                    "        AND u.user_id = qp.user_id"),
                                   {'username': username, 'project_alias': project_alias}, cur=cur)
    if project_admin is None:
        # Not allowed
        return redirect(url_for('home'))
    # project_settings = run_query(("SELECT coalesce(s.qc_percent, 0.1) as qc_percent FROM projects p "
    #                                    "     LEFT JOIN qc_settings s ON (s.project_id = p.project_id) "
    #                                    " WHERE p.project_alias = %(project_alias)s "),
    #                                   {'project_alias': project_alias}, cur=cur)
    project_settings = run_query(("SELECT * FROM qc_settings "
                                 " WHERE project_id = %(project_id)s"),
                                {'project_id': project_id}, cur=cur)

    if len(project_settings) == 0:
        query = ("INSERT INTO qc_settings (project_id, qc_level, qc_percent, "
                 " qc_threshold_critical, qc_threshold_major, qc_threshold_minor, "
                 " qc_normal_percent, qc_reduced_percent, qc_tightened_percent, updated_at) "
                 "  VALUES ("
                 "  %(project_id)s, 'Tightened', 40, 0, 1.5, 4, 10, 5, 40, "
                 "  CURRENT_TIME)")
        q = query_database_insert(query, {'project_id': project_id}, cur=cur)
        project_settings = run_query(("SELECT * FROM qc_settings "
                                      " WHERE project_id = %(project_id)s"),
                                     {'project_id': project_id}, cur=cur)

    project_settings = project_settings[0]

    folder_qc_done = run_query(("WITH pfolders AS (SELECT folder_id from folders WHERE project_id = %(project_id)s),"
                                " errors AS "
                                "         (SELECT folder_id, count(file_id) as no_files "
                                "             FROM qc_files "
                                "             WHERE folder_id IN (SELECT folder_id from pfolders) "
                                "                 AND file_qc > 0 AND file_qc != 9 "
                                "               GROUP BY folder_id),"
                                "passed AS "
                                "         (SELECT folder_id, count(file_id) as no_files "
                                "             FROM qc_files "
                                "             WHERE folder_id IN (SELECT folder_id from pfolders) "
                                "                 AND file_qc = 0 "
                                "               GROUP BY folder_id),"
                                "total AS (SELECT folder_id, count(file_id) as no_files FROM qc_files "
                                "             WHERE folder_id IN (SELECT folder_id from pfolders)"
                                "                GROUP BY folder_id), "
                                " files_total AS (SELECT folder_id, count(file_id) as no_files FROM files "
                                "             WHERE folder_id IN (SELECT folder_id from pfolders)"
                                "                GROUP BY folder_id) "
                                " SELECT f.folder_id, f.project_folder, f.delivered_to_dams, "
                                "       ft.no_files, f.file_errors, f.status, f.error_info, "
                                "   CASE WHEN q.qc_status = 0 THEN 'QC Passed' "
                                "      WHEN q.qc_status = 1 THEN 'QC Failed' "
                                "      ELSE 'QC Pending' END AS qc_status, "
                                "      q.qc_ip, u.username AS qc_by, "
                                "      date_format(q.updated_at, '%%Y-%%m-%%d') AS updated_at, "
                                "       COALESCE(errors.no_files, 0) as qc_stats_no_errors, "
                                "       COALESCE(passed.no_files, 0) as qc_stats_no_passed,"
                                "       COALESCE(total.no_files, 0) as qc_stats_no_files "
                                " FROM folders f LEFT JOIN qc_folders q ON "
                                "       (f.folder_id = q.folder_id)"
                                "       LEFT JOIN users u ON "
                                "           (q.qc_by = u.user_id)"
                                "       LEFT JOIN errors ON "
                                "           (f.folder_id = errors.folder_id)"
                                "       LEFT JOIN passed ON "
                                "           (f.folder_id = passed.folder_id)"
                                "       LEFT JOIN total ON "
                                "           (f.folder_id = total.folder_id)"
                                "       LEFT JOIN files_total ft ON "
                                "           (f.folder_id = ft.folder_id), "
                                "   projects p "
                                " WHERE f.project_id = p.project_id "
                                "   AND p.project_id = %(project_id)s "
                                "   AND q.qc_status != 9 "
                                "  ORDER BY f.date DESC, f.project_folder DESC"),
                               {'project_id': project_id}, cur=cur)

    folder_qc_info = run_query(("WITH pfolders AS (SELECT folder_id from folders WHERE project_id = %(project_id)s),"
                                     " errors AS "
                                     "         (SELECT folder_id, count(file_id) as no_files "
                                     "             FROM qc_files "
                                     "             WHERE folder_id IN (SELECT folder_id from pfolders) "
                                     "                 AND file_qc > 0 AND file_qc != 9 "
                                     "               GROUP BY folder_id),"
                                     "passed AS "
                                     "         (SELECT folder_id, count(file_id) as no_files "
                                     "             FROM qc_files "
                                     "             WHERE folder_id IN (SELECT folder_id from pfolders) "
                                     "                 AND file_qc = 0 "
                                     "               GROUP BY folder_id),"
                                     "total AS (SELECT folder_id, count(file_id) as no_files FROM qc_files "
                                     "             WHERE folder_id IN (SELECT folder_id from pfolders)"
                                     "                GROUP BY folder_id), "
                                     " files_total AS (SELECT folder_id, count(file_id) as no_files FROM files "
                                     "             WHERE folder_id IN (SELECT folder_id from pfolders)"
                                     "                GROUP BY folder_id), "
                                     " qc as (SELECT f.folder_id, f.project_folder, f.delivered_to_dams, "
                                     "       ft.no_files, f.file_errors, f.status, f.date, f.error_info, "
                                     "   CASE WHEN q.qc_status = 0 THEN 'QC Passed' "
                                     "      WHEN q.qc_status = 1 THEN 'QC Failed' "
                                     "      ELSE 'QC Pending' END AS qc_status, "
                                     "      q.qc_ip, u.username AS qc_by, "
                                     "      date_format(q.updated_at, '%%Y-%%m-%%d') AS updated_at, "
                                     "       COALESCE(errors.no_files, 0) as qc_stats_no_errors, "
                                     "       COALESCE(passed.no_files, 0) as qc_stats_no_passed,"
                                     "       COALESCE(total.no_files, 0) as qc_stats_no_files "
                                     " FROM folders f LEFT JOIN qc_folders q ON "
                                     "       (f.folder_id = q.folder_id)"
                                     "       LEFT JOIN users u ON "
                                     "           (q.qc_by = u.user_id)"
                                     "       LEFT JOIN errors ON "
                                     "           (f.folder_id = errors.folder_id)"
                                     "       LEFT JOIN passed ON "
                                     "           (f.folder_id = passed.folder_id)"
                                     "       LEFT JOIN total ON "
                                     "           (f.folder_id = total.folder_id)"
                                     "       LEFT JOIN files_total ft ON "
                                     "           (f.folder_id = ft.folder_id), "
                                     "   projects p "
                                     " WHERE f.project_id = p.project_id "
                                     "   AND p.project_id = %(project_id)s) "
                                     " SELECT * FROM qc WHERE qc_status = 'QC Pending'"
                                     "  ORDER BY date ASC, project_folder ASC LIMIT 1"),
                                    {'project_id': project_id}, cur=cur)
    cur.close()
    conn.close()
    return render_template('qc.html', site_ver=site_ver,
                           username=username,
                           project_settings=project_settings,
                           folder_qc_info=folder_qc_info,
                           folder_qc_done=folder_qc_done,
                           folder_qc_done_len=len(folder_qc_done),
                           project=project,
                           form=form,
                           site_env=site_env,
                           site_net=site_net)


@app.route('/qc_process/<folder_id>/', methods=['GET', 'POST'], strict_slashes=False)
@login_required
def qc_process(folder_id):
    """Run QC on a folder"""
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logging.error(e)
        raise InvalidUsage('System error')

    # Declare the login form
    form = LoginForm(request.form)

    username = current_user.name
    project_admin = run_query(("SELECT count(*) as no_results FROM users u, qc_projects p, folders f "
                                    "    WHERE u.username = %(username)s "
                                    "        AND p.project_id = f.project_id "
                                    "        AND f.folder_id = %(folder_id)s "
                                    "        AND u.user_id = p.user_id"),
                                   {'username': username, 'folder_id': folder_id}, cur=cur)[0]
    if project_admin['no_results'] == 0:
        # Not allowed
        return redirect(url_for('home'))
    file_id_q = request.values.get('file_id')
    msg = ""
    if file_id_q is not None:
        qc_info = request.values.get('qc_info')
        qc_val = request.values.get('qc_val')
        user_id = run_query("SELECT user_id FROM users WHERE username = %(username)s",
                                 {'username': username}, cur=cur)[0]
        if qc_val != "0" and qc_info == "":
            msg = "Error: The field QC Details can not be empty if the file has an issue.<br>Please try again."
        else:
            q = query_database_insert(("UPDATE qc_files SET "
                                "      file_qc = %(qc_val)s, "
                                "      qc_by = %(qc_by)s, "
                                "      qc_info = %(qc_info)s "
                                " WHERE file_id = %(file_id)s"),
                               {'file_id': file_id_q,
                                'qc_info': qc_info,
                                'qc_val': qc_val,
                                'qc_by': user_id['user_id']
                                }, cur=cur)
            logging.info("file_id: {}".format(file_id_q))
            return redirect(url_for('qc_process', folder_id=folder_id))
    project_id = run_query("SELECT project_id from folders WHERE folder_id = %(folder_id)s",
                                {'folder_id': folder_id}, cur=cur)[0]

    project_settings = run_query("SELECT * FROM qc_settings WHERE project_id = %(project_id)s",
                                      {'project_id': project_id['project_id']}, cur=cur)[0]

    folder_qc_check = run_query(("SELECT "
                                      "  CASE WHEN q.qc_status = 0 THEN 'QC Passed' "
                                      "          WHEN q.qc_status = 1 THEN 'QC Failed' "
                                      "          ELSE 'QC Pending' END AS qc_status, "
                                      "      qc_ip, u.username AS qc_by, "
                                      "      date_format(q.updated_at, '%%Y-%%m-%%d') AS updated_at"
                                      " FROM qc_folders q, "
                                      "      users u WHERE q.qc_by=u.user_id "
                                      "      AND q.folder_id = %(folder_id)s"),
                                     {'folder_id': folder_id}, cur=cur)
    folder_qc = {}
    folder_qc['qc_status'] = 'QC Pending'
    folder_qc['qc_by'] = ''
    folder_qc['updated_at'] = ''
    folder_qc['qc_ip'] = ''
    if folder_qc_check is not None:
        if len(folder_qc_check) > 0:
            folder_qc['qc_status'] = folder_qc_check[0]['qc_status']
            folder_qc['qc_by'] = folder_qc_check[0]['qc_by']
            folder_qc['updated_at'] = folder_qc_check[0]['updated_at']
            folder_qc['qc_ip'] = folder_qc_check[0]['qc_ip']
    folder_stats1 = run_query(("SELECT count(file_id) as no_files "
                                    "    FROM files WHERE folder_id = %(folder_id)s"),
                                   {'folder_id': folder_id}, cur=cur)
    folder_stats2 = run_query(("SELECT count(DISTINCT c.file_id) as no_errors "
                                    "    FROM files_checks c "
                                    "    WHERE file_id IN ("
                                    "        SELECT file_id "
                                    "        FROM files WHERE folder_id = %(folder_id)s) "
                                    "        AND check_results = 1"),
                                   {'folder_id': folder_id}, cur=cur)
    folder_stats = {
        'no_files': folder_stats1[0]['no_files'],
        'no_errors': folder_stats2[0]['no_errors']
    }
    logging.info("qc_status: {} | no_files: {}".format(folder_qc['qc_status'], folder_stats['no_files']))
    project_alias = run_query(("SELECT project_alias FROM projects WHERE project_id IN "
                                    "   (SELECT project_id "
                                    "       FROM folders "
                                    "       WHERE folder_id = %(folder_id)s)"),
                                   {'folder_id': folder_id}, cur=cur)[0]
    if folder_qc['qc_status'] == "QC Pending" and folder_stats['no_files'] > 0:
        # Setup the files for QC
        in_qc = run_query("SELECT count(*) as no_files FROM qc_files WHERE folder_id = %(folder_id)s",
                               {'folder_id': folder_id}, cur=cur)
        if in_qc[0]['no_files'] == 0:
            q = query_database_insert("DELETE FROM qc_folders WHERE folder_id = %(folder_id)s",
                                 {'folder_id': folder_id}, cur=cur)
            q = query_database_insert("INSERT INTO qc_folders (folder_id, qc_status) VALUES (%(folder_id)s, 9)",
                                 {'folder_id': folder_id}, cur=cur)
            no_files_for_qc = math.ceil(folder_stats['no_files'] * (float(project_settings['qc_percent']) / 100))
            if no_files_for_qc < 10:
                if folder_stats['no_files'] > 10:
                    no_files_for_qc = 10
                else:
                    no_files_for_qc = folder_stats['no_files']
            q = query_database_insert(("INSERT INTO qc_files (folder_id, file_id) ("
                                  " SELECT folder_id, file_id "
                                  "  FROM files WHERE folder_id = %(folder_id)s "
                                  "  ORDER BY RAND() LIMIT {})").format(no_files_for_qc),
                                 {'folder_id': folder_id}, cur=cur)
            logging.info("1587: {}".format(no_files_for_qc))
            return redirect(url_for('qc_process', folder_id=folder_id))
        else:
            qc_stats_q = run_query(("WITH errors AS "
                                         "         (SELECT count(file_id) as no_files "
                                         "             FROM qc_files "
                                         "             WHERE folder_id = %(folder_id)s "
                                         "                 AND file_qc > 0 AND file_qc != 9),"
                                         "passed AS "
                                         "         (SELECT count(file_id) as no_files "
                                         "             FROM qc_files "
                                         "             WHERE folder_id = %(folder_id)s "
                                         "                 AND file_qc = 0),"
                                         "total AS (SELECT count(file_id) as no_files FROM qc_files "
                                         "             WHERE folder_id = %(folder_id)s)"
                                         " SELECT t.no_files, e.no_files as no_errors,"
                                         "         p.no_files as no_passed "
                                         " FROM errors e, total t, passed p "),
                                        {'folder_id': folder_id}, cur=cur)[0]
            qc_stats = {}
            qc_stats['no_files'] = int(qc_stats_q['no_files'])
            qc_stats['no_errors'] = int(qc_stats_q['no_errors'])
            qc_stats['passed'] = int(qc_stats_q['no_passed'])
            if qc_stats_q['no_files'] == qc_stats_q['no_errors']:
                qc_stats['percent_failed'] = 100
                qc_stats['percent_passed'] = 0
            else:
                qc_stats['percent_failed'] = round((int(qc_stats_q['no_errors']) / int(qc_stats_q['no_files'])) * 100,
                                                   3)
                qc_stats['percent_passed'] = round((int(qc_stats_q['no_passed']) / int(qc_stats_q['no_files'])) * 100,
                                                   3)
            folder = run_query("SELECT * FROM folders WHERE folder_id = %(folder_id)s",
                                    {'folder_id': folder_id}, cur=cur)[0]
            if qc_stats['no_files'] != int(qc_stats['no_errors']) + int(qc_stats['passed']):
                file_qc = run_query(("SELECT f.* FROM qc_files q, files f "
                                          "  WHERE q.file_id = f.file_id "
                                          "     AND f.folder_id = %(folder_id)s AND q.file_qc = 9 "
                                          "  LIMIT 1 "),
                                         {'folder_id': folder_id}, cur=cur)[0]
                file_details = run_query(("SELECT file_id, folder_id, file_name "
                                               " FROM files WHERE file_id = %(file_id)s"),
                                              {'file_id': file_qc['file_id']}, cur=cur)[0]
                file_checks = run_query(("SELECT file_check, check_results, "
                                              "       CASE WHEN check_info = '' THEN 'Check passed.' "
                                              "           ELSE check_info END AS check_info "
                                              "   FROM files_checks WHERE file_id = %(file_id)s"),
                                             {'file_id': file_qc['file_id']}, cur=cur)
                image_url = '/preview_image/' + str(file_qc['file_id']) + '/?'
                file_metadata = pd.DataFrame(run_query(("SELECT tag, taggroup, tagid, value "
                                                             "   FROM files_exif "
                                                             "   WHERE file_id = %(file_id)s "
                                                             "       AND lower(filetype) = 'tif' "
                                                             "   ORDER BY taggroup, tag "),
                                                            {'file_id': file_qc['file_id']}, cur=cur))
                folder = run_query(
                    ("SELECT * FROM folders "
                     "  WHERE folder_id IN (SELECT folder_id FROM files WHERE file_id = %(file_id)s)"),
                    {'file_id': file_qc['file_id']}, cur=cur)[0]
                cur.close()
                conn.close()
                return render_template('qc_file.html',
                                       folder=folder,
                                       qc_stats=qc_stats,
                                       folder_id=folder_id,
                                       file_qc=file_qc,
                                       project_settings=project_settings,
                                       file_details=file_details,
                                       file_checks=file_checks,
                                       image_url=image_url,
                                       username=username,
                                       project_alias=project_alias['project_alias'],
                                       tables=[file_metadata.to_html(table_id='file_metadata', index=False, border=0,
                                                                     escape=False,
                                                                     classes=["display", "compact", "table-striped"])],
                                       msg=msg,
                                       form=form,
                                       site_env=site_env,
                                       site_net=site_net
                                       )
            else:
                error_files = run_query(("SELECT f.file_name, "
                                         " CASE WHEN q.file_qc = 1 THEN 'Critical Issue' "
                                         " WHEN q.file_qc = 2 THEN 'Major Issue' "
                                         " WHEN q.file_qc = 3 THEN 'Minor Issue' END as file_qc, "
                                         " q.qc_info FROM qc_files q, files f "
                                              "  WHERE q.folder_id = %(folder_id)s "
                                              "  AND q.file_qc > 0 AND q.file_id = f.file_id"),
                                             {'folder_id': folder_id}, cur=cur)
                print(error_files)
                qc_folder_result = True
                crit_files = 0
                major_files = 0
                minor_files = 0
                for file in error_files:
                    if file['file_qc'] == 'Critical Issue':
                        crit_files += 1
                    elif file['file_qc'] == 'Major Issue':
                        major_files += 1
                    elif file['file_qc'] == 'Minor Issue':
                        minor_files += 1
                qc_threshold_critical_comparison = math.floor(folder_stats['no_files'] * (float(project_settings['qc_threshold_critical']) / 100))
                qc_threshold_major_comparison = math.floor(folder_stats['no_files'] * (float(project_settings['qc_threshold_major']) / 100))
                qc_threshold_minor_comparison = math.floor(folder_stats['no_files'] * (float(project_settings['qc_threshold_minor']) / 100))
                if crit_files > 0:
                    if qc_threshold_critical_comparison <= crit_files:
                        qc_folder_result = False
                if major_files > 0:
                    if qc_threshold_major_comparison <= major_files:
                        qc_folder_result = False
                if minor_files > 0:
                    if qc_threshold_minor_comparison <= minor_files:
                        qc_folder_result = False
                cur.close()
                conn.close()
                return render_template('qc_done.html',
                                       folder_id=folder_id,
                                       folder=folder,
                                       qc_stats=qc_stats,
                                       project_settings=project_settings,
                                       username=username,
                                       error_files=error_files,
                                       qc_folder_result=qc_folder_result,
                                       form=form,
                                       site_env=site_env,
                                       site_net=site_net)
    else:
        error_msg = "Folder is not available for QC."
        return render_template('error.html', form=form, error_msg=error_msg,
                               project_alias=project_alias['project_alias'], site_env=site_env), 400


@app.route('/qc_done/<folder_id>/', methods=['POST', 'GET'], strict_slashes=False)
@login_required
def qc_done(folder_id):
    """Run QC on a folder"""

    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logging.error(e)
        raise InvalidUsage('System error')

    username = current_user.name

    project_admin = run_query(("SELECT count(*) as no_results "
                                    "    FROM users u, qc_projects p, folders f "
                                    "    WHERE u.username = %(username)s "
                                    "        AND p.project_id = f.project_id "
                                    "        AND f.folder_id = %(folder_id)s "
                                    "        AND u.user_id = p.user_id"),
                                   {'username': username, 'folder_id': folder_id}, cur=cur)[0]
    if project_admin['no_results'] == 0:
        # Not allowed
        return redirect(url_for('home'))
    project_info = run_query(("SELECT project_id, project_alias "
                                 "   FROM projects "
                                 "   WHERE project_id IN "
                                 "   (SELECT project_id "
                                 "       FROM folders "
                                 "       WHERE folder_id = %(folder_id)s)"),
                                {'folder_id': folder_id}, cur=cur)[0]
    project_id = project_info['project_id']
    project_alias = project_info['project_alias']
    qc_info = request.values.get('qc_info')
    qc_status = request.values.get('qc_status')
    user_id = run_query("SELECT user_id FROM users WHERE username = %(username)s",
                             {'username': username}, cur=cur)[0]

    project_qc_settings = run_query(("SELECT * FROM qc_settings WHERE project_id = %(project_id)s"),
                                    {'project_id': project_id}, cur=cur)[0]
    logging.info("1763: {}".format(qc_status))
    q = query_database_insert(("UPDATE qc_folders SET "
                          "      qc_status = %(qc_status)s, "
                          "      qc_by = %(qc_by)s, "
                          "      qc_info = %(qc_info)s, "
                          "      qc_level = %(qc_level)s "
                          " WHERE folder_id = %(folder_id)s"),
                         {'folder_id': folder_id,
                          'qc_status': qc_status,
                          'qc_info': qc_info,
                          'qc_by': user_id['user_id'],
                          'qc_level': project_qc_settings['qc_level']
                          }, cur=cur)
    # Create folder badge
    clear_badges = run_query(
        "DELETE FROM folders_badges WHERE folder_id = %(folder_id)s and badge_type = 'qc_status'",
        {'folder_id': folder_id}, cur=cur)
    if qc_status == "0":
        badgecss = "bg-success"
        qc_info = "QC Passed"
    elif qc_status == "1":
        badgecss = "bg-danger"
        qc_info = "QC Failed"
    query = (
        "INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
        " VALUES (%(folder_id)s, 'qc_status', %(badgecss)s, %(msg)s, CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(msg)s,"
        " badge_css = %(badgecss)s, updated_at = CURRENT_TIMESTAMP")
    res = query_database_insert(query, {'folder_id': folder_id, 'badgecss': badgecss, 'msg': qc_info}, cur=cur)
    # Change inspection level, if needed
    project_qc_settings = run_query(("SELECT * FROM qc_settings WHERE project_id = %(project_id)s"),
                             {'project_id': project_id}, cur=cur)[0]
    project_qc_hist = run_query(("SELECT q.* FROM qc_folders q, folders f "
                                 " WHERE f.project_id = %(project_id)s AND q.folder_id = f.folder_id "
                                 "    AND q.qc_status != 9 "
                                 " ORDER BY updated_at DESC LIMIT 5"),
                                    {'project_id': project_id}, cur=cur)
    if len(project_qc_hist) <= 5:
        level = 'Tightened'
    else:
        ok_folders = 0
        for folder in project_qc_hist:
            if folder['qc_status'] != "0":
                ok_folders += 1
            if ok_folders <= 3:
                level = 'Tightened'
            elif ok_folders == 5:
                level = 'Normal'
            else:
                level = 'Normal'
    cur.close()
    conn.close()
    return redirect(url_for('qc', project_alias=project_alias))


@app.route('/home/', methods=['GET'], strict_slashes=False)
@login_required
def home():
    """Home for user, listing projects and options"""
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logging.error(e)
        raise InvalidUsage('System error')

    # Declare the login form
    form = LoginForm(request.form)

    user_name = current_user.name
    is_admin = user_perms('', user_type='admin')
    logging.info(is_admin)
    ip_addr = request.environ['REMOTE_ADDR']
    projects = run_query(("select p.project_title, p.project_id, p.project_alias, "
                               "     date_format(p.project_start, '%%b-%%Y') as project_start, "
                               "     date_format(p.project_end, '%%b-%%Y') as project_end,"
                               "     p.qc_status, p.project_unit "
                               " FROM qc_projects qp, "
                               "       users u, "
                               "       projects p "
                               " WHERE qp.project_id = p.project_id "
                               "     AND qp.user_id = u.user_id "
                               "     AND u.username = %(username)s "
                               "     AND p.project_alias IS NOT NULL "
                               " GROUP BY p.project_title, p.project_id, p.project_alias, "
                               "     p.project_start, p.project_end,"
                               "     p.qc_status, p.project_unit "
                               " ORDER BY p.projects_order DESC"),
                              {'username': user_name}, cur=cur)
    project_list = []
    for project in projects:
        logging.info("project: {}".format(project))
        project_total = run_query(("SELECT count(*) as no_files "
                                        "    FROM files "
                                        "    WHERE folder_id IN ("
                                        "            SELECT folder_id "
                                        "              FROM folders "
                                        "              WHERE project_id = %(project_id)s)"),
                                       {'project_id': project['project_id']}, cur=cur)
        project_ok = run_query(("WITH a AS ("
                                     "   SELECT file_id FROM files WHERE folder_id IN "
                                     "       (SELECT folder_id from folders WHERE project_id = %(project_id)s)"
                                     "  ),"
                                     "   data AS ("
                                     "   SELECT c.file_id, sum(check_results) as check_results "
                                     "   FROM files_checks c, a "
                                     "   WHERE c.file_id = a.file_id "
                                     "   GROUP BY c.file_id) "
                                     " SELECT count(file_id) as no_files "
                                     " FROM data WHERE check_results = 0"),
                                    {'project_id': project['project_id']}, cur=cur)
        project_err = run_query(
            ("SELECT count(distinct file_id) as no_files FROM files_checks WHERE check_results "
             "= 1 AND "
             "file_id in (SELECT file_id from files where folder_id IN (SELECT folder_id from folders WHERE project_id = %(project_id)s))"),
            {'project_id': project['project_id']}, cur=cur)
        project_public = run_query(("SELECT COALESCE(images_public, 0) as no_files FROM projects_stats WHERE "
                                         " project_id = %(project_id)s"),
                                        {'project_id': project['project_id']}, cur=cur)
        project_running = run_query(("SELECT count(distinct file_id) as no_files FROM files_checks WHERE "
                                          "check_results "
                                          "= 9 AND "
                                          "file_id in ("
                                          "SELECT file_id FROM files WHERE folder_id IN (SELECT folder_id FROM folders "
                                          "WHERE project_id = %(project_id)s))"),
                                         {'project_id': project['project_id']}, cur=cur)
        if int(project_ok[0]['no_files']) == 0:
            ok_percent = 0
        else:
            ok_percent = round((int(project_ok[0]['no_files']) / int(project_total[0]['no_files'])) * 100, 5)
        if int(project_err[0]['no_files']) == 0:
            error_percent = 0
        else:
            error_percent = round((int(project_err[0]['no_files']) / int(project_total[0]['no_files'])) * 100, 5)
        if int(project_running[0]['no_files']) == 0:
            running_percent = 0
        else:
            running_percent = round((int(project_running[0]['no_files']) / int(project_total[0]['no_files'])) * 100, 5)
        if project['project_alias'] is None:
            project_alias = project['project_id']
        else:
            project_alias = project['project_alias']
        logging.info("project_alias: {}".format(project_alias))
        project_list.append({
            'project_title': project['project_title'],
            'project_id': project['project_id'],
            'filecheck_link': None,
            'total': format(int(project_total[0]['no_files']), ',d'),
            'errors': format(int(project_err[0]['no_files']), ',d'),
            'ok': format(int(project_ok[0]['no_files']), ',d'),
            'running': format(int(project_running[0]['no_files']), ',d'),
            'public': format(int(project_public[0]['no_files']), ',d'),
            'ok_percent': ok_percent,
            'error_percent': error_percent,
            'running_percent': running_percent,
            'project_alias': project_alias,
            'project_start': project['project_start'],
            'project_end': project['project_end'],
            'qc_status': project['qc_status'],
            'project_unit': project['project_unit']
        })

    cur.close()
    conn.close()

    return render_template('userhome.html', project_list=project_list, username=user_name,
                           is_admin=is_admin, ip_addr=ip_addr, form=form,
                           site_env=site_env, site_net=site_net)


@app.route('/new_project/', methods=['GET'], strict_slashes=False)
@login_required
def new_project(msg=None):
    """Create a new project"""
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Declare the login form
    form = LoginForm(request.form)

    username = current_user.name
    full_name = current_user.full_name
    is_admin = user_perms('', user_type='admin')
    if is_admin is False:
        # Not allowed
        return redirect(url_for('home'))
    else:
        msg = ""
        return render_template('new_project.html',
                               username=username,
                               full_name=full_name,
                               is_admin=is_admin,
                               msg=msg,
                               today_date=datetime.today().strftime('%Y-%m-%d'),
                               form=form,
                               site_env=site_env)


@app.route('/create_new_project/', methods=['POST'], strict_slashes=False)
@login_required
def create_new_project():
    """Create a new project"""

    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logging.error(e)
        raise InvalidUsage('System error')

    username = current_user.name
    is_admin = user_perms('', user_type='admin')
    if is_admin is False:
        # Not allowed
        return redirect(url_for('home'))
    p_title = request.values.get('p_title')
    p_alias = request.values.get('p_alias')
    p_desc = request.values.get('p_desc')
    p_url = request.values.get('p_url')
    p_coordurl = request.values.get('p_coordurl')
    p_noobjects = request.values.get('p_noobjects')
    p_manager = current_user.full_name
    p_md = request.values.get('p_md')
    p_prod = request.values.get('p_prod')
    p_method = request.values.get('p_method')
    p_unit = request.values.get('p_unit')
    p_area = request.values.get('p_area')
    p_storage = request.values.get('p_storage')
    p_start = request.values.get('p_start')
    p_unitstaff = request.values.get('p_unitstaff')
    project = query_database_insert(("INSERT INTO projects  "
                              "   (project_title, "
                              "    project_unit, "
                              "    project_alias,"
                              "    project_description, "
                              "    project_coordurl,"
                              "    project_area, "
                              "    project_section, "
                              "    project_method, "
                              "    project_manager, "
                              "    project_status, "
                              "    project_type,"
                              "    project_datastorage,"
                              "    project_start, "
                              "    projects_order, "
                              "      stats_estimated "
                              " ) "
                              "  ("
                              "        SELECT "
                              "            %(p_title)s,"
                              "            %(p_unit)s, "
                              "            %(p_alias)s, "
                              "            %(p_desc)s, "
                              "            %(p_coordurl)s, "
                              "            %(p_area)s, "
                              "            %(p_md)s, "
                              "            %(p_method)s, "
                              "            %(p_manager)s, "
                              "            'Ongoing', "
                              "            %(p_prod)s, "
                              "            %(p_storage)s, "
                              "            %(p_start)s, "
                              "            max(projects_order) + 1,"
                              "              0"
                              "          FROM projects "
                              ")"),
                             {'p_title': p_title,
                              'p_unit': p_unit,
                              'p_alias': p_alias,
                              'p_desc': p_desc,
                              'p_url': p_url,
                              'p_coordurl': p_coordurl,
                              'p_area': p_area,
                              'p_md': p_md,
                              'p_noobjects': p_noobjects,
                              'p_method': p_method,
                              'p_manager': p_manager,
                              'p_prod': p_prod,
                              'p_storage': p_storage,
                              'p_start': p_start
                              }, cur=cur)
    project = run_query("SELECT project_id FROM projects WHERE project_title = %(p_title)s AND project_unit = %(p_unit)s",
                             {'p_title': p_title, 'p_unit': p_unit}, cur=cur)
    project_id = project[0]['project_id']
    project = query_database_insert(("INSERT INTO projects_stats "
                              "  (project_id, collex_total, collex_to_digitize) VALUES  "
                              "   ( %(project_id)s, %(collex_total)s, %(collex_total)s)"),
                             {'project_id': project_id,
                              'collex_total': p_noobjects}, cur=cur)
    user_project = query_database_insert(("INSERT INTO qc_projects (project_id, user_id) VALUES "
                                     "    (%(project_id)s, %(user_id)s)"),
                                    {'project_id': project_id,
                                     'user_id': current_user.id}, cur=cur)
    if current_user.id != '101':
        user_project = query_database_insert(("INSERT INTO qc_projects (project_id, user_id) VALUES "
                                         "    (%(project_id)s, %(user_id)s)"),
                                        {'project_id': project_id,
                                         'user_id': '101'}, cur=cur)
    # if current_user.id != '106':
    #     user_project = query_database_insert(("INSERT INTO qc_projects (project_id, user_id) VALUES "
    #                                      "    (%(project_id)s, %(user_id)s)"),
    #                                     {'project_id': project_id,
    #                                      'user_id': '106'})
    if p_unitstaff != '':
        unitstaff = p_unitstaff.split(',')
        logging.info("unitstaff: {}".format(p_unitstaff))
        logging.info("len_unitstaff: {}".format(len(unitstaff)))
        if len(unitstaff) > 0:
            for staff in unitstaff:
                staff_user_id = run_query("SELECT user_id FROM users WHERE username = %(username)s",
                                               {'username': staff.strip()}, cur=cur)
                if len(staff_user_id) == 1:
                    user_project = query_database_insert(("INSERT INTO qc_projects (project_id, user_id) VALUES "
                                                     "    (%(project_id)s, %(user_id)s)"),
                                                    {'project_id': project_id,
                                                     'user_id': staff_user_id[0]['user_id']}, cur=cur)
                else:
                    user_project = query_database_insert(("INSERT INTO users (username, user_active, is_admin) VALUES "
                                                   "    (%(username)s, 'T', 'F')"),
                                                  {'username': staff.strip()}, cur=cur)
                    get_user_project = run_query(("SELECT user_id FROM users WHERE username = %(username)s"),
                                                         {'username': staff.strip()}, cur=cur)
                    user_project = query_database_insert(("INSERT INTO qc_projects (project_id, user_id) VALUES "
                                                     "    (%(project_id)s, %(user_id)s)"),
                                                    {'project_id': project_id,
                                                     'user_id': get_user_project[0]['user_id']}, cur=cur)

    cur.close()
    conn.close()
    return redirect(url_for('home', _anchor=p_alias))


@app.route('/edit_project/<project_alias>/', methods=['GET'], strict_slashes=False)
@login_required
def edit_project(project_alias=None):
    """Edit a project"""
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Declare the login form
    form = LoginForm(request.form)

    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logging.error(e)
        raise InvalidUsage('System error')

    username = current_user.name
    is_admin = user_perms('', user_type='admin')
    if is_admin is False:
        # Not allowed
        return redirect(url_for('home'))
    project_admin = run_query(("SELECT count(*) as no_results "
                                    "    FROM users u, qc_projects qp, projects p "
                                    "    WHERE u.username = %(username)s "
                                    "        AND p.project_alias = %(project_alias)s "
                                    "        AND qp.project_id = p.project_id "
                                    "        AND u.user_id = qp.user_id"),
                                   {'username': username, 'project_alias': project_alias}, cur=cur)
    if len(project_admin) == 0:
        # Not allowed
        return redirect(url_for('home'))
    project = run_query(("SELECT p.project_id, p.project_alias, "
                              " p.project_title, "
                              " p.project_alias, "
                              " p.project_start, "
                              " p.project_end, "
                              " p.project_unit, "
                              " p.project_section, "
                              " p.project_status, "
                              " NULL as project_url, "
                              " COALESCE(p.project_description, '') as project_description, "
                              " COALESCE(s.collex_to_digitize, 0) AS collex_to_digitize "
                              " FROM projects p LEFT JOIN projects_stats s "
                              "     ON (p.project_id = s.project_id) "
                              " WHERE p.project_alias = %(project_alias)s"),
                             {'project_alias': project_alias}, cur=cur)[0]
    cur.close()
    conn.close()
    return render_template('edit_project.html',
                           username=username,
                           is_admin=is_admin,
                           project=project,
                           form=form,
                           site_env=site_env,
                           site_net=site_net)


@app.route('/project_update/<project_alias>', methods=['POST'], strict_slashes=False)
@login_required
def project_update(project_alias):
    """Save edits to a project"""

    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logging.error(e)
        raise InvalidUsage('System error')

    username = current_user.name
    is_admin = user_perms('', user_type='admin')
    if is_admin is False:
        # Not allowed
        return redirect(url_for('home'))
    project_id = run_query(("SELECT project_id FROM projects WHERE project_alias = %(project_alias)s"),
                                   {'project_alias': project_alias}, cur=cur)
    project_id = project_id[0]['project_id']
    project_admin = run_query(("SELECT count(*) as no_results "
                                    "    FROM users u, qc_projects qp, projects p "
                                    "    WHERE u.username = %(username)s "
                                    "        AND p.project_alias = %(project_alias)s "
                                    "        AND qp.project_id = p.project_id "
                                    "        AND u.user_id = qp.user_id"),
                                   {'username': username, 'project_alias': project_alias}, cur=cur)
    if len(project_admin) == 0:
        # Not allowed
        return redirect(url_for('home'))
    p_title = request.values.get('p_title')
    p_desc = request.values.get('p_desc')
    p_url = request.values.get('p_url')
    p_status = request.values.get('p_status')
    p_start = request.values.get('p_start')
    p_end = request.values.get('p_end')
    p_noobjects = request.values.get('p_noobjects')
    project = query_database_insert(("UPDATE projects SET "
                              "   project_title = %(p_title)s, "
                              "   project_status = %(p_status)s, "
                              "   project_start = CAST(%(p_start)s AS date) "
                              " WHERE project_alias = %(project_alias)s"),
                             {'p_title': p_title,
                              'p_status': p_status,
                              'p_start': p_start,
                              'project_alias': project_alias}, cur=cur)
    if p_desc != '':
        project = query_database_insert(("UPDATE projects SET "
                                  "   project_description = %(p_desc)s "
                                  " WHERE project_alias = %(project_alias)s"),
                                 {'p_desc': p_desc,
                                  'project_alias': project_alias}, cur=cur)
    # if p_url != '':
    #     project = query_database_insert(("UPDATE projects SET "
    #                               "   project_url = %(p_url)s "
    #                               " WHERE project_alias = %(project_alias)s"),
    #                              {'p_url': p_url,
    #                               'project_alias': project_alias}, cur=cur)
    if p_end != 'None':
        project = query_database_insert(("UPDATE projects SET "
                                  "   project_end = CAST(%(p_end)s AS date) "
                                  " WHERE project_alias = %(project_alias)s "),
                                 {'p_end': p_end,
                                  'project_alias': project_alias}, cur=cur)

    if p_noobjects != '0':
        project = query_database_insert(("UPDATE projects_stats SET "
                                  "   collex_to_digitize = %(p_noobjects)s, "
                                  "   collex_ready = %(p_noobjects)s "
                                  " WHERE project_id = %(project_id)s "),
                                 {'project_id': project_id,
                                  'p_noobjects': p_noobjects}, cur=cur)
    cur.close()
    conn.close()
    return redirect(url_for('home'))


@cache.memoize(60)
@app.route('/dashboard/', methods=['GET'], strict_slashes=False)
def dashboard_empty():
    return redirect(url_for('login'))


@app.route('/file/<file_id>/', methods=['GET'], strict_slashes=False)
def file(file_id=None):
    """File details"""
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Declare the login form
    form = LoginForm(request.form)

    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logging.error(e)
        raise InvalidUsage('System error')

    file_id, file_uid = check_file_id(file_id, cur=cur)

    if file_id is None:
        error_msg = "File ID is missing."
        return render_template('error.html', form=form, error_msg=error_msg, project_alias=None, site_env=site_env), 400

    folder_info = run_query(
        "SELECT * FROM folders WHERE folder_id IN (SELECT folder_id FROM files WHERE file_id = %(file_id)s)",
        {'file_id': file_id}, cur=cur)
    if len(folder_info) == 0:
        error_msg = "Invalid File ID."
        return render_template('error.html', form=form, error_msg=error_msg, project_alias=None, site_env=site_env), 400
    else:
        folder_info = folder_info[0]
    file_details = run_query(("WITH data AS ("
                                   "         SELECT file_id, "
                                   "             COALESCE(preview_image, CONCAT(%(preview)s, file_id)) as preview_image, "
                                   "             folder_id, file_name, dams_uan "
                                   "             FROM files "
                                   "                 WHERE folder_id = %(folder_id)s AND folder_id IN (SELECT folder_id FROM folders)"
                                   " UNION "
                                   "         SELECT file_id, COALESCE(preview_image, CONCAT(%(preview)s, file_id)) as preview_image, folder_id, file_name, dams_uan "
                                   "             FROM files "
                                   "                 WHERE folder_id = %(folder_id)s AND folder_id NOT IN (SELECT folder_id FROM folders)"
                                   "             ORDER BY file_name"
                                   "),"
                                   "data2 AS (SELECT file_id, preview_image, folder_id, file_name, dams_uan, "
                                   "         lag(file_id,1) over (order by file_name) prev_id,"
                                   "         lead(file_id,1) over (order by file_name) next_id "
                                   " FROM data)"
                                   " SELECT "
                                   " file_id, "
                                   "     CASE WHEN position('?' in preview_image)>0 THEN preview_image ELSE CONCAT(preview_image, '?') END AS preview_image, "
                                   " folder_id, file_name, dams_uan, prev_id, next_id "
                                   "FROM data2 WHERE file_id = %(file_id)s LIMIT 1"),
                                  {'folder_id': folder_info['folder_id'], 'file_id': file_id,
                                   'preview': '/preview_image/'}, cur=cur)

    file_details = file_details[0]
    project_alias = run_query(("SELECT COALESCE(project_alias, CAST(project_id AS char)) as project_id FROM projects "
                    " WHERE project_id = %(project_id)s"),
                   {'project_id': folder_info['project_id']}, cur=cur)[0]
    project_alias = project_alias['project_id']

    file_checks = run_query(("SELECT file_check, check_results, CASE WHEN check_info = '' THEN 'Check passed.' "
                                  " ELSE check_info END AS check_info "
                                  " FROM files_checks WHERE file_id = %(file_id)s"),
                                 {'file_id': file_id}, cur=cur)
    image_url = '/preview_image/' + str(file_id)
    file_metadata = pd.DataFrame(run_query(("SELECT tag, taggroup, tagid, value "
                                                 " FROM files_exif "
                                                 " WHERE file_id = %(file_id)s AND "
                                                 "       lower(filetype) = 'tif' AND "
                                                 "       lower(taggroup) != 'system' "
                                                 " ORDER BY taggroup, tag "),
                                                {'file_id': file_id}, cur=cur))
    file_links = run_query("SELECT link_name, link_url FROM files_links WHERE file_id = %(file_id)s ",
                                {'file_id': file_id}, cur=cur)
    if current_user.is_authenticated:
        user_name = current_user.name
        is_admin = user_perms('', user_type='admin')
    else:
        user_name = ""
        is_admin = False
    logging.info("project_alias: {}".format(project_alias))

    cur.close()
    conn.close()

    # kiosk mode
    kiosk, user_address = kiosk_mode(request, settings.kiosks)

    return render_template('file.html',
                           folder_info=folder_info,
                           file_details=file_details,
                           file_checks=file_checks,
                           username=user_name,
                           image_url=image_url,
                           is_admin=is_admin,
                           project_alias=project_alias,
                           tables=[file_metadata.to_html(table_id='file_metadata', index=False, border=0,
                                                         escape=False,
                                                         classes=["display", "compact", "table-striped"])],
                           file_links=file_links,
                           form=form,
                           site_env=site_env,
                           site_net=site_net,
                           kiosk=kiosk,
                           user_address=user_address
                           )


@app.route('/file/', methods=['GET'], strict_slashes=False)
def file_empty():
    return redirect(url_for('login'))


@cache.memoize()
@app.route('/dashboard/<project_alias>/search_files', methods=['GET'], strict_slashes=False)
def search_files(project_alias):
    """Search files"""
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Declare the login form
    form = LoginForm(request.form)

    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logging.error(e)
        raise InvalidUsage('System error')

    q = request.values.get('q')
    metadata = request.values.get('metadata')
    page = request.values.get('page')
    if page is None:
        page = 0
    try:
        page = int(page)
    except:
        page = 0
    offset = page * 50
    project_info = run_query("SELECT * FROM projects WHERE project_alias = %(project_alias)s",
                                  {'project_alias': project_alias}, cur=cur)[0]
    if q is None:
        error_msg = "No search query was submitted."
        cur.close()
        conn.close()
        return render_template('error.html', form=form, error_msg=error_msg, project_alias=project_alias,
                               site_env=site_env), 400
    else:
        logging.info("q: {}".format(q))
        logging.info("metadata: {}".format(metadata))
        logging.info("offset: {}".format(offset))
        if metadata is None or metadata == '0':
            results = run_query(("SELECT "
                                      "  f.file_id, f.folder_id, f.file_name, COALESCE(f.preview_image, CONCAT('/preview_image/', file_id)) as preview_image, fd.project_folder "
                                      " FROM files f, folders fd, projects p "
                                      " WHERE f.folder_id = fd.folder_id AND "
                                      "  lower(f.file_name) LIKE lower(%(q)s) AND "
                                      "  fd.project_id = p.project_id AND "
                                      "  p.project_alias = %(project_alias)s "
                                      " ORDER BY f.file_name"
                                      " LIMIT 50 "
                                      " OFFSET {offset} ").format(offset=offset),
                                     {'project_alias': project_alias,
                                      'q': '%%' + q + '%%'}, cur=cur)
        else:
            results = run_query(("WITH m AS (SELECT file_id, tag, value, tagid, taggroup "
                                      "              FROM files_exif "
                                      "              WHERE value ILIKE %(q)s)"
                                      "SELECT "
                                      "  f.file_id, f.folder_id, f.file_name, COALESCE(f.preview_image, CONCAT('/preview_image/', file_id)) as preview_image, fd.project_folder "
                                      " FROM files f, m, folders fd, projects p "
                                      " WHERE f.folder_id = fd.folder_id AND "
                                      "  lower(f.file_name) LIKE lower(%(q)s) AND "
                                      "  f.file_id = m.file_id AND "
                                      "  fd.project_id = p.project_id AND "
                                      "  p.project_alias = %(project_alias)s "
                                      "  GROUP BY f.file_id, f.folder_id, f.file_name, f.preview_image, fd.project_folder "
                                      " ORDER BY f.file_name"
                                      " LIMIT 50 "
                                      " OFFSET {offset} ").format(offset=offset),
                                     {'project_alias': project_alias,
                                      'q': '%%' + q + '%%'}, cur=cur)
    cur.close()
    conn.close()

    # kiosk mode
    kiosk, user_address = kiosk_mode(request, settings.kiosks)

    return render_template('search_files.html',
                           results=results,
                           project_info=project_info,
                           project_alias=project_alias,
                           q=q,
                           form=form,
                           site_env=site_env,
                           site_net=site_net,
                           kiosk=kiosk,
                           user_address=user_address)


@cache.memoize()
@app.route('/dashboard/<project_alias>/search_folders', methods=['GET'], strict_slashes=False)
def search_folders(project_alias):
    """Search files"""
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Declare the login form
    form = LoginForm(request.form)

    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logging.error(e)
        raise InvalidUsage('System error')

    q = request.values.get('q')
    page = request.values.get('page')
    if page is None:
        page = 0
    offset = page * 50
    project_info = run_query("SELECT * FROM projects WHERE project_alias = %(project_alias)s",
                                  {'project_alias': project_alias}, cur=cur)[0]
    if q is None:
        error_msg = "No search query was submitted."
        cur.close()
        conn.close()
        return render_template('error.html', form=form, error_msg=error_msg, project_alias=project_alias,
                                site_net=site_net, site_env=site_env), 400
    else:
        logging.info("q: {}".format(q))
        logging.info("offset: {}".format(offset))
        results = run_query((
                                     "WITH pfolders AS (SELECT folder_id from folders WHERE project_id in (SELECT project_id FROM projects WHERE project_alias = %(project_alias)s)),"
                                     " errors AS "
                                     "         (SELECT folder_id, count(file_id) as no_files "
                                     "             FROM qc_files "
                                     "             WHERE folder_id IN (SELECT folder_id from pfolders) "
                                     "                 AND file_qc = 1 "
                                     "               GROUP BY folder_id),"
                                     "passed AS "
                                     "         (SELECT folder_id, count(file_id) as no_files "
                                     "             FROM qc_files "
                                     "             WHERE folder_id IN (SELECT folder_id from pfolders) "
                                     "                 AND file_qc = 0 "
                                     "               GROUP BY folder_id),"
                                     "total AS (SELECT folder_id, count(file_id) as no_files FROM qc_files "
                                     "             WHERE folder_id IN (SELECT folder_id from pfolders)"
                                     "                GROUP BY folder_id) "
                                     " SELECT f.folder_id, f.project_folder, f.delivered_to_dams, "
                                     "       f.no_files, f.file_errors "
                                     " FROM folders f LEFT JOIN qc_folders q ON "
                                     "       (f.folder_id = q.folder_id)"
                                     "       LEFT JOIN users u ON "
                                     "           (q.qc_by = u.user_id)"
                                     "       LEFT JOIN errors ON "
                                     "           (f.folder_id = errors.folder_id)"
                                     "       LEFT JOIN passed ON "
                                     "           (f.folder_id = passed.folder_id)"
                                     "       LEFT JOIN total ON "
                                     "           (f.folder_id = total.folder_id),"
                                     "   projects p "
                                     " WHERE f.project_id = p.project_id "
                                     "   AND p.project_alias = %(project_alias)s "
                                     "   AND lower(f.project_folder) LIKE lower(%(q)s) "
                                     "  ORDER BY f.project_folder ASC"
                                     "  LIMIT 50 OFFSET {offset}").format(offset=offset),
                                 {'project_alias': project_alias,
                                  'q': '%%' + q + '%%'}, cur=cur)
    results_df = pd.DataFrame({'folder': [], 'no_files': []})
    for row in results:
        results_df.loc[len(results_df.index)] = ['<a href="/dashboard/' + project_alias \
                                                 + '/' \
                                                 + str(row['folder_id']) \
                                                 + '/" title="Folder Details">' \
                                                 + row['project_folder'] \
                                                 + '</a> ', str(row['no_files'])]
    cur.close()
    conn.close()

    # kiosk mode
    kiosk, user_address = kiosk_mode(request, settings.kiosks)

    return render_template('search_folders.html',
                           tables=[results_df.to_html(table_id='results',
                                                      index=False,
                                                      border=0,
                                                      escape=False,
                                                      classes=["display", "compact", "table-striped"])],
                           project_info=project_info,
                           project_alias=project_alias,
                           q=q,
                           form=form,
                           site_env=site_env,
                           site_net=site_net,
                           kiosk=kiosk,
                           user_address=user_address)


@app.route("/logout", methods=['GET'], strict_slashes=False)
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route("/notuser", methods=['GET'], strict_slashes=False)
def not_user():
    # Declare the login form
    form = LoginForm(request.form)
    logout_user()
    return render_template('notuser.html', form=form, site_env=site_env)


###################################
# Osprey API
###################################
@cache.memoize()
@app.route('/api/', methods=['GET', 'POST'], strict_slashes=False)
def api_route_list():
    """Print available routes in JSON"""
    # Adapted from https://stackoverflow.com/a/17250154
    func_list = {}
    for rule in app.url_map.iter_rules():
        # Skip 'static' routes
        if str(rule).startswith('/api/new'):
            continue
        elif str(rule).startswith('/api/update'):
            continue
        elif str(rule).startswith('/api'):
            func_list[rule.rule] = app.view_functions[rule.endpoint].__doc__
        else:
            continue
    data = {'routes': func_list, 'sys_ver': site_ver, 'env': settings.env}
    return jsonify(data)


@app.route('/api/projects/', methods=['GET', 'POST'], strict_slashes=False)
def api_get_projects():
    """Get the list of projects."""
    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logging.error(e)
        raise InvalidUsage('System error')

    # For post use request.form.get("variable")
    section = request.form.get("section")
    # logging.info("VAL: {}".format(val))
    if section not in ['MD', 'IS']:
        query = (" SELECT "
                 " p.project_id, "
                 " p.projects_order, "
                 " p.project_unit, "
                 " u.unit_fullname, "
                 " p.project_alias, "
                 " p.project_title, "
                 " p.project_status, "
                 " p.project_manager, "
                 " date_format(p.project_start, '%Y-%b-%d') AS project_start, "
                 " CASE WHEN p.project_end IS NULL THEN NULL ELSE date_format(p.project_end, '%Y-%b-%d') END AS project_end, "
                 " p.objects_estimated,  "
                 " ps.objects_digitized, "
                 " p.images_estimated, "
                 " ps.images_taken, "
                 " ps.images_public "
                 " FROM projects p LEFT JOIN projects_stats ps ON (p.project_id = ps.project_id), si_units u "
                 " WHERE p.project_unit = u.unit_id AND p.skip_project = 0 "
                 " GROUP BY "
                 "        p.project_id, p.project_title, p.project_unit, u.unit_fullname, p.project_status, p.project_description, "
                 "        p.project_method, p.project_manager, p.project_start, p.project_end, p.updated_at, p.projects_order, p.project_type, "
                 "        ps.collex_to_digitize, p.images_estimated, p.objects_estimated, ps.images_taken, ps.objects_digitized, ps.images_public"
                 " ORDER BY p.projects_order DESC")
        projects_data = run_query(query, cur=cur)
    else:
        query = (" SELECT "
                 " p.project_id, "
                 " p.projects_order, "
                 " p.project_unit, "
                 " u.unit_fullname, "
                 " p.project_alias, "
                 " p.project_title, "
                 " p.project_status, "
                 " p.project_manager, "
                 " date_format(p.project_start, '%%Y-%%b-%%d') AS project_start, "
                 " CASE WHEN p.project_end IS NULL THEN NULL ELSE date_format(p.project_end, '%%Y-%%b-%%d') END AS project_end, "
                 " p.objects_estimated,  "
                 " ps.objects_digitized, "
                 " p.images_estimated, "
                 " ps.images_taken, "
                 " ps.images_public "
                 " FROM projects p LEFT JOIN projects_stats ps ON (p.project_id = ps.project_id), si_units u "
                 " WHERE p.project_unit = u.unit_id AND p.skip_project = 0 AND p.project_section = %(section)s "
                 " GROUP BY "
                 "        p.project_id, p.project_title, p.project_unit, p.project_status, u.unit_fullname, p.project_description, "
                 "        p.project_method, p.project_manager, p.project_start, p.project_end, p.updated_at, p.projects_order, p.project_type, "
                 "        ps.collex_to_digitize, p.images_estimated, p.objects_estimated, ps.images_taken, ps.objects_digitized, ps.images_public"
                 " ORDER BY p.projects_order DESC")
        projects_data = run_query(query, {'section': section}, cur=cur)
    last_update = run_query("SELECT date_format(MAX(updated_at), '%d-%b-%Y') AS updated_at FROM projects_stats", cur=cur)
    data = ({"projects": projects_data, "last_update": last_update[0]['updated_at']})
    # For admin
    api_key = request.form.get("api_key")
    logging.info("api_key: {}".format(api_key))
    if api_key is not None:
        if validate_api_key(api_key, cur=cur):
            query = (" SELECT * FROM qc_settings WHERE project_id = %(project_id)s")
            projects_data = run_query(query, {'section': section}, cur=cur)
    cur.close()
    conn.close()
    return jsonify(data)


@app.route('/api/projects/<project_alias>', methods=['GET', 'POST'], strict_slashes=False)
def api_get_project_details(project_alias=None):
    """Get the details of a project by specifying the project_alias."""
    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logging.error(e)
        raise InvalidUsage('System error')

    api_key = request.form.get("api_key")
    logging.info("api_key: {}".format(api_key))
    if api_key is None or validate_api_key(api_key, cur=cur) is False:
        data = run_query(("SELECT "
                               "project_id, "
                               "project_title, "
                               "project_alias, "
                               "project_unit, "
                               "project_status, "
                               "project_description, "
                               "project_type, "
                               "project_method, "
                               "project_manager, "
                               "project_area, "
                               "date_format(project_start, '%%y-%%m-%%d') AS project_start, "
                               "CASE WHEN project_end IS NULL THEN NULL ELSE date_format(project_end, '%%y-%%m-%%d') END as project_end, "
                               "project_notice, "
                               "cast(updated_at as DATE) AS updated_at "
                               "FROM projects WHERE project_alias = %(project_alias)s"),
                              {'project_alias': project_alias}, cur=cur)
    else:
        data = run_query(("SELECT "
                               "project_id, "
                               "project_title, "
                               "project_alias, "
                               "project_unit, "
                               "project_status, "
                               "project_description, "
                               "project_type, "
                               "project_method, "
                               "project_manager, "
                               "project_area, "
                               "project_datastorage, "
                               "date_format(project_start, '%%y-%%m-%%d') AS project_start, "
                               "CASE WHEN project_end IS NULL THEN NULL ELSE date_format(project_end, '%%y-%%m-%%d') END as project_end, "
                               "project_notice, "
                               "cast(updated_at AS DATE) as updated_at "
                               "FROM projects WHERE project_alias = %(project_alias)s"),
                              {'project_alias': project_alias}, cur=cur)
    if data is None:
        raise InvalidUsage('Project does not exists', status_code=401)
    else:
        if api_key is None or validate_api_key(api_key, cur=cur) is False:
            folders = run_query(("SELECT "
                                      "folder_id, project_id, project_folder as folder, status, "
                                      "notes, error_info, date_format(date, '%%y-%%m-%%d') as capture_date, "
                                      "no_files, file_errors "
                                      "FROM folders WHERE project_id = %(project_id)s"),
                                     {'project_id': data[0]['project_id']}, cur=cur)
        else:
            folders = run_query(("SELECT "
                                      "folder_id, project_id, project_folder as folder, "
                                      "folder_path, status, notes, "
                                      "error_info, date_format(date, '%%y-%%m-%%d') as capture_date, "
                                      "no_files, file_errors, "
                                      " CASE WHEN delivered_to_dams = 1 THEN 0 ELSE 9 END as delivered_to_dams "
                                      "FROM folders WHERE project_id = %(project_id)s"),
                                     {'project_id': data[0]['project_id']}, cur=cur)
        project_checks = run_query(("SELECT settings_value as project_check FROM projects_settings "
                                         " WHERE project_id = %(project_id)s AND project_setting = 'project_checks'"),
                                        {'project_id': data[0]['project_id']}, cur=cur)
        data[0]['project_checks'] = ','.join(str(v['project_check']) for v in project_checks)
        project_postprocessing = run_query(("SELECT settings_value as project_postprocessing FROM projects_settings "
                                         " WHERE project_id = %(project_id)s AND project_setting = 'project_postprocessing' ORDER BY table_id"),
                                        {'project_id': data[0]['project_id']}, cur=cur)
        data[0]['project_postprocessing'] = ','.join(str(v['project_postprocessing']) for v in project_postprocessing)
        data[0]['folders'] = folders
        project_stats = run_query(("SELECT "
                                        "collex_total, collex_to_digitize, collex_ready, objects_digitized, "
                                        "images_taken, images_in_dams, images_in_cis, images_public, "
                                        "no_records_in_cis, no_records_in_collexweb, no_records_in_collectionssiedu, "
                                        "no_records_in_gbif, cast(updated_at AS DATE) as updated_at "
                                        "FROM projects_stats WHERE project_id = %(project_id)s"),
                                       {'project_id': data[0]['project_id']}, cur=cur)
        data[0]['project_stats'] = project_stats[0]
        # Reports
        reports = run_query(
            "SELECT report_id, report_title, updated_at FROM data_reports WHERE project_id = %(project_id)s",
            {'project_id': data[0]['project_id']}, cur=cur)
        data[0]['reports'] = reports
    cur.close()
    conn.close()
    return jsonify(data[0])


@app.route('/api/update/<project_alias>', methods=['POST'], strict_slashes=False)
def api_update_project_details(project_alias=None):
    """Update a project properties."""
    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logging.error(e)
        raise InvalidUsage('System error')

    api_key = request.form.get("api_key")
    logging.info("api_key: {}".format(api_key))
    if api_key is None:
        raise InvalidUsage('Missing key', status_code=401)
    else:
        if validate_api_key(api_key, cur=cur):
            # Get project_id
            project_id = run_query("SELECT project_id FROM projects WHERE project_alias = %(project_alias)s", {'project_alias': project_alias}, cur=cur)
            if len(project_id) == 0:
                raise InvalidUsage('Invalid project', status_code=401)
            else:
                project_id = project_id[0]['project_id']
            # Value to update
            query_type = request.form.get("type")
            query_property = request.form.get("property")
            query_value = request.form.get("value")
            if query_type is not None and query_property is not None and query_value is not None:
                if query_type == "folder":
                    folder_id = request.form.get("folder_id")
                    if folder_id is not None:
                        if query_property == "status0":
                            query = ("UPDATE folders SET status = 0, error_info = NULL WHERE folder_id = %(folder_id)s")
                            res = query_database_insert(query, {'folder_id': folder_id}, cur=cur)
                            clear_badges = run_query("DELETE FROM folders_badges WHERE folder_id = %(folder_id)s and badge_type = 'folder_error'",
                                {'folder_id': folder_id}, cur=cur)
                        elif query_property == "status9":
                            query = (
                                "UPDATE folders SET status = 9, error_info = %(value)s WHERE folder_id = %(folder_id)s")
                            res = query_database_insert(query, {'value': query_value, 'folder_id': folder_id}, cur=cur)
                        elif query_property == "status1":
                            query = (
                                "UPDATE folders SET status = 1, error_info = %(value)s WHERE folder_id = %(folder_id)s")
                            res = query_database_insert(query, {'value': query_value, 'folder_id': folder_id}, cur=cur)
                            clear_badges = run_query("DELETE FROM folders_badges WHERE folder_id = %(folder_id)s and badge_type = 'folder_error'",
                                {'folder_id': folder_id}, cur=cur)
                            query = (
                                "INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
                                " VALUES (%(folder_id)s, 'folder_error', 'bg-danger', %(msg)s, CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(msg)s,"
                                " badge_css = 'bg-danger', updated_at = CURRENT_TIMESTAMP")
                            res = query_database_insert(query, {'folder_id': folder_id, 'msg': query_value}, cur=cur)
                        elif query_property == "checking_folder":
                            # Clear badges
                            clear_badges = run_query(
                                "DELETE FROM folders_badges WHERE folder_id = %(folder_id)s and badge_type = 'no_files'",
                                {'folder_id': folder_id}, cur=cur)
                            clear_badges = run_query(
                                "DELETE FROM folders_badges WHERE folder_id = %(folder_id)s and badge_type = 'error_files'",
                                {'folder_id': folder_id}, cur=cur)
                            query = (
                                "INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
                                " VALUES (%(folder_id)s, 'verification', 'bg-secondary', 'Folder under verification...', CURRENT_TIMESTAMP)")
                            res = query_database_insert(query, {'folder_id': folder_id}, cur=cur)
                        elif query_property == "stats":
                            # Clear badges
                            clear_badges = run_query("DELETE FROM folders_badges WHERE folder_id = %(folder_id)s and badge_type = 'no_files'", {'folder_id': folder_id}, cur=cur)
                            clear_badges = run_query("DELETE FROM folders_badges WHERE folder_id = %(folder_id)s and badge_type = 'error_files'",{'folder_id': folder_id}, cur=cur)
                            clear_badges = run_query("DELETE FROM folders_badges WHERE folder_id = %(folder_id)s and badge_type = 'verification'", {'folder_id': folder_id}, cur=cur)
                            # Badge of no_files
                            no_files = run_query("SELECT COUNT(*) AS no_files FROM files WHERE folder_id = %(folder_id)s", {'folder_id': folder_id}, cur=cur)
                            if no_files[0]['no_files'] > 0:
                                if no_files[0]['no_files'] == 1:
                                    no_folder_files = "1 file"
                                else:
                                    no_folder_files = "{} files".format(no_files[0]['no_files'])
                                query = ("INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
                                         " VALUES (%(folder_id)s, 'no_files', 'bg-primary', %(no_files)s, CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(no_files)s,"
                                         " badge_css = 'bg-primary', updated_at = CURRENT_TIMESTAMP")
                                res = query_database_insert(query, {'folder_id': folder_id, 'no_files': no_folder_files}, cur=cur)
                            # Badge of error files
                            # no_files = query_database("SELECT file_errors FROM folders WHERE folder_id = %(folder_id)s", {'folder_id': folder_id})
                            query = ("UPDATE folders f SET f.file_errors = 0 where folder_id = %(folder_id)s")
                            res = query_database_insert(query, {'folder_id': folder_id}, cur=cur)
                            query = ("WITH data AS (SELECT CASE WHEN COUNT(DISTINCT f.file_id) > 0 THEN 1 ELSE 0 END AS no_files, %(folder_id)s as folder_id FROM files_checks c, files f"
                                        " WHERE f.folder_id = %(folder_id)s AND f.file_id = c.file_id AND c.check_results = 1)"
                                        " UPDATE folders f, data d SET f.file_errors = d.no_files "
                                        "WHERE f.folder_id = d.folder_id")
                            res = query_database_insert(query, {'folder_id': folder_id}, cur=cur)
                            no_files = run_query("SELECT file_errors FROM folders WHERE folder_id = %(folder_id)s", {'folder_id': folder_id}, cur=cur)
                            if no_files[0]['file_errors'] == 1:
                                query = (
                                    "INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
                                    " VALUES (%(folder_id)s, 'error_files', 'bg-danger', 'Files with errors', CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(no_files)s,"
                                    "       badge_css = 'bg-danger', updated_at = CURRENT_TIMESTAMP")
                                res = query_database_insert(query, {'folder_id': folder_id, 'no_files': no_folder_files}, cur=cur)
                            # Update project
                            ## Update count
                            query = ("with data as "
                                     "  (select fol.project_id, count(DISTINCT f.file_name) as no_files "
                                     "          from files f, folders fol "
                                     "          where fol.project_id = %(project_id)s and fol.folder_id =f.folder_id)"
                                     "UPDATE projects_stats p, data SET p.images_taken = data.no_files where p.project_id = data.project_id")
                            res = query_database_insert(query, {'project_id': project_id}, cur=cur)
                            ## Get query for no. of objects
                            query_obj = run_query("SELECT project_object_query FROM projects WHERE project_id = %(project_id)s",
                                                 {'project_id': project_id}, cur=cur)[0]
                            query = ("with data as "
                                     "  (select fol.project_id, {} as no_objects"
                                     "          from files f, folders fol "
                                     "          where fol.project_id = %(project_id)s and fol.folder_id =f.folder_id)"
                                     "UPDATE projects_stats p, data SET p.objects_digitized = data.no_objects where p.project_id = data.project_id".format(query_obj['project_object_query'].replace('\\', '')))
                            res = query_database_insert(query, {'project_id': project_id}, cur=cur)
                        elif query_property == "raw0":
                            query = ("INSERT INTO folders_md5 (folder_id, md5_type, md5) "
                                     " VALUES (%(folder_id)s, %(value)s, 0) ON DUPLICATE KEY UPDATE md5 = 0")
                            res = query_database_insert(query, {'value': query_value, 'folder_id': folder_id}, cur=cur)
                        elif query_property == "raw1":
                            query = ("INSERT INTO folders_md5 (folder_id, md5_type, md5) "
                                     " VALUES (%(folder_id)s, %(value)s, 1) ON DUPLICATE KEY UPDATE md5 = 1")
                            res = query_database_insert(query, {'value': query_value, 'folder_id': folder_id}, cur=cur)
                        elif query_property == "tif_md5_exists":
                            query = ("INSERT INTO folders_md5 (folder_id, md5_type, md5) "
                                               " VALUES (%(folder_id)s, 'tif', %(value)s) ON DUPLICATE KEY UPDATE md5 = %(value)s")
                            res = query_database_insert(query, {'value': query_value, 'folder_id': folder_id}, cur=cur)
                            if query_value == 1:
                                query = (
                                    "INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
                                    " VALUES (%(folder_id)s, 'md5_files', 'bg-danger', 'MD5 files missing', CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = 'MD5 files missing',"
                                    "       badge_css = 'bg-danger', updated_at = CURRENT_TIMESTAMP")
                                res = query_database_insert(query, {'folder_id': folder_id}, cur=cur)
                        elif query_property == "tif_md5_matches_error":
                            query = (
                                "INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
                                " VALUES (%(folder_id)s, 'folder_md5', 'bg-danger', %(value)s, CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(value)s,"
                                "       badge_css = 'bg-danger', updated_at = CURRENT_TIMESTAMP")
                            res = query_database_insert(query, {'folder_id': folder_id, 'value': query_value}, cur=cur)
                        elif query_property == "tif_md5_matches_ok":
                            clear_badges = run_query(
                                "DELETE FROM folders_badges WHERE folder_id = %(folder_id)s and badge_type = 'folder_md5'",
                                {'folder_id': folder_id}, cur=cur)
                            query = (
                                "INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
                                " VALUES (%(folder_id)s, 'folder_md5', 'bg-success', %(value)s, CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(value)s,"
                                "       badge_css = 'bg-success', updated_at = CURRENT_TIMESTAMP")
                            res = query_database_insert(query, {'folder_id': folder_id, 'value': 'TIF MD5 Valid'}, cur=cur)
                        elif query_property == "raw_md5_matches_error":
                            query = (
                                "INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
                                " VALUES (%(folder_id)s, 'folder_raw_md5', 'bg-danger', %(value)s, CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(value)s,"
                                "       badge_css = 'bg-danger', updated_at = CURRENT_TIMESTAMP")
                            res = query_database_insert(query, {'folder_id': folder_id, 'value': query_value}, cur=cur)
                        elif query_property == "raw_md5_matches_ok":
                            clear_badges = run_query(
                                "DELETE FROM folders_badges WHERE folder_id = %(folder_id)s and badge_type = 'folder_raw_md5'",
                                {'folder_id': folder_id}, cur=cur)
                            query = (
                                "INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
                                " VALUES (%(folder_id)s, 'folder_raw_md5', 'bg-success', %(value)s, CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(value)s,"
                                "       badge_css = 'bg-success', updated_at = CURRENT_TIMESTAMP")
                            res = query_database_insert(query, {'folder_id': folder_id, 'value': 'RAW MD5 Valid'}, cur=cur)
                        elif query_property == "raw_md5_exists":
                            query = ("INSERT INTO folders_md5 (folder_id, md5_type, md5) "
                                               " VALUES (%(folder_id)s, 'raw', %(value)s) ON DUPLICATE KEY UPDATE md5 = %(value)s")
                            res = query_database_insert(query, {'value': query_value, 'folder_id': folder_id}, cur=cur)
                            query = (
                                "INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
                                " VALUES (%(folder_id)s, 'md5_files', 'bg-danger', 'MD5 files missing', CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = 'MD5 files missing',"
                                "       badge_css = 'bg-danger', updated_at = CURRENT_TIMESTAMP")
                            if query_value == 1:
                                res = query_database_insert(query, {'folder_id': folder_id}, cur=cur)
                        elif query_property == "qc":
                            query = ("SELECT * FROM qc_folders WHERE folder_id = %(folder_id)s")
                            folder_qc = query_database_insert(query, {'folder_id': folder_id}, cur=cur)
                            if len(folder_qc[0]) == 0:
                                qc_status = "QC Pending"
                                badge_css = "bg-secondary"
                            else:
                                folder_qc_status = folder_qc[0]['qc_status']
                                if folder_qc_status == 0:
                                    qc_status = "QC Passed"
                                    badge_css = "bg-success"
                                elif folder_qc_status ==1:
                                    qc_status = "QC Failed"
                                    badge_css = "bg-danger"
                                elif folder_qc_status == 9:
                                    qc_status = "QC Pending"
                                    badge_css = "bg-secondary"
                            query = ("INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
                                " VALUES (%(folder_id)s, 'qc_status', %(badge_css)s, %(qc_status)s, CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(qc_status)s,"
                                "       badge_css = %(badge_css)s, updated_at = CURRENT_TIMESTAMP")
                            res = query_database_insert(query, {'qc_status': qc_status, 'badge_css': badge_css, 'folder_id': folder_id}, cur=cur)
                        else:
                            raise InvalidUsage('Invalid operation', status_code=401)
                        cur.close()
                        conn.close()
                        return jsonify({"result": True})
                if query_type == "file":
                    file_id = request.form.get("file_id")
                    folder_id = request.form.get("folder_id")
                    if query_property == "unique":
                        # Check if file is unique
                        query = ("SELECT f.file_id, fol.project_folder FROM files f, folders fol "
                                 " WHERE f.folder_id = fol.folder_id AND f.file_id = %(file_id)s AND f.folder_id != %(folder_id)s"
                                 " AND f.folder_id IN (SELECT folder_id from folders where project_id = %(project_id)s)")
                        res = run_query(query,
                                        {'file_id': file_id, 'folder_id': folder_id, 'project_id': project_id},
                                        cur=cur)
                        if len(res) == 0:
                            check_results = 0
                            check_info = ""
                        elif len(res) == 1:
                            check_results = 1
                            conflict_folder = res[0]['project_folder']
                            check_info = "File with the same name in folder: {}".format(conflict_folder)
                        else:
                            check_results = 1
                            conflict_folder = []
                            for row in res:
                                conflict_folder.append(row['project_folder'])
                            conflict_folder = ', '.join(conflict_folder)
                            check_info = "Files with the same name in folders: {}".format(conflict_folder)
                        query = (
                            "INSERT INTO files_checks (file_id, folder_id, file_check, check_results, check_info, updated_at) "
                            "VALUES (%(file_id)s, %(folder_id)s, 'unique_file', %(check_results)s, %(check_info)s, CURRENT_TIME)"
                            " ON DUPLICATE KEY UPDATE"
                            " check_results = %(check_results)s, check_info = %(check_info)s, updated_at = CURRENT_TIME")
                        res = query_database_insert(query,
                                                    {'file_id': file_id, 'folder_id': folder_id,
                                                     'check_results': check_results, 'check_info': check_info}, cur=cur)
                    elif query_property == "filechecks":
                        # Add to server side:
                        #  - valid_name
                        #  - dupe_elsewhere
                        #  - md5
                        folder_id = request.form.get("folder_id")
                        file_check = request.form.get("file_check")
                        check_results = query_value
                        check_info = request.form.get("check_info")
                        query = (
                            "INSERT INTO files_checks (file_id, folder_id, file_check, check_results, check_info, updated_at) "
                            " VALUES (%(file_id)s, %(folder_id)s, %(file_check)s, %(check_results)s, %(check_info)s, CURRENT_TIME) "
                            " ON DUPLICATE KEY UPDATE "
                            " check_results = %(check_results)s, check_info = %(check_info)s, updated_at = CURRENT_TIME")
                        logging.info(query)
                        res = query_database_insert(query,
                                                    {'file_id': file_id, 'folder_id': folder_id,
                                                     'file_check': file_check,
                                                     'check_results': check_results, 'check_info': check_info}, cur=cur)
                        logging.info(res)
                    elif query_property == "filemd5":
                        filetype = request.form.get("filetype")
                        folder_id = request.form.get("folder_id")
                        query = ("INSERT INTO file_md5 (file_id, filetype, md5) "
                                 " VALUES (%(file_id)s, %(filetype)s, %(value)s) ON DUPLICATE KEY UPDATE md5 = %(value)s")
                        res = query_database_insert(query,
                                                    {'file_id': file_id, 'filetype': filetype, 'value': query_value}, cur=cur)
                        # Check for the same MD5 in another file
                        # query = ("SELECT f.file_id, f.file_name, fol.project_folder "
                        #          " FROM files f, file_md5 m, folders fol "
                        #          " WHERE f.folder_id = fol.folder_id AND f.file_id = m.file_id AND"
                        #          "   m.filetype='tif' and m.md5 = %(value)s and f.file_id != %(file_id)s")
                        # res = query_database(query, {'value': query_value, 'file_id': file_id})
                        # if len(res) == 0:
                        #     check_results = 0
                        #     check_info = ""
                        # elif len(res) == 1:
                        #     check_results = 1
                        #     conflict_file = res[0]['file_name']
                        #     conflict_folder = res[0]['project_folder']
                        #     check_info = "File ({}) with the same MD5 hash in folder: {}".format(conflict_file, conflict_folder)
                        # else:
                        #     check_results = 1
                        #     conflict_folder = []
                        #     for row in res:
                        #         conflict_folder.append('/'.join([row['project_folder'], row['file_name']]))
                        #     conflict_folder = ', '.join(conflict_folder)
                        #     check_info = "Files with the same MD5 hash: {}".format(conflict_folder)
                        # query = ("INSERT INTO files_checks (file_id, folder_id, file_check, check_results, check_info, updated_at) "
                        #          "VALUES (%(file_id)s, %(folder_id)s, 'md5', %(check_results)s, %(check_info)s, CURRENT_TIME) ON DUPLICATE KEY UPDATE "
                        #          " check_results = %(check_results)s, check_info = %(check_info)s, updated_at = CURRENT_TIME")
                        # res = query_database_insert(query, {'file_id': file_id, 'folder_id': folder_id,
                        #                                     'check_results': check_results, 'check_info': check_info})
                    elif query_property == "exif":
                        filetype = request.form.get("filetype")
                        data_json = json.loads(query_value)
                        # exif_data = []
                        query = ("INSERT INTO files_exif (file_id, filetype, taggroup, tag, tagid, value) "
                                 " VALUES (%s, %s, %s, %s, %s, %s) "
                                 " ON DUPLICATE KEY UPDATE value = %s")
                        for key in data_json[0].keys():
                            if key == 'SourceFile':
                                continue
                            else:
                                for k, item in data_json[0][key].items():
                                    if k == "id":
                                        this_key = item
                                    else:
                                        if type(item) == 'list':
                                            this_val = ', '.join(item)
                                        else:
                                            this_val = str(item)
                                row_data = (file_id, filetype, key.split(':')[0], key.split(':')[1], this_key, this_val, this_val)
                                # exif_data.append(row_data)
                                res = query_database_insert(query, row_data, cur=cur)
                        # res = query_database_insert_multi(query, exif_data, cur=cur)
                        # logging.info("exif_data for {}:{}".format(file_id, exif_data))
                    elif query_property == "delete":
                        query = ("DELETE FROM files WHERE file_id = %(file_id)s")
                        res = query_database_insert(query, {'file_id': file_id}, cur=cur)
                    else:
                        raise InvalidUsage('Invalid value for property', status_code=400)
                    cur.close()
                    conn.close()
                    return jsonify({"result": True})
                else:
                    raise InvalidUsage('Invalid value for type', status_code=400)
            else:
                raise InvalidUsage('Missing args', status_code=400)
        else:
            raise InvalidUsage('Unauthorized', status_code=401)


@app.route('/api/new/<project_alias>', methods=['POST'], strict_slashes=False)
def api_new_folder(project_alias=None):
    """Update a project properties."""
    api_key = request.form.get("api_key")
    logging.info("api_key: {}".format(api_key))
    if api_key is None:
        raise InvalidUsage('Missing key', status_code=401)
    else:
        # Connect to db
        try:
            conn = pymysql.connect(host=settings.host,
                                   user=settings.user,
                                   passwd=settings.password,
                                   database=settings.database,
                                   port=settings.port,
                                   charset='utf8mb4',
                                   cursorclass=pymysql.cursors.DictCursor,
                                   autocommit=True)
            cur = conn.cursor()
        except pymysql.Error as e:
            logging.error(e)
            raise InvalidUsage('System error')

        if validate_api_key(api_key, cur=cur):
            # Get project_id
            results = run_query("SELECT project_id from projects WHERE project_alias = %(project_alias)s",
                                     {'project_alias': project_alias}, cur=cur)
            project_id = results[0]['project_id']
            # New folder info
            query_type = request.form.get("type")
            if query_type is not None:
                if query_type == "folder":
                    folder = request.form.get("folder")
                    folder_path = request.form.get("folder_path")
                    project_id = request.form.get("project_id")
                    folder_date = request.form.get("folder_date")
                    if folder is not None and folder_path is not None:
                        query = ("INSERT INTO folders (project_folder, folder_path, status, project_id, date) "
                                 " VALUES (%(folder)s, %(folder_path)s, 0, %(project_id)s, %(folder_date)s)")
                        data = query_database_insert(query, {'folder': folder, 'folder_path': folder_path,
                                                             'project_id': project_id, 'folder_date': folder_date},
                                                     return_res=True, cur=cur)
                        data = run_query("SELECT * FROM folders WHERE project_folder = %(project_folder)s AND folder_path = %(folder_path)s AND project_id = %(project_id)s",
                                              {'project_folder': folder, 'folder_path': folder_path, 'project_id': project_id}, cur=cur)
                        cur.close()
                        conn.close()
                        return jsonify({"result": data})
                    else:
                        raise InvalidUsage('Missing args', status_code=400)
                elif query_type == "file":
                    filename = request.form.get("filename")
                    timestamp = request.form.get("timestamp")
                    folder_id = request.form.get("folder_id")
                    if filename is not None and timestamp is not None and folder_id is not None:
                        query = ("INSERT INTO files (folder_id, file_name, file_timestamp, uid) "
                                 "  VALUES (%(folder_id)s, %(filename)s, %(timestamp)s, uuid_v4s())")
                        data = query_database_insert(query, {'folder_id': folder_id, 'filename': filename,
                                                             'timestamp': timestamp}, cur=cur)
                        logging.debug("new_file:{}".format(data))
                        query = ("SELECT file_id, uid FROM files WHERE folder_id = %(folder_id)s AND file_name = %(filename)s")
                        file_info = run_query(query, {'folder_id': folder_id, 'filename': filename}, cur=cur)
                        file_id = file_info[0]['file_id']
                        file_uid = file_info[0]['uid']
                        # Check for unique file
                        query = ("SELECT f.file_id, fol.project_folder FROM files f, folders fol "
                                 " WHERE f.folder_id = fol.folder_id AND f.file_name = %(filename)s AND f.folder_id != %(folder_id)s"
                                 " AND f.folder_id IN (SELECT folder_id from folders where project_id = %(project_id)s)")
                        res = run_query(query,
                                             {'filename': filename, 'folder_id': folder_id, 'project_id': project_id}, cur=cur)
                        if len(res) == 0:
                            check_results = 0
                            check_info = ""
                        elif len(res) == 1:
                            check_results = 1
                            conflict_folder = res[0]['project_folder']
                            check_info = "File with the same name in folder: {}".format(conflict_folder)
                        else:
                            check_results = 1
                            conflict_folder = []
                            for row in res:
                                conflict_folder.append(row['project_folder'])
                            conflict_folder = ', '.join(conflict_folder)
                            check_info = "Files with the same name in folders: {}".format(conflict_folder)
                        query = ("INSERT INTO files_checks (file_id, uid, folder_id, file_check, check_results, check_info, updated_at) "
                            "VALUES (%(file_id)s, %(uid)s, %(folder_id)s, 'unique_file', %(check_results)s, %(check_info)s, CURRENT_TIME)"
                            " ON DUPLICATE KEY UPDATE"
                            " check_results = %(check_results)s, check_info = %(check_info)s, updated_at = CURRENT_TIME")
                        res = query_database_insert(query,
                                                    {'file_id': file_id, 'folder_id': folder_id,
                                                     'check_results': check_results, 'check_info': check_info, 'uid': file_uid}, cur=cur)
                        query = ("SELECT * FROM files WHERE file_id = %(file_id)s")
                        data = run_query(query, {'file_id': file_id}, cur=cur)
                        cur.close()
                        conn.close()
                        return jsonify({"result": data})
                    else:
                        raise InvalidUsage('Missing args', status_code=400)
                elif query_type == "filesize":
                    file_id = request.form.get("file_id")
                    filetype = request.form.get("filetype")
                    filesize = request.form.get("filesize")
                    if file_id is not None and filetype is not None and filesize is not None:
                        query = ("INSERT INTO files_size (file_id, filetype, filesize) "
                                 " VALUES (%(file_id)s, %(filetype)s, %(filesize)s) ON DUPLICATE KEY UPDATE "
                                 " filesize = %(filesize)s")
                        data = query_database_insert(query,
                                                     {'file_id': file_id, 'filetype': filetype, 'filesize': filesize}, cur=cur)
                        cur.close()
                        conn.close()
                        return jsonify({"result": data})
                    else:
                        raise InvalidUsage('Missing args', status_code=400)
                else:
                    raise InvalidUsage('Invalid value for type', status_code=400)
            else:
                raise InvalidUsage('Missing args', status_code=400)
        else:
            raise InvalidUsage('Unauthorized', status_code=401)


@app.route('/api/folders/<int:folder_id>', methods=['GET', 'POST'], strict_slashes=False)
def api_get_folder_details(folder_id=None):
    """Get the details of a folder and the list of files."""
    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logging.error(e)
        raise InvalidUsage('System error')

    data = run_query(("SELECT f.folder_id, f.project_id, f.project_folder as folder, f.status, "
                           "   f.notes, f.date, coalesce(f.no_files, 0) as no_files, f.file_errors, f.error_info, "
                            " CASE WHEN f.delivered_to_dams = 0 THEN 'Completed' "
                              "              WHEN f.delivered_to_dams = 1 THEN 'Ready' "
                              "              WHEN f.delivered_to_dams = 9 THEN 'Pending' END as delivered_to_dams, "
                           " COALESCE(CASE WHEN qcf.qc_status = 0 THEN 'QC Passed' "
                              "              WHEN qcf.qc_status = 1 THEN 'QC Failed' "
                              "              WHEN qcf.qc_status = 9 THEN 'QC Pending' END,"
                              "          'QC Pending') as qc_status "
                        " FROM folders f "
                     " LEFT JOIN qc_folders qcf ON (f.folder_id = qcf.folder_id) "
                      " WHERE f.folder_id = %(folder_id)s"), {'folder_id': folder_id}, api=True, cur=cur)
    project_id = data[0]['project_id']
    if len(data) == 1:
        api_key = request.form.get("api_key")
        logging.info("api_key: {}".format(api_key))
        if api_key is None:
            query = ("SELECT file_id, folder_id, file_name, DATE_FORMAT(file_timestamp, '%%Y-%%m-%%d %%H:%%i:%%S') as file_timestamp, "
                 " dams_uan, preview_image, DATE_FORMAT(updated_at, '%%Y-%%m-%%d %%H:%%i:%%S') as updated_at, "
                 " DATE_FORMAT(created_at, '%%Y-%%m-%%d %%H:%%i:%%S') AS created_at "
                 " FROM files WHERE folder_id = %(folder_id)s")
            files = run_query(query, {'folder_id': folder_id}, api=True, cur=cur)
            data[0]['files'] = files
        else:
            if validate_api_key(api_key, cur=cur):
                filechecks_list_temp = run_query(
                    ("SELECT settings_value as file_check FROM projects_settings "
                     " WHERE project_setting = 'project_checks' and project_id = %(project_id)s"),
                    {'project_id': project_id}, cur=cur)
                filechecks_list = []
                for fcheck in filechecks_list_temp:
                    filechecks_list.append(fcheck['file_check'])

                query = (
                    "SELECT file_id, folder_id, file_name, DATE_FORMAT(file_timestamp, '%%Y-%%m-%%d %%H:%%i:%%S') as file_timestamp, "
                    " dams_uan, preview_image, DATE_FORMAT(updated_at, '%%Y-%%m-%%d %%H:%%i:%%S') as updated_at, "
                    " DATE_FORMAT(created_at, '%%Y-%%m-%%d %%H:%%i:%%S') AS created_at "
                    " FROM files WHERE folder_id = %(folder_id)s")
                files_list = run_query(query, {'folder_id': folder_id}, api=True, cur=cur)
                folder_files_df = pd.DataFrame(files_list)
                for fcheck in filechecks_list:
                    logging.info("fcheck: {}".format(fcheck))
                    list_files = pd.DataFrame(run_query(("SELECT f.file_id, "
                                                         "   CASE WHEN check_results = 0 THEN 'OK' "
                                                         "       WHEN check_results = 9 THEN 'Pending' "
                                                         "       WHEN check_results = 1 THEN 'Failed' "
                                                         "       ELSE 'Pending' END as {fcheck} "
                                                         " FROM files f LEFT JOIN files_checks c ON (f.file_id=c.file_id AND c.file_check = %(file_check)s) "
                                                         "  where f.folder_id = %(folder_id)s").format(fcheck=fcheck),
                                                        {'file_check': fcheck, 'folder_id': folder_id}, cur=cur))
                    logging.info("list_files.size: {}".format(list_files.shape[0]))
                    if list_files.shape[0] > 0:
                        folder_files_df = folder_files_df.merge(list_files, how='outer', on='file_id')
                files = folder_files_df
                data[0]['files'] = files.to_dict('records')
        cur.close()
        conn.close()
        return jsonify(data[0])
    else:
        return None


@app.route('/api/files/<file_id>', methods=['GET', 'POST'], strict_slashes=False)
def api_get_file_details(file_id=None):
    """Get the details of a file."""

    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logging.error(e)
        raise InvalidUsage('System error')

    file_id, file_uid = check_file_id(file_id, cur=cur)

    if file_id is None:
        return None

    data = run_query(("SELECT uid as osprey_id, folder_id, file_name, cast(file_timestamp AS DATETIME) as file_timestamp, "
                           "   dams_uan, preview_image, cast(updated_at AS DATETIME) as updated_at, "
                           "   cast(created_at AS DATETIME) as created_at "
                           " FROM files WHERE file_id = %(file_id)s"),
                          {'file_id': file_id}, cur=cur)
    if len(data) == 1:
        filechecks = run_query(
            ("WITH data AS (SELECT settings_value as file_check, %(file_id)s as file_id FROM projects_settings " 
                " WHERE project_setting = 'project_checks' and project_id IN (SELECT project_id FROM folders WHERE folder_id in (SElect folder_id from files where file_id = %(file_id)s ))) "
                 " SELECT f.check_info, CASE WHEN f.check_results IS NULL THEN 9 ELSE f.check_results END as check_results, d.file_check, cast(f.updated_at AS DATETIME) as updated_at " 
                 " FROM data d LEFT JOIN files_checks f ON (d.file_id = f.file_id and d.file_check = f.file_check)"),
            {'file_id': file_id}, cur=cur)
        data[0]['file_checks'] = filechecks
        file_exif = run_query(
            ("SELECT tag, value, filetype, tagid, taggroup, cast(updated_at AS DATETIME) as updated_at "
             " FROM files_exif WHERE file_id = %(file_id)s "
             " UNION "
             " SELECT tag, value, filetype, tagid, taggroup, cast(updated_at AS DATETIME) as updated_at "
             " FROM files_exif_old WHERE file_id = %(file_id)s"),
            {'file_id': file_id}, cur=cur)
        data[0]['exif'] = file_exif
        file_md5 = run_query(("SELECT filetype, md5, cast(updated_at AS DATETIME) as updated_at "
                                   "FROM file_md5 WHERE file_id = %(file_id)s"),
                                  {'file_id': file_id}, cur=cur)
        data[0]['md5_hashes'] = file_md5
        file_links = run_query(
            ("SELECT link_name, link_url, link_notes, cast(updated_at AS DATETIME) as updated_at "
             "FROM files_links WHERE file_id = %(file_id)s"),
            {'file_id': file_id}, cur=cur)
        data[0]['links'] = file_links
        file_post = run_query(
            ("SELECT post_step, post_results, post_info, cast(updated_at AS DATETIME) as updated_at "
             "FROM file_postprocessing WHERE file_id = %(file_id)s"),
            {'file_id': file_id}, cur=cur)
        data[0]['file_postprocessing'] = file_post
        val = jsonify(data[0])
    else:
        val = jsonify(None)
    cur.close()
    conn.close()
    return val


@app.route('/api/reports/<report_id>/', methods=['GET'], strict_slashes=False)
def api_get_report(report_id=None):
    """Get the data from a project report."""
    if report_id is None:
        return None
    else:
        # Connect to db
        try:
            conn = pymysql.connect(host=settings.host,
                                   user=settings.user,
                                   passwd=settings.password,
                                   database=settings.database,
                                   port=settings.port,
                                   charset='utf8mb4',
                                   cursorclass=pymysql.cursors.DictCursor,
                                   autocommit=True)
            cur = conn.cursor()
        except pymysql.Error as e:
            logging.error(e)
            raise InvalidUsage('System error')

        file_name = request.args.get("file_name")
        dams_uan = request.args.get("dams_uan")
        logging.info("file_name: {}".format(file_name))
        logging.info("dams_uan: {}".format(dams_uan))
        query = run_query("SELECT * FROM data_reports WHERE report_id = %(report_id)s",
                               {'report_id': report_id}, cur=cur)
        if len(query) == 0:
            query = run_query("SELECT * FROM data_reports WHERE report_alias = %(report_id)s",
                                   {'report_id': report_id}, cur=cur)
            if len(query) == 0:
                return None
        if file_name is not None and dams_uan is not None:
            return None
        elif file_name is not None and dams_uan is None:
            data = run_query(
                "SELECT * FROM ({}) a WHERE file_name = %(file_name)s".format(query[0]['query_api'].replace('%', '%%')),
                {'file_name': file_name}, cur=cur)
        elif dams_uan is not None and file_name is None:
            data = run_query(
                "SELECT * FROM ({}) a WHERE dams_uan = %(dams_uan)s".format(query[0]['query_api'].replace('%', '%%')),
                {'dams_uan': dams_uan}, cur=cur)
        else:
            data = run_query(query[0]['query_api'], cur=cur)
        cur.close()
        conn.close()
        return jsonify(data)


@cache.memoize()
@app.route('/reports/', methods=['GET'], strict_slashes=False)
def data_reports_form():
    """Report of a project"""
    project_alias = request.values.get("project_alias")
    report_id = request.values.get("report_id")
    return redirect(url_for('data_reports', project_alias=project_alias, report_id=report_id))


@cache.memoize()
@app.route('/reports/<project_alias>/<report_id>/', methods=['GET'], strict_slashes=False)
def data_reports(project_alias=None, report_id=None):
    """Report of a project"""

    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logging.error(e)
        raise InvalidUsage('System error')

    # Declare the login form
    form = LoginForm(request.form)

    if project_alias is None:
        error_msg = "Project is not available."
        return render_template('error.html', form=form, error_msg=error_msg, project_alias=None, site_env=site_env), 404

    # Declare the login form
    form = LoginForm(request.form)

    project_id = run_query(("SELECT project_id FROM projects WHERE project_alias = %(project_alias)s"),
                                {'project_alias': project_alias}, cur=cur)

    if len(project_id) == 0:
        error_msg = "Project was not found."
        return render_template('error.html', form=form, error_msg=error_msg, project_alias=project_id,
                               site_env=site_env, site_net=site_net), 404

    project_id = project_id[0]['project_id']
    project_report = run_query(("SELECT * FROM data_reports WHERE "
                                     " project_id = %(project_id)s AND report_id = %(report_id)s"),
                                    {'project_id': project_id, 'report_id': report_id}, cur=cur)
    if len(project_report) == 0:
        error_msg = "Report was not found."
        cur.close()
        conn.close()
        return render_template('error.html', form=form, error_msg=error_msg, project_alias=project_alias,
                               site_env=site_env, site_net=site_net), 404

    report_data = pd.DataFrame(run_query(project_report[0]['query'], cur=cur))
    report_data_updated = run_query(project_report[0]['query_updated'], cur=cur)[0]['updated_at']
    report = run_query("SELECT * FROM data_reports WHERE report_id = %(report_id)s", {'report_id': report_id}, cur=cur)[0]
    project_info = run_query("SELECT * FROM projects WHERE project_id = %(project_id)s",
                                  {'project_id': project_id}, cur=cur)[0]
    cur.close()
    conn.close()
    return render_template('reports.html',
                           project_id=project_id,
                           project_alias=project_alias,
                           project_info=project_info,
                           report=project_report,
                           tables=[report_data.to_html(table_id='report_data',
                                                       index=False,
                                                       border=0,
                                                       escape=False,
                                                       classes=["display", "compact", "table-striped"])],
                           report_data_updated=report_data_updated,
                           form=form,
                           site_env=site_env,
                           site_net=site_net
                           )


@cache.memoize()
@app.route('/preview_image/<file_id>/', methods=['GET', 'POST'], strict_slashes=False)
def get_preview(file_id=None, max=None):
    """Return image previews"""
    if file_id is None:
        raise InvalidUsage('file_id missing', status_code=400)
    #
    try:
        file_id = int(file_id)
    except:
        try:
            # Allow for UUIDs
            file_id = UUID(file_id)
        except:
            raise InvalidUsage('invalid file_id value', status_code=400)

    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logging.error(e)
        raise InvalidUsage('System error')

    data = run_query("SELECT folder_id FROM files WHERE file_id = %(file_id)s LIMIT 1", {'file_id': file_id}, cur=cur)
    logging.info(data)
    if len(data) == 0:
        filename = "static/na.jpg"
        return send_file(filename, mimetype='image/jpeg')
    else:
        try:
            folder_id = data[0]['folder_id']
            max = request.args.get('max')
            if max is not None:
                width = max
            else:
                width = None
            filename = "image_previews/folder{}/{}.jpg".format(folder_id, file_id)
            if width is not None:
                if os.path.isfile(filename):
                    img_resized = "image_previews/folder{}/{}/{}.jpg".format(folder_id, width, file_id)
                    if os.path.isfile(img_resized):
                        filename = img_resized
                    else:
                        logging.info(filename)
                        img = Image.open(filename)
                        wpercent = (int(width) / float(img.size[0]))
                        hsize = int((float(img.size[1]) * float(wpercent)))
                        img = img.resize((int(width), hsize), Image.LANCZOS)
                        filename = "/tmp/{}_{}.jpg".format(file_id, width)
                        img.save(filename, icc_profile=img.info.get('icc_profile'))
                else:
                    logging.info(filename)
                    filename = "static/na.jpg"
        except:
            filename = "static/na.jpg"
    if not os.path.isfile(filename):
        filename = "static/na.jpg"
    logging.debug("preview_request: {} - {}".format(file_id, filename))

    cur.close()
    conn.close()

    try:
        return send_file(filename, mimetype='image/jpeg')
    except:
        return send_file("static/na.jpg", mimetype='image/jpeg')


@cache.memoize()
@app.route('/barcode_image/<barcode>/', methods=['GET', 'POST'], strict_slashes=False)
def get_barcodeimage(barcode=None):
    """Return image previews using a barcode that has a collex prefix in format: prefix:barcode"""
    if barcode is None:
        raise InvalidUsage('barcode value missing', status_code=400)
    #
    barcode_split = barcode.split(":")
    if len(barcode_split) != 2:
        raise InvalidUsage('Invalid barcode', status_code=400)

    # Connect to db
    try:
        conn = pymysql.connect(host=settings.host,
                               user=settings.user,
                               passwd=settings.password,
                               database=settings.database,
                               port=settings.port,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor,
                               autocommit=True)
        cur = conn.cursor()
    except pymysql.Error as e:
        logging.error(e)
        raise InvalidUsage('System error')

    if barcode_split[0] == 'nmnhbot':
        query = ("SELECT file_id, folder_id, preview_image FROM files "
                 "WHERE file_name = %(file_name)s AND folder_id IN "
                 "(SELECT folder_id FROM folders WHERE project_id in(100,131)) LIMIT 1")
        data = run_query(query, {'file_name': barcode_split[1]}, cur=cur)
        if data is True:
            filename = "static/na.jpg"
            return send_file(filename, mimetype='image/jpeg')
        else:
            data = data[0]
            file_id = data['file_id']
            folder_id = data['folder_id']
            preview_image = data['preview_image']
            logging.info("data: {}".format(data))
            if preview_image is not None:
                redirect(preview_image, code=302)
            else:
                max = request.args.get('max')
                if max is not None:
                    width = max
                else:
                    width = request.args.get('size')
                if width is None:
                    filename = "image_previews/folder{}/{}.jpg".format(folder_id, file_id)
                else:
                    filename = "image_previews/folder{}/{}.jpg".format(folder_id, file_id)
                    if os.path.isfile(filename):
                        img = Image.open(filename)
                        wpercent = (int(width) / float(img.size[0]))
                        hsize = int((float(img.size[1]) * float(wpercent)))
                        img = img.resize((int(width), hsize), Image.LANCZOS)
                        filename = "/tmp/{}_{}.jpg".format(file_id, width)
                        img.save(filename)
                    else:
                        filename = "static/na.jpg"
        if not os.path.isfile(filename):
            logging.info(filename)
            filename = "static/na.jpg"
    logging.debug("barcode_request: {} - {}".format(barcode, filename))
    cur.close()
    conn.close()
    try:
        return send_file(filename, mimetype='image/jpeg')
    except:
        return send_file("static/na.jpg", mimetype='image/jpeg')


#####################################
if __name__ == '__main__':
    app.run(debug=True)
