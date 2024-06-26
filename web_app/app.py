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
from flask import Response
from flask import Blueprint
from flask import send_from_directory

from cache import cache
# Logging
from logger import logger
from osprey_api import osprey_api
from osprey_common import *

import os
import locale
import math
import pandas as pd
import json
import time
from datetime import datetime
from PIL import Image
from PIL import ImageFilter
from PIL import ImageFont
from PIL import ImageDraw
from uuid import UUID

from time import strftime
from time import localtime

# MySQL
import mysql.connector

# Flask Login
from flask_login import LoginManager
from flask_login import login_required
from flask_login import login_user
from flask_login import logout_user
from flask_login import UserMixin
from flask_login import current_user

from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms import PasswordField
from wtforms.validators import DataRequired

import settings

logger.info("site_ver = {}".format(site_ver))
logger.info("site_env = {}".format(site_env))
logger.info("site_net = {}".format(site_net))

# Set locale for number format
locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')

# Remove DecompressionBombWarning due to large files
# by using a large threshold
# https://github.com/zimeon/iiif/issues/11
Image.MAX_IMAGE_PIXELS = 1000000000

app = Flask(__name__)
app.secret_key = settings.secret_key

# Minify responses
if site_env == "prod":
    from flask_minify import Minify
    Minify(app=app, html=True, js=True, cssless=True)

# Add logger
app.logger.addHandler(logger)

# Setup cache
cache.init_app(app)

# Disable strict trailing slashes
app.url_map.strict_slashes = False

# Add blueprints
app.register_blueprint(osprey_api)

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
    logger.error(e)
    error_msg = "Error: {}".format(e)
    return render_template('error.html', error_msg=error_msg, 
                           project_alias=None, site_env=site_env, site_net=site_net, site_ver=site_ver), 404


@app.errorhandler(500)
def sys_error(e):
    logger.error(e)
    error_msg = "System error: {}".format(e)
    return render_template('error.html', error_msg=error_msg, 
                           project_alias=None, site_env=site_env, site_net=site_net, site_ver=site_ver), 500


def validate_api_key(api_key, cur=None):
    logger.info("api_key: {}".format(api_key))
    try:
        api_key_check = UUID(api_key)
    except ValueError:
        logger.info("Invalid UUID: {}".format(api_key))
        return False
    # Run query
    query = ("SELECT api_key from api_keys WHERE api_key = %(api_key)s")
    parameters = {'api_key': api_key}
    logger.info("query: {}".format(query))
    logger.info("parameters: {}".format(parameters))
    result = cur.execute(query, parameters)
    data = cur.fetchall()
    if len(data) == 1:
        if data[0]['api_key'] == api_key:
            return True
        else:
            return False
    else:
        return False


def run_query(query, parameters=None, return_val=True, cur=None):
    logger.info("parameters: {}".format(parameters))
    logger.info("query: {}".format(query))
    # Run query
    try:
        if parameters is None:
            results = cur.execute(query)
        else:
            results = cur.execute(query, parameters)
    except mysql.connector.Error as error:
        logger.error("Error: {}".format(error))
        raise InvalidUsage(error, status_code=500)
    if return_val:
        data = cur.fetchall()
        logger.info("No of results: ".format(len(data)))
        return data
    else:
        return True


def query_database_insert(query, parameters, return_res=False, cur=None):
    logger.info("query: {}".format(query))
    logger.info("parameters: {}".format(parameters))
    # Run query
    data = False
    try:
        results = cur.execute(query, parameters)
    except Exception as error:
        logger.error("Error: {}".format(error))
        return False
    data = cur.fetchall()
    logger.info("No of results: ".format(len(data)))
    if len(data) == 0:
        data = False
    return data


def query_database_insert_multi(query, parameters, return_res=False, cur=None):
    logger.info("query: {}".format(query))
    logger.info("parameters: {}".format(parameters))
    # Run query
    data = False
    try:
        results = cur.executemany(query, parameters)
    except Exception as error:
        logger.error("Error_insert_multi: {}".format(error))
        return False
    data = cur.fetchall()
    logger.info("No of results: ".format(len(data)))
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


@cache.memoize()
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
        conn = mysql.connector.connect(host=settings.host,
                                user=settings.user,
                                password=settings.password,
                                database=settings.database,
                                port=settings.port, autocommit=True)
        conn.time_zone = '-04:00'
        cur = conn.cursor(dictionary=True)
    # except mysql.connector.Error as e:
    except mysql.connector.Error as e:
        logger.error(e)
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
        try:
            conn = mysql.connector.connect(host=settings.host,
                                    user=settings.user,
                                    password=settings.password,
                                    database=settings.database,
                                    port=settings.port, autocommit=True)
            conn.time_zone = '-04:00'
            cur = conn.cursor(dictionary=True)
        except mysql.connector.Error as err:
            logger.error(err)
            return jsonify({'error': 'API error'}), 500
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
    try:
        conn = mysql.connector.connect(host=settings.host,
                                user=settings.user,
                                password=settings.password,
                                database=settings.database,
                                port=settings.port, autocommit=True)
        conn.time_zone = '-04:00'
        cur = conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        logger.error(err)
        return jsonify({'error': 'API error'}), 500
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
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                          'favicon.ico',mimetype='image/vnd.microsoft.icon')


@cache.memoize()
@app.route('/team/<team>', methods=['GET', 'POST'], provide_automatic_options=False)
@app.route('/', methods=['GET', 'POST'], provide_automatic_options=False)
def homepage(team=None):
    """Main homepage for the system"""
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
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

    try:
        conn = mysql.connector.connect(host=settings.host,
                                user=settings.user,
                                password=settings.password,
                                database=settings.database,
                                port=settings.port, autocommit=True)
        conn.time_zone = '-04:00'
        cur = conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        logger.error(err)
        return jsonify({'error': 'API error'}), 500
    # check if both http method is POST and form is valid on submit
    if form.validate_on_submit():

        # assign form data to variables
        username = request.form.get('username', '', type=str)
        password = request.form.get('password', '', type=str)
        query = "SELECT user_id, username, user_active, full_name FROM users WHERE username = %(username)s AND pass = MD5(%(password)s)"
        user = run_query(query, {'username': username.lower(), 'password': password}, cur=cur)
        logger.info(user)
        if len(user) == 1:
            logger.info(user[0]['user_active'])
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

    if team is None:
        team = "summary"
        team_heading = "Collections Digitization - Highlights"
        html_title = "Collections Digitization Dashboard"

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
        team_heading = "Summary of Mass Digitization Team Projects"
        html_title = "Mass Digitization Team Projects, Collections Digitization"

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
        team_heading = "Summary of Imaging Services Team Projects"
        html_title = "Imaging Services Team Projects, Collections Digitization"
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
        team_heading = "Summary of Informatics Team Projects"
        html_title = "Summary of the Informatics Team Projects, Collections Digitization"
        # IS stats
        summary_stats = {
            'digitization_projects': "{:,}".format(
                        run_query(
                            "SELECT COUNT(*) as total "
                            "FROM projects_informatics", cur=cur)[0]['total']),
            'active_projects': "{:,}".format(run_query(("SELECT COUNT(*) as total "
                            "FROM projects_informatics WHERE project_status='Ongoing'"),
                           cur=cur)[0]['total']),
            'records': "{:,}".format(run_query(("SELECT SUM(records) as total "
                          " FROM projects_informatics WHERE records_redundant IS False"),
                         cur=cur)[0]['total'])
        }

    section_query = (" SELECT "
                     " p.projects_order, "
                     " CONCAT('<abbr title=\"', u.unit_fullname, '\" class=\"bg-white\">', p.project_unit, '</abbr>') as project_unit, "
                     " CASE WHEN p.project_alias IS NULL THEN p.project_title ELSE CONCAT('<a href=\"/dashboard/', p.project_alias, '\" class=\"bg-white\">', p.project_title, '</a>') END as project_title, "
                     " p.project_status, "
                     " p.project_manager, "
                     " CASE "
                     "      WHEN p.project_end IS NULL THEN CONCAT(date_format(p.project_start, '%d %b %Y'), ' -') "
                     "      WHEN p.project_start = p.project_end THEN date_format(p.project_start, '%d %b %Y') "                     
                     "      WHEN date_format(p.project_start, '%Y-%c') = date_format(p.project_end, '%Y-%c') "
                     "          THEN CONCAT(date_format(p.project_start, '%d'), ' - ', date_format(p.project_end, '%d %b %Y')) "
                     "      WHEN date_format(p.project_start, '%Y') = date_format(p.project_end, '%Y') "
                     "          THEN CONCAT(date_format(p.project_start, '%d %b'), ' - ', date_format(p.project_end, '%d %b %Y')) "
                     "      ELSE CONCAT(date_format(p.project_start, '%d %b %Y'), ' - ', date_format(p.project_end, '%d %b %Y')) END "
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
    list_projects_md = list_projects_md.drop("images_public", axis=1)
    list_projects_md = list_projects_md.rename(columns={
        "project_unit": "Unit",
        "project_title": "Title",
        "project_status": "Status",
        "project_manager": "<abbr title=\"Project Manager\" class=\"bg-white\">PM</abbr>",
        "project_dates": "Dates",
        # "project_progress": "Project Progress<sup>*</sup>",
        "objects_digitized": "Specimens/Objects Digitized",
        "images_taken": "Images Captured"#,
        # "images_public": "Public Images"
    })

    list_projects_is = pd.DataFrame(run_query(section_query, {'section': 'IS'}, cur=cur))
    list_projects_is = list_projects_is.drop("images_public", axis=1)
    list_projects_is = list_projects_is.rename(columns={
        "project_unit": "Unit",
        "project_title": "Title",
        "project_status": "Status",
        "project_manager": "<abbr title=\"Project Manager\" class=\"bg-white\">PM</abbr>",
        "project_dates": "Dates",
        # "project_progress": "Project Progress<sup>*</sup>",
        "objects_digitized": "Specimens/Objects Digitized",
        "images_taken": "Images Captured"#,
        # "images_public": "Public Images"
    })


    # Informatics Table
    inf_section_query = (" SELECT "
                     " CONCAT('<abbr title=\"', u.unit_fullname, '\">', p.project_unit, '</abbr>') as project_unit, "
                     " CONCAT('<strong>', p.project_title, '</strong><br>', p.summary) as project_title, "
                     " p.project_status, "
                     " CASE WHEN p.github_link IS NULL THEN 'NA' ELSE "
                     "       CONCAT('<a href=\"', p.github_link, '\" title=\"Link to code repository of ', p.project_title, ' in Github\">Repository</a>') END as github_link, "
                     " CASE "
                     "      WHEN p.project_end IS NULL THEN CONCAT(date_format(p.project_start, '%b %Y'), ' -') "
                     "      WHEN date_format(p.project_start, '%b %Y') = date_format(p.project_end, '%b %Y') THEN date_format(p.project_start, '%b %Y') "                     
                     "      ELSE CONCAT(date_format(p.project_start, '%b %Y'), ' - ', date_format(p.project_end, '%b %Y')) END "
                     "         as project_dates, "
                     " CASE WHEN p.records = 0 THEN 'NA' ELSE "
                     " (CASE WHEN p.records_estimated IS True THEN CONCAT(coalesce(format(p.records, 0), 0), '*') ELSE "
                     "      coalesce(format(p.records, 0), 0) END) END as records, "
                     " CASE WHEN p.info_link IS NULL THEN 'NA' ELSE p.info_link END AS info_link "
                     " FROM projects_informatics p LEFT JOIN si_units u ON (p.project_unit = u.unit_id) "
                     " ORDER BY p.project_start DESC, p.project_end DESC")
    list_projects_inf = pd.DataFrame(run_query(inf_section_query, cur=cur))
    list_projects_inf = list_projects_inf.rename(columns={
        "project_unit": "Unit",
        "project_title": "Title",
        "project_status": "Status",
        "github_link": "Repository",
        "info_link": "More Info",
        "project_manager": "<abbr title=\"Project Manager\">PM</abbr>",
        "project_dates": "Dates",
        "records": "Records Created or Enhanced"
    })

    # Informatics Software
    inf_software = ("SELECT CONCAT('<strong>', software_name, '</strong>') as software_name, software_details, "
                    " CONCAT('<a href=\"', repository, '\" title=\"Link to code repository in Github\"><img src=\"/static/github-32.png\" alt=\"Github Logo\"></a>') as repository, "
                    " CONCAT('<a href=\"', more_info, '\" title=\"Link to a page with more information about the software\">More Info</a>') as more_info "
                    " FROM informatics_software ORDER BY sortby DESC")
    list_software = pd.DataFrame(run_query(inf_software, cur=cur))
    list_software = list_software.rename(columns={
        "software_name": "Software",
        "software_details": "Details",
        "repository": "Repository",
        "more_info": "Details"
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
                           summary_stats=summary_stats,
                           team=team,
                           tables_md=[list_projects_md.to_html(table_id='list_projects_md', index=False,
                                                               border=0, escape=False,
                                                               classes=["display", "w-100"])],
                           tables_is=[list_projects_is.to_html(table_id='list_projects_is', index=False,
                                                               border=0, escape=False,
                                                               classes=["display", "w-100"])],
                           tables_inf=[list_projects_inf.to_html(table_id='list_projects_inf', index=False,
                                                               border=0, escape=False,
                                                               classes=["display", "w-100"])],
                           tables_software=[list_software.to_html(table_id='list_software', index=False,
                                                               border=0, escape=False,
                                                               classes=["display", "w-100"])],
                           asklogin=True,
                           site_env=site_env,
                           site_net=site_net,
                           site_ver=site_ver,
                           last_update=last_update[0]['updated_at'],
                           kiosk=kiosk,
                           user_address=user_address,
                           team_heading=team_heading,
                           html_title=html_title,
                           analytics_code=settings.analytics_code                           
                           )


@app.route('/team/', methods=['POST', 'GET'], provide_automatic_options=False)
def empty_team():
    return redirect(url_for('homepage'))


@cache.memoize()
@app.route('/dashboard/', methods=['GET'], provide_automatic_options=False)
def dashboard_empty():
    return redirect(url_for('homepage'))


@cache.memoize()
@app.route('/dashboard/<project_alias>/<folder_id>/<tab>/<page>/', methods=['POST', 'GET'], provide_automatic_options=False)
@app.route('/dashboard/<project_alias>/<folder_id>/<tab>/', methods=['POST', 'GET'], provide_automatic_options=False)
@app.route('/dashboard/<project_alias>/<folder_id>/', methods=['POST', 'GET'], provide_automatic_options=False)
def dashboard_f(project_alias=None, folder_id=None, tab=None, page=None):
    """Dashboard for a project"""

    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))

    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Declare the login form
    form = LoginForm(request.form)

    try:
        folder_id = int(folder_id)
    except ValueError:
        error_msg = "Invalid folder ID"
        return render_template('error.html', error_msg=error_msg,
                                project_alias=project_alias, site_env=site_env, site_net=site_net,
                                analytics_code=settings.analytics_code), 400

    # Tab
    if tab is None or tab == '':
        tab = "filechecks"
    else:
        if tab not in ['filechecks', 'lightbox', 'postprod']:
            error_msg = "Invalid tab ID."
            return render_template('error.html', error_msg=error_msg,
                                project_alias=project_alias, site_env=site_env, site_net=site_net, site_ver=site_ver,
                                analytics_code=settings.analytics_code), 400

    # Page
    if page is None or page == '':
        page = 1
    else:
        try:
            page = int(page)
        except:
            error_msg = "Invalid page number."
            return render_template('error.html', error_msg=error_msg,
                                   project_alias=project_alias, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 400

    # Connect to db
    try:
        conn = mysql.connector.connect(host=settings.host,
                                user=settings.user,
                                password=settings.password,
                                database=settings.database,
                                port=settings.port, autocommit=True)
        conn.time_zone = '-04:00'
        cur = conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        logger.error(err)
        return jsonify({'error': 'API error'}), 500

    # Check if project exists
    if project_alias_exists(project_alias, cur=cur) is False:
        error_msg = "Project was not found."
        return render_template('error.html', error_msg=error_msg,
                                project_alias=project_alias, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404

    project_id_check = run_query("SELECT project_id FROM projects WHERE project_alias = %(project_alias)s",
                                      {'project_alias': project_alias}, cur=cur)
    if len(project_id_check) == 0:
        error_msg = "Project was not found."
        return render_template('error.html', error_msg=error_msg,
                               project_alias=project_alias, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404
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
        return render_template('error.html', error_msg=error_msg,
                               project_alias=project_alias, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404

    project_stats = {}
    if project_alias is None:
        error_msg = "Project is not available."
        return render_template('error.html', error_msg=error_msg,
                               project_alias=project_alias, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404

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
        logger.info("project_admin: {} - {}".format(username, project_admin))
    else:
        project_admin = False
    project_info = run_query("SELECT *, "
                             "      CONCAT(date_format(project_start, '%d-%b-%Y'), "
                             "          CASE WHEN project_end IS NULL THEN '' ELSE CONCAT(' to ', date_format(project_end, '%d-%b-%Y')) END "
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

    if tab == "filechecks":
        filechecks_list_temp = run_query(
            ("SELECT settings_value as file_check FROM projects_settings "
             " WHERE project_setting = 'project_checks' and project_id = %(project_id)s"),
            {'project_id': project_info['project_id']}, cur=cur)
        filechecks_list = []
        for fcheck in filechecks_list_temp:
            filechecks_list.append(fcheck['file_check'])
        logger.info("filechecks_list:{}".format(filechecks_list_temp))
        project_postprocessing = []

    if tab == "postprod":
        project_postprocessing_temp = run_query(
            ("SELECT settings_value as file_check FROM projects_settings "
             " WHERE project_setting = 'project_postprocessing' and project_id = %(project_id)s ORDER BY table_id"),
            {'project_id': project_info['project_id']}, cur=cur)
        project_postprocessing = []
        if project_postprocessing_temp is not None:
            for fcheck in project_postprocessing_temp:
                project_postprocessing.append(fcheck['file_check'])
        filechecks_list = []
    project_statistics = run_query(("SELECT * FROM projects_stats WHERE project_id = %(project_id)s"), {'project_id': project_id}, cur=cur)[0]
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
    project_stats_other = run_query(("SELECT other_icon, other_name, COALESCE(other_stat, 0) as other_stat FROM projects_stats WHERE project_id = %(project_id)s"), {'project_id': project_id}, cur=cur)[0]
    project_stats_other['other_stat'] = format(int(project_stats_other['other_stat']), ',d')

    project_folders_badges = run_query("SELECT b.folder_id, b.badge_type, b.badge_css, b.badge_text FROM folders_badges b, folders f WHERE b.folder_id = f.folder_id and f.project_id = %(project_id)s and b.badge_type != 'no_files'", {'project_id': project_id}, cur=cur)
    folder_name = None
    folder_qc = {
        'qc_status': "QC Pending",
        'qc_by': "",
        'updated_at': "",
        'qc_ip': ""
    }
    files_df = ""
    folder_files_df = pd.DataFrame()
    post_processing_df = pd.DataFrame()
    files_count = ""
    pagination_html = ""
    folder_stats = {
        'no_files': 0,
        'no_errors': 0
    }
    qc_check = ""
    qc_details = pd.DataFrame()
    qc_folder_info = ""

    if folder_id is not None and folder_id != '':
        folder_name = run_query(("SELECT project_folder FROM folders "
                                 "WHERE folder_id = %(folder_id)s and project_id = %(project_id)s"),
                                     {'folder_id': folder_id, 'project_id': project_id}, cur=cur)
        logger.info("folder_name: {}".format(len(folder_name)))
        if len(folder_name) == 0:
            error_msg = "Folder does not exist in this project."
            return render_template('error.html', error_msg=error_msg, project_alias=project_alias,
                                   site_env=site_env, site_net=site_net, site_ver=site_ver), 404
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
                                 "WITH data AS (SELECT f.file_id, CONCAT('/preview_image/', f.file_id, '/?') as preview_image, "
                                 "         f.preview_image as preview_image_ext, f.folder_id, f.file_name, "
                                 "               COALESCE(s.sensitive_contents, 0) as sensitive_contents "
                                 "           FROM files f LEFT JOIN sensitive_contents s ON f.file_id = s.file_id "
                                 " WHERE f.folder_id = %(folder_id)s)"
                                 " SELECT file_id, preview_image, preview_image_ext, folder_id, file_name, sensitive_contents "
                                 " FROM data "
                                 " ORDER BY file_name "
                                 "LIMIT {no_items} OFFSET {offset}").format(offset=offset, no_items=no_items),
                             {'folder_id': folder_id}, cur=cur)
        files_count = run_query("SELECT count(*) as no_files FROM files WHERE folder_id = %(folder_id)s",
                                {'folder_id': folder_id}, cur=cur)[0]
        files_count = files_count['no_files']

        if tab == "filechecks":
            page_no = "File Checks"
            if files_count == 0:
                folder_files_df = pd.DataFrame()
                pagination_html = ""
                files_df = ""
                files_count = ""
                folder_stats = {
                    'no_files': 0,
                    'no_errors': 0
                }

            else:
                for fcheck in filechecks_list:
                    logger.info("fcheck: {}".format(fcheck))
                    list_files = pd.DataFrame(run_query(("SELECT f.file_id, "
                                                              "   CASE WHEN check_results = 0 THEN 'OK' "
                                                              "       WHEN check_results = 9 THEN 'Pending' "
                                                              "       WHEN check_results = 1 THEN 'Failed' "
                                                              "       ELSE 'Pending' END as {fcheck} "
                                                              " FROM files f LEFT JOIN files_checks c ON (f.file_id=c.file_id AND c.file_check = %(file_check)s) "
                                                              "  where f.folder_id = %(folder_id)s").format(fcheck=fcheck),
                                                             {'file_check': fcheck, 'folder_id': folder_id}, cur=cur))
                    logger.info("list_files.size: {}".format(list_files.shape[0]))
                    if list_files.shape[0] > 0:
                        folder_files_df = folder_files_df.merge(list_files, how='outer', on='file_id')
                preview_files = pd.DataFrame(run_query(("SELECT f.file_id, "
                                                             "  CASE WHEN f.preview_image is NULL THEN CONCAT('/preview_image/', f.file_id, '/?') ELSE f.preview_image END as preview_image "
                                                             " FROM files f where f.folder_id = %(folder_id)s"),
                                                            {'folder_id': folder_id}, cur=cur))
                folder_files_df = folder_files_df.sort_values(by=['file_name'])
                folder_files_df = folder_files_df.sort_values(by=filechecks_list)
                folder_files_df = folder_files_df.merge(preview_files, how='outer', on='file_id')
                folder_files_df['file_name'] = '<a href="/file/' \
                                               + folder_files_df['file_id'].astype(str) + '/" title="Details of File ' + folder_files_df['file_name'].astype(str) + '">' \
                                               + folder_files_df['file_name'].astype(str) \
                                               + '</a> ' \
                                               + '<button type="button" class="btn btn-light btn-sm" ' \
                                               + 'data-bs-toggle="modal" data-bs-target="#previewmodal1" ' \
                                               + 'data-bs-info="' + folder_files_df['preview_image'] \
                                               + '&max=1200" data-bs-link = "/file/' + folder_files_df['file_id'].astype(str) \
                                               + '" data-bs-text = "Details of the file ' + folder_files_df[
                                                   'file_name'].astype(str) \
                                               + '" title="Image Preview of ' + folder_files_df['file_name'].astype(str) + '">' \
                                               + '<i class="fa-regular fa-image"></i></button>'
                folder_files_df = folder_files_df.drop(['file_id'], axis=1)
                folder_files_df = folder_files_df.drop(['preview_image'], axis=1)


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
                post_processing_df = pd.DataFrame()
        elif tab == "lightbox":
            page_no = "Lightbox Page {}".format(page)
            # Pagination
            pagination_html = "<nav aria-label=\"pages\"><ul class=\"pagination float-end\">"
            no_pages = math.ceil(files_count / no_items)
            logger.info("no_pages: {}".format(no_pages))
            if page == 1:
                pagination_html = pagination_html + "<li class=\"page-item disabled\"><a class=\"page-link\" href=\"#\" " \
                                                    "tabindex=\"-1\">Previous</a></li>"
            else:
                pagination_html = pagination_html + "<li class=\"page-item\"><a class=\"page-link\" " \
                                                    "href=\"" + url_for('dashboard_f', project_alias=project_alias,
                                                                        folder_id=folder_id, tab="lightbox",
                                                                        page="{}".format(page - 1)) \
                                  + "\">Previous</a></li>"
            # Ellipsis for first pages
            if page > 5:
                pagination_html = pagination_html + "<li class=\"page-item\"><a class=\"page-link\" " \
                                  + "href=\"" + url_for('dashboard_f', project_alias=project_alias, folder_id=folder_id,
                                                        tab="lightbox", page="1") \
                                  + "\">1</a></li>"
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
                                      + url_for('dashboard_f', project_alias=project_alias, folder_id=folder_id,
                                                tab="lightbox", page="{}".format(i)) \
                                      + "\">{}</a>".format(i) \
                                      + "</li>"
            if (no_pages - page) > 4:
                pagination_html = pagination_html + "<li class=\"page-item disabled\"><a class=\"page-link\" " \
                                                    "href=\"#\">...</a></li>"
                pagination_html = pagination_html + "<li class=\"page-item\"><a class=\"page-link\" " \
                                  + "href=\"" + url_for('dashboard_f', project_alias=project_alias, folder_id=folder_id,
                                                        tab="lightbox", page="{last}".format(last=no_pages)) \
                                  + "\">{last}</a></li>".format(last=no_pages)
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
                                                            folder_id=folder_id, tab="lightbox",
                                                            page="{}".format(page + 1)) \
                                      + "\">" \
                                      + "Next</a></li>"
            pagination_html = pagination_html + "</ul></nav>"
        elif tab == "postprod":
            page_no = "Post-Processing Steps"
            folder_files_df = pd.DataFrame()
            post_processing_df = pd.DataFrame(run_query(("SELECT file_id, file_name FROM files "
                                                  " WHERE folder_id = %(folder_id)s ORDER BY file_name"),
                                                 {'folder_id': folder_id}, cur=cur))
            logger.info("project_postprocessing {}".format(project_postprocessing))
            post_processing_df['file_name'] = '<a href="/file/' \
                                              + post_processing_df['file_id'].astype(str) + '/" title="File Details">' \
                                              + post_processing_df['file_name'].astype(str) \
                                              + '</a>'
            if len(project_postprocessing) > 0:
                for fcheck in project_postprocessing:
                    logger.info("fcheck: {}".format(fcheck))
                    list_files = pd.DataFrame(run_query(("SELECT f.file_id, "
                                                              "   CASE WHEN post_results = 0 THEN 'Completed' "
                                                              "       WHEN post_results = 9 THEN 'Pending' "
                                                              "       WHEN post_results = 1 THEN 'Failed' "
                                                              "       ELSE 'Pending' END as {fcheck} "
                                                              " FROM files f LEFT JOIN file_postprocessing c ON (f.file_id=c.file_id AND c.post_step = %(file_check)s) "
                                                              "  where f.folder_id = %(folder_id)s").format(
                        fcheck=fcheck),
                                                             {'file_check': fcheck, 'folder_id': folder_id}, cur=cur))
                    logger.info("list_files.size: {}".format(list_files.shape[0]))
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
    logger.info("folder_links: {}".format(folder_links))

    # Reports
    reports = run_query("SELECT * FROM data_reports WHERE project_id = %(project_id)s ORDER BY report_title_brief",
                             {'project_id': project_id}, cur=cur)

    if len(reports) > 0:
        proj_reports = True
    else:
        proj_reports = False

    if tab == "filechecks":
        qc_check = run_query("SELECT * FROM qc_files WHERE folder_id = %(folder_id)s AND file_qc != 0",
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
            qc_folder_info = run_query(("SELECT qc_info from qc_folders where folder_id = %(folder_id)s"),
                                {'folder_id': folder_id}, cur=cur)
            qc_folder_info=qc_folder_info[0]['qc_info']
        else:
            qc_check = False
            qc_details = pd.DataFrame()
            qc_folder_info = ""

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

    # Last update for folder
    fol_last_update = run_query("SELECT date_format(updated_at, '%Y-%b-%d %T') as last_updated FROM folders where folder_id = %(folder_id)s", {'folder_id': folder_id}, cur=cur)[0]['last_updated']

    cur.close()
    conn.close()

    # kiosk mode
    kiosk, user_address = kiosk_mode(request, settings.kiosks)

    # Add sort to show Failed tests at the top
    # Sort by filename first
    files_table_sort = "[0, 'asc']"
    
    no_cols = folder_files_df.shape[1]
    i = 1
    while i < no_cols:
        if 'Failed' in folder_files_df.iloc[:, i].values:
            files_table_sort = "[{}, 'asc']".format(i)
        i += 1

    return render_template('dashboard.html',
                           fol_last_update=fol_last_update,
                           page_no=page_no,
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
                           page=page,
                           files_count=files_count,
                           pagination_html=pagination_html,
                           folder_stats=folder_stats,
                           post_processing=[post_processing_df.to_html(table_id='post_processing_table',
                                                       index=False,
                                                       border=0,
                                                       escape=False,
                                                       classes=["display", "compact", "table-striped", "w-100"])],
                           postproc_data=(project_info['project_postprocessing'] != ""),
                           post_processing_rows=post_processing_df.shape[0],
                           folder_links=folder_links,
                           project_folders_badges=project_folders_badges,
                           form=form,
                           proj_reports=proj_reports,
                           reports=reports,
                           site_env=site_env,
                           site_net=site_net,
                           site_ver=site_ver,
                           kiosk=kiosk,
                           user_address=user_address,
                           qc_check=qc_check,
                           qc_folder_info=qc_folder_info,
                           qc_details=[qc_details.to_html(table_id='qc_details_table',
                                                       index=False,
                                                       border=0,
                                                       escape=False,
                                                       classes=["display", "compact", "table-striped", "w-100"])],
                           project_disk=project_disk,
                           projects_links=projects_links,
                           project_manager_link=project_manager_link,
                           analytics_code=settings.analytics_code,
                           project_stats_other=project_stats_other,
                           files_table_sort=files_table_sort
                           )



@cache.memoize()
@app.route('/dashboard_ajax/<project_alias>/<folder_id>/', methods=['POST', 'GET'], provide_automatic_options=False)
def dashboard_f_ajax(project_alias=None, folder_id=None, tab=None, page=None):
    """Dashboard for a project"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Declare the login form
    form = LoginForm(request.form)

    try:
        folder_id = int(folder_id)
    except ValueError:
        error_msg = "Invalid folder ID"
        return render_template('error.html', error_msg=error_msg,
                               project_alias=project_alias, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 400

    # Tab
    if tab is None or tab == '':
        tab = "filechecks"
    else:
        if tab not in ['filechecks', 'lightbox', 'postprod']:
            error_msg = "Invalid tab ID."
            return render_template('error.html', error_msg=error_msg,
                                   project_alias=project_alias, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 400

    # Page
    if page is None or page == '':
        page = 1
    else:
        try:
            page = int(page)
        except:
            error_msg = "Invalid page number."
            return render_template('error.html', error_msg=error_msg,
                                   project_alias=project_alias, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 400

    # Connect to db
    try:
        conn = mysql.connector.connect(host=settings.host,
                                user=settings.user,
                                password=settings.password,
                                database=settings.database,
                                port=settings.port, autocommit=True)
        conn.time_zone = '-04:00'
        cur = conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        logger.error(err)
        return jsonify({'error': 'API error'}), 500

    # Check if project exists
    if project_alias_exists(project_alias, cur=cur) is False:
        error_msg = "Project was not found."
        return render_template('error.html', error_msg=error_msg,
                                project_alias=project_alias, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404

    project_id_check = run_query("SELECT project_id FROM projects WHERE project_alias = %(project_alias)s",
                                      {'project_alias': project_alias}, cur=cur)
    if len(project_id_check) == 0:
        error_msg = "Project was not found."
        return render_template('error.html', error_msg=error_msg,
                               project_alias=project_alias, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404
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
        return render_template('error.html', error_msg=error_msg,
                               project_alias=project_alias, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404

    project_stats = {}
    if project_alias is None:
        error_msg = "Project is not available."
        return render_template('error.html', error_msg=error_msg,
                               project_alias=project_alias, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404

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
        logger.info("project_admin: {} - {}".format(username, project_admin))
    else:
        project_admin = False
    project_info = run_query("SELECT *, "
                             "      CONCAT(date_format(project_start, '%d-%b-%Y'), "
                             "          CASE WHEN project_end IS NULL THEN '' ELSE CONCAT(' to ', date_format(project_end, '%d-%b-%Y')) END "
                             "          ) as pdates "
                             " FROM projects WHERE project_alias = %(project_alias)s",
                                  {'project_alias': project_alias}, cur=cur)[0]

    project_managers = run_query("SELECT project_manager FROM projects WHERE project_alias = %(project_alias)s",
                                  {'project_alias': project_alias}, cur=cur)[0]

    project_manager_link = project_managers['project_manager']
    if project_managers['project_manager'] == "Jeanine Nault":
        project_manager_link = "<a href=\"https://dpo.si.edu/jeanine-nault\" class=\"bg-white\" title=\"Link to Jeanine Nault's staff page\">Jeanine Nault</a>"
    elif project_managers['project_manager'] == "Nathan Ian Anderson":
        project_manager_link = "<a href=\"https://dpo.si.edu/nathan-ian-anderson\" class=\"bg-white\" title=\"Link to Nathan Ian Anderson's staff page\">Nathan Ian Anderson</a>"
    elif project_managers['project_manager'] == "Erin M. Mazzei":
        project_manager_link = "<a href=\"https://dpo.si.edu/erin-mazzei\" class=\"bg-white\" title=\"Link to Erin M. Mazzei's staff page\">Erin M. Mazzei</a>"

    projects_links = run_query("SELECT * FROM projects_links WHERE project_id = %(project_id)s ORDER BY table_id",
                                  {'project_id': project_info['project_id']}, cur=cur)

    if tab == "filechecks":
        filechecks_list_temp = run_query(
            ("SELECT settings_value as file_check FROM projects_settings "
             " WHERE project_setting = 'project_checks' and project_id = %(project_id)s"),
            {'project_id': project_info['project_id']}, cur=cur)
        filechecks_list = []
        for fcheck in filechecks_list_temp:
            filechecks_list.append(fcheck['file_check'])
        logger.info("filechecks_list:{}".format(filechecks_list_temp))
        project_postprocessing = []

    if tab == "postprod":
        project_postprocessing_temp = run_query(
            ("SELECT settings_value as file_check FROM projects_settings "
             " WHERE project_setting = 'project_postprocessing' and project_id = %(project_id)s ORDER BY table_id"),
            {'project_id': project_info['project_id']}, cur=cur)
        project_postprocessing = []
        if project_postprocessing_temp is not None:
            for fcheck in project_postprocessing_temp:
                project_postprocessing.append(fcheck['file_check'])
        filechecks_list = []
    project_statistics = run_query(("SELECT * FROM projects_stats WHERE project_id = %(project_id)s"), {'project_id': project_id}, cur=cur)[0]
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
    files_df = ""
    folder_files_df = pd.DataFrame()
    post_processing_df = pd.DataFrame()
    files_count = ""
    pagination_html = ""
    folder_stats = {
        'no_files': 0,
        'no_errors': 0
    }
    qc_check = ""
    qc_details = pd.DataFrame()

    if folder_id is not None and folder_id != '':
        folder_name = run_query(("SELECT project_folder FROM folders "
                                 "WHERE folder_id = %(folder_id)s and project_id = %(project_id)s"),
                                     {'folder_id': folder_id, 'project_id': project_id}, cur=cur)
        logger.info("folder_name: {}".format(len(folder_name)))
        if len(folder_name) == 0:
            error_msg = "Folder does not exist in this project."
            return render_template('error.html', error_msg=error_msg, project_alias=project_alias,
                                   site_env=site_env, site_net=site_net, site_ver=site_ver), 404
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
                                 "WITH data AS (SELECT file_id, CONCAT('/preview_image/', file_id, '/?') as preview_image, "
                                 "         preview_image as preview_image_ext, folder_id, file_name FROM files "
                                 "WHERE folder_id = %(folder_id)s)"
                                 " SELECT file_id, preview_image, preview_image_ext, folder_id, file_name"
                                 " FROM data "
                                 " ORDER BY file_name "
                                 "LIMIT {no_items} OFFSET {offset}").format(offset=offset, no_items=no_items),
                             {'folder_id': folder_id}, cur=cur)
        files_count = run_query("SELECT count(*) as no_files FROM files WHERE folder_id = %(folder_id)s",
                                {'folder_id': folder_id}, cur=cur)[0]
        files_count = files_count['no_files']

        if tab == "filechecks":
            page_no = "File Checks"
            if files_count == 0:
                folder_files_df = pd.DataFrame()
                pagination_html = ""
                files_df = ""
                files_count = ""
                folder_stats = {
                    'no_files': 0,
                    'no_errors': 0
                }

            else:
                for fcheck in filechecks_list:
                    logger.info("fcheck: {}".format(fcheck))
                    list_files = pd.DataFrame(run_query(("SELECT f.file_id, "
                                                              "   CASE WHEN check_results = 0 THEN 'OK' "
                                                              "       WHEN check_results = 9 THEN 'Pending' "
                                                              "       WHEN check_results = 1 THEN 'Failed' "
                                                              "       ELSE 'Pending' END as {fcheck} "
                                                              " FROM files f LEFT JOIN files_checks c ON (f.file_id=c.file_id AND c.file_check = %(file_check)s) "
                                                              "  where f.folder_id = %(folder_id)s").format(fcheck=fcheck),
                                                             {'file_check': fcheck, 'folder_id': folder_id}, cur=cur))
                    logger.info("list_files.size: {}".format(list_files.shape[0]))
                    if list_files.shape[0] > 0:
                        folder_files_df = folder_files_df.merge(list_files, how='outer', on='file_id')
                preview_files = pd.DataFrame(run_query(("SELECT f.file_id, "
                                                             "  CASE WHEN f.preview_image is NULL THEN CONCAT('/preview_image/', f.file_id, '/?') ELSE f.preview_image END as preview_image "
                                                             " FROM files f where f.folder_id = %(folder_id)s"),
                                                            {'folder_id': folder_id}, cur=cur))
                folder_files_df = folder_files_df.sort_values(by=['file_name'])
                folder_files_df = folder_files_df.sort_values(by=filechecks_list)
                folder_files_df = folder_files_df.merge(preview_files, how='outer', on='file_id')
                folder_files_df['file_name'] = '<a href="/file/' \
                                               + folder_files_df['file_id'].astype(str) + '/" title="Details of File ' + folder_files_df['file_name'].astype(str) + '">' \
                                               + folder_files_df['file_name'].astype(str) \
                                               + '</a> ' \
                                               + '<button type="button" class="btn btn-light btn-sm" ' \
                                               + 'data-bs-toggle="modal" data-bs-target="#previewmodal1" ' \
                                               + 'data-bs-info="' + folder_files_df['preview_image'] \
                                               + '&max=1200" data-bs-link = "/file/' + folder_files_df['file_id'].astype(str) \
                                               + '" data-bs-text = "Details of the file ' + folder_files_df[
                                                   'file_name'].astype(str) \
                                               + '" title="Image Preview of ' + folder_files_df['file_name'].astype(str) + '">' \
                                               + '<i class="fa-regular fa-image"></i></button>'
                folder_files_df = folder_files_df.drop(['file_id'], axis=1)
                folder_files_df = folder_files_df.drop(['preview_image'], axis=1)


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
                post_processing_df = pd.DataFrame()
        elif tab == "lightbox":
            page_no = "Lightbox Page {}".format(page)
            # Pagination
            pagination_html = "<nav aria-label=\"pages\"><ul class=\"pagination float-end\">"
            no_pages = math.ceil(files_count / no_items)
            logger.info("no_pages: {}".format(no_pages))
            if page == 1:
                pagination_html = pagination_html + "<li class=\"page-item disabled\"><a class=\"page-link\" href=\"#\" " \
                                                    "tabindex=\"-1\">Previous</a></li>"
            else:
                pagination_html = pagination_html + "<li class=\"page-item\"><a class=\"page-link\" " \
                                                    "href=\"" + url_for('dashboard_f', project_alias=project_alias,
                                                                        folder_id=folder_id, tab="lightbox",
                                                                        page="{}".format(page - 1)) \
                                  + "\">Previous</a></li>"
            # Ellipsis for first pages
            if page > 5:
                pagination_html = pagination_html + "<li class=\"page-item\"><a class=\"page-link\" " \
                                  + "href=\"" + url_for('dashboard_f', project_alias=project_alias, folder_id=folder_id,
                                                        tab="lightbox", page="1") \
                                  + "\">1</a></li>"
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
                                      + url_for('dashboard_f', project_alias=project_alias, folder_id=folder_id,
                                                tab="lightbox", page="{}".format(i)) \
                                      + "\">{}</a>".format(i) \
                                      + "</li>"
            if (no_pages - page) > 4:
                pagination_html = pagination_html + "<li class=\"page-item disabled\"><a class=\"page-link\" " \
                                                    "href=\"#\">...</a></li>"
                pagination_html = pagination_html + "<li class=\"page-item\"><a class=\"page-link\" " \
                                  + "href=\"" + url_for('dashboard_f', project_alias=project_alias, folder_id=folder_id,
                                                        tab="lightbox", page="{last}".format(last=no_pages)) \
                                  + "\">{last}</a></li>".format(last=no_pages)
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
                                                            folder_id=folder_id, tab="lightbox",
                                                            page="{}".format(page + 1)) \
                                      + "\">" \
                                      + "Next</a></li>"
            pagination_html = pagination_html + "</ul></nav>"
        elif tab == "postprod":
            page_no = "Post-Processing Steps"
            folder_files_df = pd.DataFrame()
            post_processing_df = pd.DataFrame(run_query(("SELECT file_id, file_name FROM files "
                                                  " WHERE folder_id = %(folder_id)s ORDER BY file_name"),
                                                 {'folder_id': folder_id}, cur=cur))
            logger.info("project_postprocessing {}".format(project_postprocessing))
            post_processing_df['file_name'] = '<a href="/file/' \
                                              + post_processing_df['file_id'].astype(str) + '/" title="File Details">' \
                                              + post_processing_df['file_name'].astype(str) \
                                              + '</a>'
            if len(project_postprocessing) > 0:
                for fcheck in project_postprocessing:
                    logger.info("fcheck: {}".format(fcheck))
                    list_files = pd.DataFrame(run_query(("SELECT f.file_id, "
                                                              "   CASE WHEN post_step = 0 THEN 'Completed' "
                                                              "       WHEN post_step = 9 THEN 'Pending' "
                                                              "       WHEN post_step = 1 THEN 'Failed' "
                                                              "       ELSE 'Pending' END as {fcheck} "
                                                              " FROM files f LEFT JOIN file_postprocessing c ON (f.file_id=c.file_id AND c.post_step = %(file_check)s) "
                                                              "  where f.folder_id = %(folder_id)s").format(
                        fcheck=fcheck),
                                                             {'file_check': fcheck, 'folder_id': folder_id}, cur=cur))
                    logger.info("list_files.size: {}".format(list_files.shape[0]))
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
    logger.info("folder_links: {}".format(folder_links))

    # Reports
    reports = run_query("SELECT * FROM data_reports WHERE project_id = %(project_id)s ORDER BY report_title_brief",
                             {'project_id': project_id}, cur=cur)

    if len(reports) > 0:
        proj_reports = True
    else:
        proj_reports = False

    if tab == "filechecks":
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
    folder_files_df = pd.DataFrame()
    return render_template('dashboard_ajax.html',
                           page_no=page_no,
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
                           page=page,
                           files_count=files_count,
                           pagination_html=pagination_html,
                           folder_stats=folder_stats,
                           post_processing=[post_processing_df.to_html(table_id='post_processing_table',
                                                       index=False,
                                                       border=0,
                                                       escape=False,
                                                       classes=["display", "compact", "table-striped", "w-100"])],
                           postproc_data=(project_info['project_postprocessing'] != ""),
                           post_processing_rows=post_processing_df.shape[0],
                           folder_links=folder_links,
                           project_folders_badges=project_folders_badges,
                           form=form,
                           proj_reports=proj_reports,
                           reports=reports,
                           site_env=site_env,
                           site_net=site_net,
                           site_ver=site_ver,
                           kiosk=kiosk,
                           user_address=user_address,
                           qc_check=qc_check,
                           qc_details=[qc_details.to_html(table_id='qc_details_table',
                                                       index=False,
                                                       border=0,
                                                       escape=False,
                                                       classes=["display", "compact", "table-striped", "w-100"])],
                           project_disk=project_disk,
                           projects_links=projects_links,
                           project_manager_link=project_manager_link,
                           analytics_code=settings.analytics_code
                           )


# DataTable API
@cache.memoize()
@app.route('/ajax/<project_alias>/<folder_id>/', methods=['GET'], provide_automatic_options=False)
def filestable(project_alias=None, folder_id=None):
    """Dashboard for a project"""

    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
    try:
        folder_id = int(folder_id)
    except ValueError:
        error_msg = "Invalid folder ID"
        return render_template('error.html', error_msg=error_msg,
                               project_alias=project_alias, site_env=site_env, site_ver=site_ver, site_net=site_net,
                           analytics_code=settings.analytics_code), 400

    # Connect to db
    try:
        conn = mysql.connector.connect(host=settings.host,
                                user=settings.user,
                                password=settings.password,
                                database=settings.database,
                                port=settings.port, autocommit=True)
        conn.time_zone = '-04:00'
        cur = conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        logger.error(err)
        return jsonify({'error': 'API error'}), 500

    # Check if project exists
    if project_alias_exists(project_alias, cur=cur) is False:
        error_msg = "Project was not found."
        return render_template('error.html', error_msg=error_msg,
                                project_alias=project_alias, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404

    project_id_check = run_query("SELECT project_id FROM projects WHERE project_alias = %(project_alias)s",
                                      {'project_alias': project_alias}, cur=cur)
    if len(project_id_check) == 0:
        error_msg = "Project was not found."
        return render_template('error.html', error_msg=error_msg,
                               project_alias=project_alias, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404
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
        return render_template('error.html', error_msg=error_msg,
                               project_alias=project_alias, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404

    if project_alias is None:
        error_msg = "Project is not available."
        return render_template('error.html', error_msg=error_msg,
                               project_alias=project_alias, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404

    filechecks_list_temp = run_query(
        ("SELECT settings_value as file_check FROM projects_settings "
         " WHERE project_setting = 'project_checks' and project_id = %(project_id)s"),
        {'project_id': project_id}, cur=cur)
    filechecks_list = []
    for fcheck in filechecks_list_temp:
        filechecks_list.append(fcheck['file_check'])
    logger.info("filechecks_list:{}".format(filechecks_list_temp))
    project_postprocessing = []

    files_df = ""
    folder_files_df = pd.DataFrame()

    if folder_id is not None and folder_id != '':
        folder_name = run_query(("SELECT project_folder FROM folders "
                                 "WHERE folder_id = %(folder_id)s and project_id = %(project_id)s"),
                                     {'folder_id': folder_id, 'project_id': project_id}, cur=cur)
        logger.info("folder_name: {}".format(len(folder_name)))
        if len(folder_name) == 0:
            error_msg = "Folder does not exist in this project."
            return render_template('error.html', error_msg=error_msg, project_alias=project_alias,
                                   site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404
        else:
            folder_name = folder_name[0]

        folder_files_df = pd.DataFrame(
            run_query("SELECT file_id, file_name FROM files WHERE folder_id = %(folder_id)s",
                      {'folder_id': folder_id}, cur=cur))
        files_df = run_query((
                                 "WITH data AS (SELECT file_id, CONCAT('/preview_image/', file_id, '/?') as preview_image, "
                                 "         preview_image as preview_image_ext, folder_id, file_name FROM files "
                                 "WHERE folder_id = %(folder_id)s)"
                                 " SELECT file_id, preview_image, preview_image_ext, folder_id, file_name"
                                 " FROM data "
                                 " ORDER BY file_name "
                                 "LIMIT {no_items} OFFSET {offset}").format(offset=0, no_items=25),
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

        else:
            for fcheck in filechecks_list:
                logger.info("fcheck: {}".format(fcheck))
                list_files = pd.DataFrame(run_query(("SELECT f.file_id, "
                                                          "   CASE WHEN check_results = 0 THEN 'OK' "
                                                          "       WHEN check_results = 9 THEN 'Pending' "
                                                          "       WHEN check_results = 1 THEN 'Failed' "
                                                          "       ELSE 'Pending' END as {fcheck} "
                                                          " FROM files f LEFT JOIN files_checks c ON (f.file_id=c.file_id AND c.file_check = %(file_check)s) "
                                                          "  where f.folder_id = %(folder_id)s").format(fcheck=fcheck),
                                                         {'file_check': fcheck, 'folder_id': folder_id}, cur=cur))
                logger.info("list_files.size: {}".format(list_files.shape[0]))
                if list_files.shape[0] > 0:
                    folder_files_df = folder_files_df.merge(list_files, how='outer', on='file_id')
            preview_files = pd.DataFrame(run_query(("SELECT f.file_id, "
                                                         "  CASE WHEN f.preview_image is NULL THEN CONCAT('/preview_image/', f.file_id, '/?') ELSE f.preview_image END as preview_image "
                                                         " FROM files f where f.folder_id = %(folder_id)s"),
                                                        {'folder_id': folder_id}, cur=cur))
            folder_files_df = folder_files_df.sort_values(by=['file_name'])
            folder_files_df = folder_files_df.sort_values(by=filechecks_list)
            folder_files_df = folder_files_df.merge(preview_files, how='outer', on='file_id')
            folder_files_df['file_name'] = '<a href="/file/' \
                                           + folder_files_df['file_id'].astype(str) + '/" title="Details of File ' + folder_files_df['file_name'].astype(str) + '">' \
                                           + folder_files_df['file_name'].astype(str) \
                                           + '</a> ' \
                                           + '<button type="button" class="btn btn-light btn-sm" ' \
                                           + 'data-bs-toggle="modal" data-bs-target="#previewmodal1" ' \
                                           + 'data-bs-info="' + folder_files_df['preview_image'] \
                                           + '&max=1200" data-bs-link = "/file/' + folder_files_df['file_id'].astype(str) \
                                           + '" data-bs-text = "Details of the file ' + folder_files_df[
                                               'file_name'].astype(str) \
                                           + '" title="Image Preview of ' + folder_files_df['file_name'].astype(str) + '">' \
                                           + '<i class="fa-regular fa-image"></i></button>'
            folder_files_df = folder_files_df.drop(['file_id'], axis=1)
            folder_files_df = folder_files_df.drop(['preview_image'], axis=1)

    else:
        folder_files_df = pd.DataFrame()
        pagination_html = ""
        files_df = ""
        files_count = ""

    cur.close()
    conn.close()
    data = {}
    folder_files_df = folder_files_df.iloc[:25]
    data["data"] = json.loads(folder_files_df.to_json(orient='values'))
    data["draw"] = 1
    data["recordsTotal"] = files_count
    data["recordsFiltered"] = files_count
    return(data)


@cache.memoize()
@app.route('/dashboard/<project_alias>/', methods=['GET', 'POST'], provide_automatic_options=False)
def dashboard(project_alias=None):
    """Dashboard for a project"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Connect to db
    try:
        conn = mysql.connector.connect(host=settings.host,
                                user=settings.user,
                                password=settings.password,
                                database=settings.database,
                                port=settings.port, autocommit=True)
        conn.time_zone = '-04:00'
        cur = conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        logger.error(err)
        return jsonify({'error': 'API error'}), 500

    # Declare the login form
    form = LoginForm(request.form)

    project_stats = {}

    # Check if project exists
    project_id = project_alias_exists(project_alias, cur=cur)
    if project_id is False:
        error_msg = "Project was not found."
        return render_template('error.html', error_msg=error_msg, project_alias=project_alias,
                               site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404

    logger.info("project_id: {}".format(project_id))
    logger.info("project_alias: {}".format(project_alias))
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
        logger.info("project_admin: {} - {}".format(username, project_admin))
    else:
        project_admin = False
    project_info = run_query("SELECT *, CONCAT('https://dpo.si.edu/', lower(replace(project_manager, ' ', '-'))) as project_manager_link, "
                             "      CONCAT(date_format(project_start, '%d-%b-%Y'), "
                             "          CASE WHEN project_end IS NULL THEN '' ELSE CONCAT(' to ', date_format(project_end, '%d-%b-%Y')) END "
                             "          ) as pdates "
                             "   FROM projects WHERE project_id = %(project_id)s",
                                  {'project_id': project_id}, cur=cur)[0]

    project_managers = run_query("SELECT project_manager FROM projects WHERE project_alias = %(project_alias)s",
                                 {'project_alias': project_alias}, cur=cur)[0]

    project_manager_link = project_managers['project_manager']
    if project_managers['project_manager'] == "Jeanine Nault":
        project_manager_link = "<a href=\"https://dpo.si.edu/jeanine-nault\" class=\"bg-white\" title=\"Link to Jeanine Nault's staff page\">Jeanine Nault</a>"
    elif project_managers['project_manager'] == "Nathan Ian Anderson":
        project_manager_link = "<a href=\"https://dpo.si.edu/nathan-ian-anderson\" class=\"bg-white\" title=\"Link to Nathan Ian Anderson's staff page\">Nathan Ian Anderson</a>"
    elif project_managers['project_manager'] == "Erin M. Mazzei":
        project_manager_link = "<a href=\"https://dpo.si.edu/erin-mazzei\" class=\"bg-white\" title=\"Link to Erin M. Mazzei's staff page\">Erin M. Mazzei</a>"


    projects_links = run_query("SELECT * FROM projects_links WHERE project_id = %(project_id)s ORDER BY table_id",
                               {'project_id': project_info['project_id']}, cur=cur)

    try:
        filechecks_list = project_info['project_checks'].split(',')
    except:
        error_msg = "Project is not available."
        return render_template('error.html', error_msg=error_msg, project_alias=project_alias,
                               site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404

    project_statistics = run_query(("SELECT COALESCE(images_taken, 0) as images_taken, COALESCE(objects_digitized, 0) as objects_digitized "
                                    "  FROM projects_stats WHERE project_id = %(project_id)s"),
                                   {'project_id': project_id}, cur=cur)[0]

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

    project_stats['objects'] = format(int(project_statistics['objects_digitized']), ',d')

    project_stats_other = run_query(("SELECT other_icon, other_name, COALESCE(other_stat, 0) as other_stat FROM projects_stats WHERE project_id = %(project_id)s"), {'project_id': project_id}, cur=cur)[0]
    project_stats_other['other_stat'] = format(int(project_stats_other['other_stat']), ',d')

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
                           page_no="",
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
                           tab=None,
                           page=1,
                           files_count=files_count,
                           pagination_html=pagination_html,
                           folder_stats=folder_stats,
                           post_processing=[post_processing_df.to_html(table_id='post_processing_table',
                                                                       index=False,
                                                                       border=0,
                                                                       escape=False,
                                                                       classes=["display", "compact",
                                                                                "table-striped"])],
                           postproc_data=(project_info['project_postprocessing'] != ""),
                           folder_links=folder_links,
                           project_folders_badges=project_folders_badges,
                           form=form,
                           proj_reports=proj_reports,
                           reports=reports,
                           site_env=site_env,
                           site_net=site_net,
                           site_ver=site_ver,
                           kiosk=kiosk,
                           user_address=user_address,
                           project_disk=project_disk,
                           projects_links=projects_links,
                           project_manager_link=project_manager_link,
                           analytics_code=settings.analytics_code,
                           project_stats_other=project_stats_other
                           )


@cache.memoize()
@app.route('/dashboard/<project_alias>/statistics/', methods=['POST', 'GET'], provide_automatic_options=False)
def proj_statistics(project_alias=None):
    """Statistics for a project"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
    user_exists = False
    username = None

    # Declare the login form
    form = LoginForm(request.form)

    # Connect to db
    try:
        conn = mysql.connector.connect(host=settings.host,
                                user=settings.user,
                                password=settings.password,
                                database=settings.database,
                                port=settings.port, autocommit=True)
        conn.time_zone = '-04:00'
        cur = conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        logger.error(err)
        return jsonify({'error': 'API error'}), 500

    # Check if project exists
    if project_alias_exists(project_alias, cur=cur) is False:
        error_msg = "Project was not found."
        return render_template('error.html', error_msg=error_msg,
                                project_alias=project_alias, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404

    project_id_check = run_query("SELECT project_id FROM projects WHERE project_alias = %(project_alias)s",
                                      {'project_alias': project_alias}, cur=cur)
    if len(project_id_check) == 0:
        error_msg = "Project was not found."
        return render_template('error.html', error_msg=error_msg,
                               project_alias=project_alias, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404
    else:
        project_id = project_id_check[0]['project_id']

    project_info = run_query("SELECT * FROM projects WHERE project_id = %(project_id)s", {'project_id': project_id}, cur=cur)[0]

    proj_stats_steps = run_query("SELECT * FROM projects_detail_statistics_steps WHERE project_id = %(proj_id)s and (stat_type='column' or stat_type='boxplot' or stat_type='area') and active=1 ORDER BY step_order", {'proj_id': project_info['proj_id']}, cur=cur)

    proj_stats_vals1 = run_query("SELECT s.step_info, s.step_notes, step_units, s.css, s.round_val, DATE_FORMAT(s.step_updated_on, \"%Y-%m-%d %H:%i:%s\") as step_updated_on, e.step_value FROM projects_detail_statistics_steps s, projects_detail_statistics e WHERE s.project_id = %(proj_id)s and s.stat_type='stat' and e.step_id = s.step_id and s.active=1 ORDER BY s.step_order LIMIT 3", {'proj_id': project_info['proj_id']}, cur=cur)

    proj_stats_vals2 = run_query("SELECT s.step_info, s.step_notes, s.step_units, s.css, s.round_val, DATE_FORMAT(s.step_updated_on, \"%Y-%m-%d %H:%i:%s\") as step_updated_on, e.step_value FROM projects_detail_statistics_steps s, projects_detail_statistics e WHERE s.project_id = %(proj_id)s and s.stat_type='stat' and e.step_id = s.step_id and s.active=1 ORDER BY s.step_order LIMIT 3, 3", {'proj_id': project_info['proj_id']}, cur=cur)

    # Stats
    project_stats = {}
    project_statistics = run_query(("SELECT COALESCE(images_taken, 0) as images_taken, COALESCE(objects_digitized, 0) as objects_digitized "
                                    "  FROM projects_stats WHERE project_id = %(project_id)s"),
                                    {'project_id': project_id}, cur=cur)[0]
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
    project_stats['objects'] = format(int(project_statistics['objects_digitized']), ',d')

    project_stats_other = run_query(("SELECT other_icon, other_name, COALESCE(other_stat, 0) as other_stat FROM projects_stats WHERE project_id = %(project_id)s"), {'project_id': project_id}, cur=cur)[0]
    project_stats_other['other_stat'] = format(int(project_stats_other['other_stat']), ',d')

    cur.close()
    conn.close()

    return render_template('statistics.html',
                           project_alias=project_alias,
                           project_info=project_info,
                           proj_stats_steps=proj_stats_steps,
                           proj_stats_vals1=proj_stats_vals1,
                           proj_stats_vals2=proj_stats_vals2,
                           project_stats=project_stats,
                           project_stats_other=project_stats_other)



@cache.memoize()
@app.route('/dashboard/<project_id>/statistics/<step_id>', methods=['POST', 'GET'], provide_automatic_options=False)
def proj_statistics_dl(project_id=None, step_id=None):
    """Download statistics for a project"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
        
    # Connect to db
    try:
        conn = mysql.connector.connect(host=settings.host,
                                user=settings.user,
                                password=settings.password,
                                database=settings.database,
                                port=settings.port, autocommit=True)
        conn.time_zone = '-04:00'
        cur = conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        logger.error(err)
        return jsonify({'error': 'API error'}), 500

    project_id_check = run_query("SELECT proj_id FROM projects WHERE proj_id = %(proj_id)s",
                                      {'proj_id': project_id}, cur=cur)
    if len(project_id_check) == 0:
        error_msg = "Project was not found."
        return render_template('error.html', error_msg=error_msg,
                               project_alias=None, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404

    project_info = run_query("SELECT * FROM projects WHERE proj_id = %(proj_id)s", {'proj_id': project_id}, cur=cur)[0]

    proj_stats = run_query("SELECT e.step_info, e.step_notes, e.step_units, s.* FROM projects_detail_statistics_steps e RIGHT JOIN projects_detail_statistics s ON (e.step_id = s.step_id) WHERE e.step_id = %(step_id)s", {'step_id': step_id}, cur=cur)

    cur.close()
    conn.close()

    csv_data = "data_type,info,units,date,value\n"
    for data_row in proj_stats:
        csv_data += f"{data_row['step_info']}, {data_row['step_notes']}, {data_row['step_units']}, {data_row['date']}, {data_row['step_value']}\n"

    current_time = strftime("%Y%m%d_%H%M%S", localtime())

    # Create a direct download response with the CSV data and appropriate headers
    response = Response(csv_data, content_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename={}_stats_{}.csv".format(project_info['project_alias'], current_time)
 
    return response


@cache.memoize()
@app.route('/about/', methods=['GET'], provide_automatic_options=False)
def about():
    """About page for the system"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
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
    return render_template('about.html', form=form, 
                           site_net=site_net, site_env=site_env, site_ver=site_ver,
                           kiosk=kiosk, user_address=user_address,
                           analytics_code=settings.analytics_code)


@app.route('/qc/<project_alias>/', methods=['POST', 'GET'], provide_automatic_options=False)
@login_required
def qc(project_alias=None):
    """List the folders and QC status"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    try:
        conn = mysql.connector.connect(host=settings.host,
                                user=settings.user,
                                password=settings.password,
                                database=settings.database,
                                port=settings.port, autocommit=True)
        conn.time_zone = '-04:00'
        cur = conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        logger.error(err)
        return jsonify({'error': 'API error'}), 500

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

    project_qc_stats = {}

    project_qc_ok = run_query(("SELECT count(f.folder_id) as no_folders FROM folders f LEFT JOIN qc_folders q on (f.folder_id = q.folder_id ) "
                        "WHERE f.project_id = %(project_id)s and q.qc_status = 0"),
                        {'project_id': project_id}, cur=cur)[0]

    project_qc_failed = run_query((
                                  "SELECT count(f.folder_id) as no_folders FROM folders f LEFT JOIN qc_folders q on (f.folder_id = q.folder_id ) "
                                  "WHERE f.project_id = %(project_id)s and q.qc_status = 1"),
                              {'project_id': project_id}, cur=cur)[0]

    project_qc_count = run_query((
        "SELECT count(f.folder_id) as no_folders FROM folders f WHERE f.project_id = %(project_id)s"),
        {'project_id': project_id}, cur=cur)[0]

    project_qc_stats['total'] = project_qc_count['no_folders']
    project_qc_stats['ok'] = project_qc_ok['no_folders']
    project_qc_stats['failed'] = project_qc_failed['no_folders']

    project_qc_stats['pending'] = project_qc_stats['total'] - (project_qc_stats['ok'] + project_qc_stats['failed'])

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
                                "       ft.no_files, f.file_errors, f.status, f.error_info, q.qc_level, "
                                "   CASE WHEN q.qc_status = 0 THEN 'QC Passed' "
                                "      WHEN q.qc_status = 1 THEN 'QC Failed' "
                                "      ELSE 'QC Pending' END AS qc_status, "
                                "      q.qc_ip, u.username AS qc_by, "
                                "      date_format(q.updated_at, '%Y-%m-%d') AS updated_at, "
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
                                     "      date_format(q.updated_at, '%Y-%m-%d') AS updated_at, "
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
                                     " WHERE f.project_id = p.project_id AND f.file_errors = 0 "
                                     "   AND p.project_id = %(project_id)s) "
                                     " SELECT * FROM qc WHERE qc_status = 'QC Pending' and qc_by is null "
                                     "  ORDER BY date ASC, project_folder ASC LIMIT 1"),
                                    {'project_id': project_id}, cur=cur)
    folder_qc_pending = run_query(("WITH pfolders AS (SELECT folder_id from folders WHERE project_id = %(project_id)s),"
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
                                     "      date_format(q.updated_at, '%Y-%m-%d') AS updated_at, "
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
                                     " SELECT * FROM qc WHERE qc_status = 'QC Pending' and qc_by is not null "
                                     "  ORDER BY date ASC, project_folder ASC"),
                                    {'project_id': project_id}, cur=cur)
    cur.close()
    conn.close()
    return render_template('qc.html', username=username,
                           project_settings=project_settings,
                           folder_qc_info=folder_qc_info,
                           folder_qc_pending=folder_qc_pending,
                           folder_qc_done=folder_qc_done,
                           folder_qc_done_len=len(folder_qc_done),
                           project=project,
                           form=form,
                           project_qc_stats=project_qc_stats,
                           site_env=site_env,
                           site_net=site_net,
                           site_ver=site_ver,
                           analytics_code=settings.analytics_code)


@app.route('/qc_process/<folder_id>/', methods=['GET', 'POST'], provide_automatic_options=False)
@login_required
def qc_process(folder_id):
    """Run QC on a folder"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Connect to db
    try:
        conn = mysql.connector.connect(host=settings.host,
                                user=settings.user,
                                password=settings.password,
                                database=settings.database,
                                port=settings.port, autocommit=True)
        conn.time_zone = '-04:00'
        cur = conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        logger.error(err)
        return jsonify({'error': 'API error'}), 500

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
    # check if folder is owned, assigned otherwise
    folder_owner = run_query(("SELECT f.*, u.username from qc_folders f, users u "
                                    "    WHERE u.user_id = f.qc_by "
                                    "        AND f.folder_id = %(folder_id)s"),
                                   {'folder_id': folder_id}, cur=cur)
    if len(folder_owner) == 1:
        # print(folder_owner[0]['username'])
        # print(username)
        if folder_owner[0]['username'] != username:
            # Not allowed
            project_alias = run_query(("SELECT p.project_alias from folders f, projects p "
                                    "    WHERE f.project_id = p.project_id "
                                    "        AND f.folder_id = %(folder_id)s"),
                                   {'folder_id': folder_id}, cur=cur)
            return redirect(url_for('qc', project_alias=project_alias[0]['project_alias']))
    else:
        # Assign user
        q = query_database_insert(("UPDATE qc_folders SET qc_by = %(qc_by)s "
                                " WHERE folder_id = %(folder_id)s"),
                               {'folder_id': folder_id,
                                'qc_by': current_user.id
                                }, cur=cur)
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
            logger.info("file_id: {}".format(file_id_q))
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
                                      "      date_format(q.updated_at, '%Y-%m-%d') AS updated_at"
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
    logger.info("qc_status: {} | no_files: {}".format(folder_qc['qc_status'], folder_stats['no_files']))
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
            logger.info("1587: {}".format(no_files_for_qc))
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
                file_details = run_query(("SELECT f.file_id, f.folder_id, f.file_name, COALESCE(s.sensitive_contents, 0) as sensitive_contents "
                                               " FROM files f LEFT JOIN sensitive_contents s ON f.file_id = s.file_id WHERE f.file_id = %(file_id)s"),
                                              {'file_id': file_qc['file_id']}, cur=cur)[0]
                file_checks = run_query(("SELECT file_check, check_results, "
                                              "       CASE WHEN check_info = '' THEN 'Check passed.' "
                                              "           ELSE check_info END AS check_info "
                                              "   FROM files_checks WHERE file_id = %(file_id)s"),
                                             {'file_id': file_qc['file_id']}, cur=cur)
                image_url = '/preview_image/' + str(file_qc['file_id']) + '/?'
                image_url_prev = '/preview_image/' + str(file_qc['file_id']) + '/?max=1200'
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

                # DZI zoomable image
                zoom_filename = url_for('static', filename='/image_previews/folder{}/{}.dzi'.format(file_details['folder_id'], file_qc['file_id']))
                
                if os.path.isfile('static/image_previews/folder{}/{}.dzi'.format(file_details['folder_id'], file_qc['file_id'])):
                    zoom_exists = 1
                    zoom_js = ""
                else:
                    zoom_exists = 0
                    zoom_filename = None
                    zoom_js = """
                            $('#previmg')
                            .wrap('<span style="display:inline-block"></span>')
                            .css('display', 'block')
                            .parent()
                            .zoom();
                            """

                return render_template('qc_file.html',
                                       zoom_exists=zoom_exists,
                                       zoom_filename=zoom_filename,
                                       zoom_js=zoom_js,
                                       folder=folder,
                                       qc_stats=qc_stats,
                                       folder_id=folder_id,
                                       file_qc=file_qc,
                                       project_settings=project_settings,
                                       file_details=file_details,
                                       file_checks=file_checks,
                                       image_url=image_url,
                                       image_url_prev=image_url_prev,
                                       username=username,
                                       project_alias=project_alias['project_alias'],
                                       tables=[file_metadata.to_html(table_id='file_metadata', index=False, border=0,
                                                                     escape=False,
                                                                     classes=["display", "compact", "table-striped"])],
                                       msg=msg,
                                       form=form,
                                       site_env=site_env,
                                       site_net=site_net,
                                       site_ver=site_ver,
                                       analytics_code=settings.analytics_code
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
                                       site_net=site_net,
                                       site_ver=site_ver,
                                       analytics_code=settings.analytics_code)
    else:
        error_msg = "Folder is not available for QC."
        return render_template('error.html', error_msg=error_msg,
                               project_alias=project_alias['project_alias'], site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 400


@app.route('/qc_done/<folder_id>/', methods=['POST', 'GET'], provide_automatic_options=False)
@login_required
def qc_done(folder_id):
    """Run QC on a folder"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
    try:
        conn = mysql.connector.connect(host=settings.host,
                                user=settings.user,
                                password=settings.password,
                                database=settings.database,
                                port=settings.port, autocommit=True)
        conn.time_zone = '-04:00'
        cur = conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        logger.error(err)
        return jsonify({'error': 'API error'}), 500

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
    if len(project_qc_hist) < 5:
        level = 'Tightened'
    else:
        ok_folders = 0
        for folder in project_qc_hist:
            if folder['qc_status'] == 0:
                ok_folders += 1
        logger.info("ok_folders post QC: {}".format(ok_folders))
        if ok_folders <= 4:
            level = 'Tightened'
        elif ok_folders == 5:
            level = 'Normal'
        else:
            level = 'Normal'
    res = query_database_insert("UPDATE qc_settings SET qc_level = %(qc_level)s, qc_percent = qc_{}_percent WHERE project_id = %(project_id)s".format(level.lower()),
                                {'project_id': project_id, 'qc_level': level}, cur=cur)
    cur.close()
    conn.close()
    return redirect(url_for('qc', project_alias=project_alias))


@app.route('/home/', methods=['GET'], provide_automatic_options=False)
@login_required
def home():
    """Home for user, listing projects and options"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    try:
        conn = mysql.connector.connect(host=settings.host,
                                user=settings.user,
                                password=settings.password,
                                database=settings.database,
                                port=settings.port, autocommit=True)
        conn.time_zone = '-04:00'
        cur = conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        logger.error(err)
        return jsonify({'error': 'API error'}), 500

    # Declare the login form
    form = LoginForm(request.form)

    user_name = current_user.name
    is_admin = user_perms('', user_type='admin')
    logger.info(is_admin)
    ip_addr = request.environ['REMOTE_ADDR']
    projects = run_query(("select p.project_title, p.project_id, p.project_alias, "
                               "     date_format(p.project_start, '%b-%Y') as project_start, "
                               "     date_format(p.project_end, '%b-%Y') as project_end,"
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
        logger.info("project: {}".format(project))
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
        logger.info("project_alias: {}".format(project_alias))
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
                           site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code)


@app.route('/new_project/', methods=['GET'], provide_automatic_options=False)
@login_required
def new_project(msg=None):
    """Create a new project"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
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
                               site_env=site_env,
                               site_net=site_net, site_ver=site_ver,
                               analytics_code=settings.analytics_code)


@app.route('/create_new_project/', methods=['POST'], provide_automatic_options=False)
@login_required
def create_new_project():
    """Create a new project"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
    # Connect to db
    try:
        conn = mysql.connector.connect(host=settings.host,
                                user=settings.user,
                                password=settings.password,
                                database=settings.database,
                                port=settings.port, autocommit=True)
        conn.time_zone = '-04:00'
        cur = conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        logger.error(err)
        return jsonify({'error': 'API error'}), 500

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
                              'collex_total': int(p_noobjects)}, cur=cur)
    user_project = query_database_insert(("INSERT INTO qc_projects (project_id, user_id) VALUES "
                                     "    (%(project_id)s, %(user_id)s)"),
                                    {'project_id': project_id,
                                     'user_id': current_user.id}, cur=cur)
    if current_user.id != '101':
        user_project = query_database_insert(("INSERT INTO qc_projects (project_id, user_id) VALUES "
                                         "    (%(project_id)s, %(user_id)s)"),
                                        {'project_id': project_id,
                                         'user_id': '101'}, cur=cur)
    if p_unitstaff != '':
        unitstaff = p_unitstaff.split(',')
        logger.info("unitstaff: {}".format(p_unitstaff))
        logger.info("len_unitstaff: {}".format(len(unitstaff)))
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
    fcheck_query = ("INSERT INTO projects_settings (project_id, project_setting, settings_value) VALUES "
                                          "    (%(project_id)s, 'project_checks', %(value)s)")
    fcheck_insert = query_database_insert(fcheck_query, {'project_id': project_id, 'value': 'unique_file'}, cur=cur)
    fcheck_insert = query_database_insert(fcheck_query, {'project_id': project_id, 'value': 'tifpages'}, cur=cur)
    file_check = request.values.get('raw_pair')
    if file_check == "1":
        fcheck_insert = query_database_insert(fcheck_query, {'project_id': project_id, 'value': 'raw_pair'}, cur=cur)
    file_check = request.values.get('tif_compression')
    if file_check == "1":
        fcheck_insert = query_database_insert(fcheck_query, {'project_id': project_id, 'value': 'tif_compression'}, cur=cur)
    file_check = request.values.get('magick')
    if file_check == "1":
        fcheck_insert = query_database_insert(fcheck_query, {'project_id': project_id, 'value': 'magick'}, cur=cur)
    file_check = request.values.get('jhove')
    if file_check == "1":
        fcheck_insert = query_database_insert(fcheck_query, {'project_id': project_id, 'value': 'jhove'}, cur=cur)
    file_check = request.values.get('sequence')
    if file_check == "1":
        fcheck_insert = query_database_insert(fcheck_query, {'project_id': project_id, 'value': 'sequence'}, cur=cur)
    #
    cur.close()
    conn.close()
    return redirect(url_for('home', _anchor=p_alias))


@app.route('/edit_project/<project_alias>/', methods=['GET'], provide_automatic_options=False)
@login_required
def edit_project(project_alias=None):
    """Edit a project"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
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
        conn = mysql.connector.connect(host=settings.host,
                                user=settings.user,
                                password=settings.password,
                                database=settings.database,
                                port=settings.port, autocommit=True)
        conn.time_zone = '-04:00'
        cur = conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        logger.error(err)
        return jsonify({'error': 'API error'}), 500

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
                           site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code)


@app.route('/proj_links/<project_alias>/', methods=['GET'], provide_automatic_options=False)
@login_required
def proj_links(project_alias=None):
    """Add / edit links associated with a project"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
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
        conn = mysql.connector.connect(host=settings.host,
                                user=settings.user,
                                password=settings.password,
                                database=settings.database,
                                port=settings.port, autocommit=True)
        conn.time_zone = '-04:00'
        cur = conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        logger.error(err)
        return jsonify({'error': 'API error'}), 500

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

    projects_links = run_query("SELECT * FROM projects_links WHERE project_id = %(project_id)s ORDER BY table_id",
                               {'project_id': project['project_id']}, cur=cur)

    cur.close()
    conn.close()
    return render_template('proj_links.html',
                           username=username,
                           is_admin=is_admin,
                           project=project,
                           form=form,
                           projects_links=projects_links,
                           site_env=site_env,
                           site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code)


@app.route('/add_links/', methods=['POST'], provide_automatic_options=False)
@login_required
def add_links(project_alias=None):
    """Create a new project"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
    # Connect to db
    try:
        conn = mysql.connector.connect(host=settings.host,
                                user=settings.user,
                                password=settings.password,
                                database=settings.database,
                                port=settings.port, autocommit=True)
        conn.time_zone = '-04:00'
        cur = conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        logger.error(err)
        return jsonify({'error': 'API error'}), 500

    username = current_user.name
    is_admin = user_perms('', user_type='admin')
    if is_admin is False:
        # Not allowed
        return redirect(url_for('home'))
    project_alias = request.values.get('project_alias')

    project = run_query(("SELECT project_id "
                         " FROM projects  "
                         " WHERE project_alias = %(project_alias)s"),
                        {'project_alias': project_alias}, cur=cur)[0]

    link_title = request.values.get('link_title')
    link_type = request.values.get('link_type')
    link_url = request.values.get('link_url')
    new_link = query_database_insert(("INSERT INTO projects_links "
                              "   (project_id, "
                              "    link_type, "
                              "    link_title,"
                              "    url) "
                              "  ("
                              "        SELECT "
                              "            %(project_id)s,"
                              "            %(link_type)s, "
                              "            %(link_title)s, "
                              "            %(url)s)"),
                             {'project_id': project['project_id'],
                              'link_type': link_type,
                              'link_title': link_title,
                              'url': link_url
                              }, cur=cur)
    cur.close()
    conn.close()
    return redirect(url_for('proj_links', project_alias=project_alias))


@app.route('/project_update/<project_alias>', methods=['POST'], provide_automatic_options=False)
@login_required
def project_update(project_alias):
    """Save edits to a project"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
    # Connect to db
    try:
        conn = mysql.connector.connect(host=settings.host,
                                user=settings.user,
                                password=settings.password,
                                database=settings.database,
                                port=settings.port, autocommit=True)
        conn.time_zone = '-04:00'
        cur = conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        logger.error(err)
        return jsonify({'error': 'API error'}), 500

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


@app.route('/file/<file_id>/', methods=['GET'], provide_automatic_options=False)
def file(file_id=None):
    """File details"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Declare the login form
    form = LoginForm(request.form)

    try:
        conn = mysql.connector.connect(host=settings.host,
                                user=settings.user,
                                password=settings.password,
                                database=settings.database,
                                port=settings.port, autocommit=True)
        conn.time_zone = '-04:00'
        cur = conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        logger.error(err)
        return jsonify({'error': 'System Error'}), 500

    file_id, file_uid = check_file_id(file_id, cur=cur)

    if file_id is None:
        error_msg = "File ID is missing."
        return render_template('error.html', error_msg=error_msg, project_alias=None, site_env=site_env, site_net=site_net, site_ver=site_ver), 400

    folder_info = run_query(
        "SELECT * FROM folders WHERE folder_id IN (SELECT folder_id FROM files WHERE file_id = %(file_id)s)",
        {'file_id': file_id}, cur=cur)
    if len(folder_info) == 0:
        error_msg = "Invalid File ID."
        return render_template('error.html', error_msg=error_msg, project_alias=None, site_env=site_env, site_net=site_net, site_ver=site_ver), 400
    else:
        folder_info = folder_info[0]
    file_details = run_query(("WITH data AS ("
                                   "         SELECT file_id, "
                                   "             CONCAT(%(preview)s, file_id) as preview_image, "
                                   "             preview_image as preview_image_ext, "
                                   "             folder_id, file_name, dams_uan, file_ext"
                                   "             FROM files "
                                   "                 WHERE folder_id = %(folder_id)s AND folder_id IN (SELECT folder_id FROM folders)"
                                   " UNION "
                                   "         SELECT file_id, CONCAT(%(preview)s, file_id) as preview_image, preview_image as preview_image_ext, folder_id, file_name, dams_uan, file_ext "
                                   "             FROM files "
                                   "                 WHERE folder_id = %(folder_id)s AND folder_id NOT IN (SELECT folder_id FROM folders)"
                                   "             ORDER BY file_name"
                                   "),"
                                   "data2 AS (SELECT file_id, preview_image, file_ext, preview_image_ext, folder_id, file_name, dams_uan, "
                                   "         lag(file_id,1) over (order by file_name) prev_id,"
                                   "         lead(file_id,1) over (order by file_name) next_id "
                                   " FROM data)"
                                   " SELECT "
                                   " file_id, "
                                   "     CASE WHEN position('?' in preview_image)>0 THEN preview_image ELSE CONCAT(preview_image, '?') END AS preview_image, "
                                   " preview_image_ext, folder_id, file_name, dams_uan, prev_id, next_id, file_ext "
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
    file_postprocessing = run_query(("SELECT post_step, post_results, CASE WHEN post_info = '' THEN 'Step completed.' "
                                     " WHEN post_info IS NULL THEN 'Step completed.' "
                                  " ELSE post_info END AS post_info "
                                  " FROM file_postprocessing WHERE file_id = %(file_id)s"),
                                 {'file_id': file_id}, cur=cur)
    image_url = '/preview_image/' + str(file_id)
    file_metadata = pd.DataFrame(run_query(("SELECT tag, taggroup, tagid, value "
                                                 " FROM files_exif "
                                                 " WHERE file_id = %(file_id)s AND "
                                                 "       lower(filetype) = %(file_ext)s AND "
                                                 "       lower(taggroup) != 'system' "
                                                 " ORDER BY taggroup, tag "),
                                                {'file_id': file_id, 'file_ext': file_details['file_ext']}, cur=cur))
    file_links = run_query("SELECT link_name, link_url, link_aria FROM files_links WHERE file_id = %(file_id)s ",
                                {'file_id': file_id}, cur=cur)
    file_sensitive = run_query("SELECT sensitive_contents, sensitive_info FROM sensitive_contents WHERE file_id = %(file_id)s ",
                                {'file_id': file_id}, cur=cur)
    if len(file_sensitive) == 0:
        file_sensitive = 0
        sensitive_info = ""
    else:
        file_data = file_sensitive[0]
        file_sensitive = file_data['sensitive_contents']
        sensitive_info = file_data['sensitive_info']
    
    if current_user.is_authenticated:
        user_name = current_user.name
        is_admin = user_perms('', user_type='admin')
    else:
        user_name = ""
        is_admin = False
    logger.info("project_alias: {}".format(project_alias))

    cur.close()
    conn.close()

    # kiosk mode
    kiosk, user_address = kiosk_mode(request, settings.kiosks)

    # DZI zoomable image
    zoom_filename = url_for('static', filename='/image_previews/folder{}/{}.dzi'.format(file_details['folder_id'], file_id))
    
    if os.path.isfile('static/image_previews/folder{}/{}.dzi'.format(file_details['folder_id'], file_id)):
        zoom_exists = 1
    else:
        zoom_exists = 0
        zoom_filename = None

    return render_template('file.html',
                           zoom_exists=zoom_exists,
                           zoom_filename=zoom_filename,
                           folder_info=folder_info,
                           file_details=file_details,
                           file_checks=file_checks,
                           file_postprocessing=file_postprocessing,
                           username=user_name,
                           image_url=image_url,
                           is_admin=is_admin,
                           project_alias=project_alias,
                           tables=[file_metadata.to_html(table_id='file_metadata', index=False, border=0,
                                                         escape=False,
                                                         classes=["display", "compact", "table-striped"])],
                           file_metadata_rows=file_metadata.shape[0],
                           file_links=file_links,
                           file_sensitive=str(file_sensitive),
                           sensitive_info=sensitive_info,
                           form=form,
                           site_env=site_env,
                           site_net=site_net,
                           site_ver=site_ver,
                           kiosk=kiosk,
                           user_address=user_address,
                           analytics_code=settings.analytics_code
                           )



@app.route('/file/', methods=['GET'], provide_automatic_options=False)
def file_empty():
    return redirect(url_for('homepage'))


@cache.memoize()
@app.route('/dashboard/<project_alias>/search_files', methods=['GET'], provide_automatic_options=False)
def search_files(project_alias):
    """Search files"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
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
        conn = mysql.connector.connect(host=settings.host,
                                user=settings.user,
                                password=settings.password,
                                database=settings.database,
                                port=settings.port, autocommit=True)
        conn.time_zone = '-04:00'
        cur = conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        logger.error(err)
        return jsonify({'error': 'API error'}), 500

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
        return render_template('error.html', error_msg=error_msg, project_alias=project_alias,
                               site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 400
    else:
        logger.info("q: {}".format(q))
        logger.info("metadata: {}".format(metadata))
        logger.info("offset: {}".format(offset))
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
                                      'q': '%' + q + '%'}, cur=cur)
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
                                      'q': '%' + q + '%'}, cur=cur)
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
                           site_ver=site_ver,
                           kiosk=kiosk,
                           user_address=user_address,
                           analytics_code=settings.analytics_code)


@cache.memoize()
@app.route('/dashboard/<project_alias>/search_folders', methods=['GET'], provide_automatic_options=False)
def search_folders(project_alias):
    """Search files"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
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
        conn = mysql.connector.connect(host=settings.host,
                                user=settings.user,
                                password=settings.password,
                                database=settings.database,
                                port=settings.port, autocommit=True)
        conn.time_zone = '-04:00'
        cur = conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        logger.error(err)
        return jsonify({'error': 'API error'}), 500

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
        return render_template('error.html', error_msg=error_msg, project_alias=project_alias,
                                site_net=site_net, site_env=site_env, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 400
    else:
        logger.info("q: {}".format(q))
        logger.info("offset: {}".format(offset))
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
                                  'q': '%' + q + '%'}, cur=cur)
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
                           site_ver=site_ver,
                           kiosk=kiosk,
                           user_address=user_address,
                           analytics_code=settings.analytics_code)


@app.route('/folder_update/<project_alias>/<folder_id>', methods=['GET'], provide_automatic_options=False)
@login_required
def update_folder_dams(project_alias=None, folder_id=None):
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
    if folder_id is None or project_alias is None:
        return redirect(url_for('home'))

    """Update folder when sending to DAMS"""
    # Connect to db
    try:
        conn = mysql.connector.connect(host=settings.host,
                                user=settings.user,
                                password=settings.password,
                                database=settings.database,
                                port=settings.port, autocommit=True)
        conn.time_zone = '-04:00'
        cur = conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        logger.error(err)
        return jsonify({'error': 'API error'}), 500

    # Set as in the way to DAMS
    damsupdate = query_database_insert(
        ("UPDATE folders SET delivered_to_dams = 1 WHERE folder_id = %(folder_id)s"),
        {'folder_id': folder_id}, cur=cur)
        
    # Del DAMS status badge, if exists
    delbadge = query_database_insert(
            ("DELETE FROM folders_badges WHERE folder_id = %(folder_id)s AND badge_type = 'dams_status'"),
                {'folder_id': folder_id}, cur=cur)

    # Set as Ready for DAMS
    delbadge = query_database_insert(
            ("INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text) "
             " VALUES (%(folder_id)s, 'dams_status', 'bg-secondary', 'Ready for DAMS')"),
                {'folder_id': folder_id}, cur=cur)

    # Update post-proc
    delbadge = query_database_insert(
            ("""
                INSERT INTO file_postprocessing
                    (file_id, post_results, post_step)
                (
                    SELECT
                        file_id, 0 as post_results, 'ready_for_dams' as post_step
                    FROM
                         (SELECT file_id FROM files WHERE folder_id = %(folder_id)s)
                        a
                ) ON
                DUPLICATE KEY UPDATE
                post_results = 0
            """),
                {'folder_id': folder_id}, cur=cur)

    # Update DAMS UAN
    delbadge = query_database_insert(
            ("""
                UPDATE files f,
                (
                    SELECT f.file_id, d.dams_uan
                    FROM
                        dams_cdis_file_status_view_dpo d,
                        files f,
                        folders fold,
                        projects p
                    WHERE
                        fold.folder_id = f.folder_id AND
                        fold.project_id = p.project_id AND
                        d.project_cd = p.dams_project_cd AND
                        d.file_name = CONCAT(f.file_name, '.tif') AND
                        f.folder_id =   %(folder_id)s
                ) d
                SET f.dams_uan = d.dams_uan
                WHERE f.file_id = d.file_id
            """),
                {'folder_id': folder_id}, cur=cur)

    # Update in DAMS
    damsupdate = query_database_insert(
            ("""
                INSERT INTO file_postprocessing
                    (file_id, post_results, post_step)
                (
                    SELECT
                         file_id,
                         0 as post_results,
                         'in_dams' as post_step
                    FROM
                     (
                     SELECT file_id FROM files
                     WHERE
                        folder_id = %(folder_id)s AND 
                        dams_uan != '' AND dams_uan IS NOT NULL
                     )
                    a
                ) ON
                DUPLICATE KEY UPDATE post_results = 0
            """),
                {'folder_id': folder_id}, cur=cur)

    no_files_ready = run_query(
        ("SELECT COUNT(*) as no_files FROM files WHERE folder_id = %(folder_id)s AND dams_uan != '' AND dams_uan IS NOT NULL"),
        {'folder_id': folder_id}, cur=cur)

    no_files_pending = run_query(
        ("SELECT COUNT(*) as no_files FROM files WHERE folder_id = %(folder_id)s AND (dams_uan = '' OR dams_uan IS NULL)"),
        {'folder_id': folder_id}, cur=cur)

    if no_files_ready[0]['no_files'] > 0 and no_files_pending[0]['no_files'] == 0:
        # Update in DAMS
        damsupdate = query_database_insert(
            ("UPDATE folders SET delivered_to_dams = 0 WHERE folder_id = %(folder_id)s"),
            {'folder_id': folder_id}, cur=cur)
        damsupdate = query_database_insert(
            ("DELETE FROM folders_badges WHERE folder_id = %(folder_id)s AND badge_type = 'dams_status'"),
            {'folder_id': folder_id}, cur=cur)
        damsupdate = query_database_insert(
            ("""
                INSERT INTO folders_badges 
                    (folder_id, badge_type, badge_css, badge_text) VALUES 
                    (%(folder_id)s, 'dams_status', 'bg-success', 'Delivered to DAMS')
            """), {'folder_id': folder_id}, cur=cur)
    cur.close()
    conn.close()
    return redirect(url_for('dashboard_f', project_alias=project_alias, folder_id=folder_id))












@app.route('/update_image/', methods=['POST'], provide_automatic_options=False)
@login_required
def update_image():
    """Update image as having sensitive contents"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
    # Connect to db
    try:
        conn = mysql.connector.connect(host=settings.host,
                                user=settings.user,
                                password=settings.password,
                                database=settings.database,
                                port=settings.port, autocommit=True)
        conn.time_zone = '-04:00'
        cur = conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        logger.error(err)
        return jsonify({'error': 'API error'}), 500

    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
        user_id = current_user.id
    else:
        cur.close()
        conn.close()
        return redirect(url_for('homepage'))

    file_id = int(request.form['file_id'])
    sensitive_info = request.form['sensitive_info']

    update = query_database_insert(
        ("INSERT INTO sensitive_contents (file_id, sensitive_contents, sensitive_info, user_id) VALUES (%(file_id)s, 1, %(sensitive_info)s, %(user_id)s) ON DUPLICATE KEY UPDATE sensitive_contents = 1"),
            {'file_id': file_id, 'sensitive_info': sensitive_info, 'user_id': current_user.id}, cur=cur)

    cur.close()
    conn.close()
    return redirect(url_for('file', file_id=file_id))
    





@app.route("/logout", methods=['GET'], provide_automatic_options=False)
def logout():
    logout_user()
    return redirect(url_for('homepage'))


@app.route("/notuser", methods=['GET'], provide_automatic_options=False)
def not_user():
    # Declare the login form
    form = LoginForm(request.form)
    logout_user()
    return render_template('notuser.html', form=form, site_env=site_env)



@cache.memoize()
@app.route('/reports/', methods=['GET'], provide_automatic_options=False)
def data_reports_form():
    """Report of a project"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
    # Declare the login form
    form = LoginForm(request.form)

    project_alias = request.values.get("project_alias")
    report_id = request.values.get("report_id")
    if project_alias is None or report_id is None:
        error_msg = "Report is not available."
        return render_template('error.html', error_msg=error_msg, project_alias=None, 
                               site_env=site_env, site_net=site_net, site_ver=site_ver), 404
    return redirect(url_for('data_reports', project_alias=project_alias, report_id=report_id))


@cache.memoize()
@app.route('/reports/<project_alias>/<report_id>/', methods=['GET'], provide_automatic_options=False)
def data_reports(project_alias=None, report_id=None):
    """Report of a project"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
    # Declare the login form
    form = LoginForm(request.form)

    # Connect to db
    try:
        conn = mysql.connector.connect(host=settings.host,
                                user=settings.user,
                                password=settings.password,
                                database=settings.database,
                                port=settings.port, autocommit=True)
        conn.time_zone = '-04:00'
        cur = conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        logger.error(err)
        return jsonify({'error': 'API error'}), 500

    if project_alias is None:
        error_msg = "Project is not available."
        return render_template('error.html', error_msg=error_msg, project_alias=None, site_env=site_env, site_net=site_net), 404

    # Declare the login form
    form = LoginForm(request.form)

    project_id = run_query(("SELECT project_id FROM projects WHERE project_alias = %(project_alias)s"),
                                {'project_alias': project_alias}, cur=cur)

    if len(project_id) == 0:
        error_msg = "Project was not found."
        return render_template('error.html', error_msg=error_msg, project_alias=project_id,
                               site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404

    project_id = project_id[0]['project_id']
    project_report = run_query(("SELECT * FROM data_reports WHERE "
                                     " project_id = %(project_id)s AND report_id = %(report_id)s"),
                                    {'project_id': project_id, 'report_id': report_id}, cur=cur)
    if len(project_report) == 0:
        error_msg = "Report was not found."
        cur.close()
        conn.close()
        return render_template('error.html', error_msg=error_msg, project_alias=project_alias,
                               site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404

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
                           site_net=site_net,
                           site_ver=site_ver,
                           analytics_code=settings.analytics_code
                           )


@cache.memoize()
@app.route('/preview_image/<file_id>/', methods=['GET', 'POST'], provide_automatic_options=False)
def get_preview(file_id=None, max=None, sensitive=None):
    """Return image previews"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
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
        conn = mysql.connector.connect(host=settings.host,
                                user=settings.user,
                                password=settings.password,
                                database=settings.database,
                                port=settings.port, autocommit=True)
        conn.time_zone = '-04:00'
        cur = conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        logger.error(err)
        return jsonify({'error': 'API error'}), 500
    
    data = run_query("SELECT folder_id FROM files WHERE file_id = %(file_id)s LIMIT 1", {'file_id': file_id}, cur=cur)
    logger.info(data)
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
            filename = "static/image_previews/folder{}/{}.jpg".format(folder_id, file_id)

            if width is not None:
                if os.path.isfile(filename):
                    img_resized = "static/image_previews/folder{}/{}/{}.jpg".format(folder_id, width, file_id)
                    if os.path.isfile(img_resized):
                        filename = img_resized
                    else:
                        logger.info(filename)
                        img = Image.open(filename)
                        wpercent = (int(width) / float(img.size[0]))
                        hsize = int((float(img.size[1]) * float(wpercent)))
                        img = img.resize((int(width), hsize), Image.LANCZOS)
                        filename = "/tmp/{}_{}.jpg".format(file_id, width)
                        img.save(filename, icc_profile=img.info.get('icc_profile'))
                else:
                    logger.info(filename)
                    filename = "static/na.jpg"
        except:
            filename = "static/na.jpg"
    if not os.path.isfile(filename):
        filename = "static/na.jpg"
    logger.debug("preview_request: {} - {}".format(file_id, filename))
    
    # Check for sensitive contents
    img = run_query("SELECT * FROM sensitive_contents WHERE file_id = %(file_id)s", {'file_id': file_id}, cur=cur)
    if len(img) == 0:
        img_sen = 0
    else:
        img_sen = img[0]['sensitive_contents']
    logger.debug("sensitive_contents: {} - {}".format(file_id, img_sen))
    sensitive = request.args.get('sensitive')
    
    if str(img_sen) == "1" and filename != "static/na.jpg" and sensitive != "ok":
        filename = "static/image_previews/folder{}/{}.jpg".format(folder_id, file_id)
        try:
            img = Image.open(filename)
            if width is not None:
                wpercent = (int(width) / float(img.size[0]))
                hsize = int((float(img.size[1]) * float(wpercent)))
                img = img.resize((int(width), hsize), Image.LANCZOS)
                img_blurred = img.filter(ImageFilter.GaussianBlur(radius = (hsize/100)))
            else:
                width = "000"
                img_blurred = img.filter(ImageFilter.GaussianBlur(radius = (img.size[1]/100)))
            filename = "/tmp/{}_{}.jpg".format(file_id, width)
            img_blurred.save(filename, icc_profile=img.info.get('icc_profile'))
            logger.info("Img blurred {} {}".format(file_id, filename))
        except:
            logger.error("Sensitive {} {}".format(file_id, filename))
            filename = "static/na.jpg"
    
    cur.close()
    conn.close()

    try:
        return send_file(filename, mimetype='image/jpeg')
    except:
        return send_file("static/na.jpg", mimetype='image/jpeg')



@cache.memoize()
@app.route('/barcode_image/<barcode>/', methods=['GET', 'POST'], provide_automatic_options=False)
def get_barcodeimage(barcode=None):
    """Return image previews using a barcode that has a collex prefix in format: prefix:barcode"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
    if barcode is None:
        raise InvalidUsage('barcode value missing', status_code=400)
    #
    barcode_split = barcode.split(":")
    if len(barcode_split) != 2:
        raise InvalidUsage('Invalid barcode', status_code=400)

    # Connect to db
    try:
        conn = mysql.connector.connect(host=settings.host,
                                user=settings.user,
                                password=settings.password,
                                database=settings.database,
                                port=settings.port, autocommit=True)
        conn.time_zone = '-04:00'
        cur = conn.cursor(dictionary=True)
    except mysql.connector.Error as err:
        logger.error(err)
        return jsonify({'error': 'API error'}), 500

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
            logger.info("data: {}".format(data))
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
            logger.info(filename)
            filename = "static/na.jpg"
    logger.debug("barcode_request: {} - {}".format(barcode, filename))
    cur.close()
    conn.close()
    try:
        return send_file(filename, mimetype='image/jpeg')
    except:
        return send_file("static/na.jpg", mimetype='image/jpeg')


@cache.memoize()
@app.route('/api/', methods=['GET', 'POST'], strict_slashes=False, provide_automatic_options=False)
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
    data = {'routes': func_list, 'sys_ver': site_ver, 'env': site_env, 'net': site_net}
    return jsonify(data)


#####################################
if __name__ == '__main__':
    if site_env == "dev":
        app.run(threaded=True, debug=True)
    else:
        app.run(threaded=True, debug=False)
