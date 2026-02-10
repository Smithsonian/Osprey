#!flask/bin/python
#
# DPO Osprey Dashboard
#
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
from flask import send_from_directory

from cache import cache
# Logging
from logger import logger

import os
import locale
import math
import pandas as pd
import numpy as np
import io
from datetime import datetime
from PIL import Image
from PIL import ImageFilter
from uuid import UUID
from pathlib import Path
from time import strftime
from time import localtime
import glob
import random
from plotnine import ggplot
from plotnine import aes
from plotnine import geom_bar
from ldap3 import Server, Connection, ALL, NTLM
from ldap3.core.exceptions import LDAPBindError as LDAPBindError
from ldap3 import set_config_parameter
import time
import tarfile
import subprocess

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
from werkzeug.utils import secure_filename

import settings

site_ver = "2.9.1"
site_env = settings.env
site_net = settings.site_net

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

# For subdirs
def prefix_route(route_function, prefix='', mask='{0}{1}'):
  '''
    Defines a new route function with a prefix.
    The mask argument is a `format string` formatted with, in that order:
      prefix, route
  '''
  def newroute(route, *args, **kwargs):
    '''New function to prefix the route'''
    return route_function(mask.format(prefix, route), *args, **kwargs)
  return newroute
        
app.route = prefix_route(app.route, '/')

# Minify responses
if site_env == "prod":
    from flask_minify import Minify
    Minify(app=app, html=True, js=True, cssless=True)

# Add logger
app.logger.addHandler(logger)

# Setup cache
cache.init_app(app)

# Disable strict trailing slashes
app.url_map.strict_slashes = True


# Connect to Mysql
try:
    conn = mysql.connector.connect(host=settings.host,
                            user=settings.user,
                            password=settings.password,
                            database=settings.database,
                            port=settings.port, 
                            autocommit=True, 
                            connection_timeout=60)
    conn.time_zone = '-05:00'
    cur = conn.cursor(dictionary=True)
except mysql.connector.Error as err:
    logger.error(err)


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


def run_query(query, parameters=None, return_val=True, log_vals=True):
    if log_vals == True:
        logger.info("parameters: {}".format(parameters))
        logger.info("query: {}".format(query))
    # Check connection to DB and reconnect if needed
    conn.ping(reconnect=True, attempts=3, delay=1)
    # Run query
    if parameters is None:
        results = cur.execute(query)
    else:
        results = cur.execute(query, parameters)
    if return_val:
        data = cur.fetchall()
        logger.info("No of results: ".format(len(data)))
        return data
    else:
        return True


def query_database_insert(query, parameters, return_res=False):
    logger.info("query: {}".format(query))
    logger.info("parameters: {}".format(parameters))
    # Check connection to DB and reconnect if needed
    conn.ping(reconnect=True, attempts=3, delay=1)
    # Run query
    data = False
    try:
        results = cur.execute(query, parameters)
    except Exception as error:
        logger.error("Error: {}".format(error))
        return False
    logger.info("Query: {}".format(cur.statement))    
    if return_res:
        insert_id = cur.lastrowid
        return(insert_id)
    return True


@cache.memoize()
def project_alias_exists(project_alias=None):
    if project_alias is None:
        return False
    else:
        project_id = run_query("SELECT project_id FROM projects WHERE project_alias = %(project_alias)s",
                                    {'project_alias': project_alias})
        if len(project_id) == 0:
            return False
        else:
            return project_id[0]['project_id']


def check_file_id(file_id=None):
    if file_id is None:
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
        file_id = run_query("SELECT file_id FROM files WHERE uid = %(uid)s", {'uid': file_uid})
        if len(file_id) == 0:
            return False, False
        else:
            return file_id[0]['file_id'], file_uid
    else:
        file_uid = run_query("SELECT uid FROM files WHERE file_id = %(file_id)s", {'file_id': file_id})
        if len(file_uid) == 0:
            return False, False
        else:
            return file_id, file_uid[0]['uid']


def check_file_id_transcription(file_id=None):
    if file_id is None:
        return False
    else:
        try:
            file_uid = UUID(file_id, version=4)
        except ValueError:
            return False
    file_id = run_query("SELECT file_transcription_id as file_id FROM transcription_files WHERE file_transcription_id = %(uid)s", {'uid': str(file_uid)})
    if len(file_id) == 0:
        return False
    else:
        return file_id[0]['file_id']
    

@cache.memoize()
def user_perms(project_id, user_type='user'):
    try:
        user_name = current_user.name
    except:
        return False
    val = False
    if user_type == 'user':
        query = ("SELECT COUNT(*) as is_user FROM qc_projects p, users u "
                 " WHERE p.user_id = u.user_id AND p.project_id = %(project_id)s AND u.username = %(user_name)s")
        is_user = run_query(query, {'project_id': project_id, 'user_name': user_name})
        val = is_user[0]['is_user'] == 1
    if user_type == 'admin':
        query = "SELECT is_admin FROM users WHERE username = %(user_name)s"
        is_admin = run_query(query, {'user_name': user_name})
        val = is_admin[0]['is_admin'] == 1
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
        query = ("SELECT user_active FROM users WHERE username = %(username)s")
        user = run_query(query, {'username': name})
        return user

    def is_anonymous(self):
        return False

    def is_authenticated(self):
        return True


@login_manager.user_loader
def load_user(username):
    query = ("SELECT username, user_id, user_active, full_name FROM users WHERE username = %(username)s")
    u = run_query(query, {'username': username})
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
@app.route('/static/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico', mimetype='image/vnd.microsoft.icon')


@cache.memoize()
@app.route('/team/<team>/<subset>', methods=['GET', 'POST'], provide_automatic_options=False)
@app.route('/team/<team>', methods=['GET', 'POST'], provide_automatic_options=False)
@app.route('/', methods=['GET', 'POST'], provide_automatic_options=False)
def homepage(team=None, subset=None):
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

    # Last update
    last_update = run_query("SELECT date_format(MAX(updated_at), '%d-%b-%Y') AS updated_at FROM projects_stats")

    mass_digi_total = 0

    if team is None:
        team = "summary"
        team_heading = "Collections Digitization - Highlights"
        html_title = "Collections Digitization Dashboard"

        # Summary stats
        summary_stats = {
            'objects_digitized': "{:,}".format(run_query(("SELECT SUM(objects_digitized) as total "
                       " from projects_stats where project_id NOT IN (SELECT project_id FROM projects WHERE skip_project IS True)"))[0]['total']),
            'images_captured': "{:,}".format(run_query(("SELECT SUM(images_taken) as total "
                     " from projects_stats where project_id NOT IN (SELECT project_id FROM projects WHERE skip_project IS True)"))[0]['total']),
            'digitization_projects': "{:,}".format(
                     run_query(("SELECT COUNT(*) as total FROM projects WHERE skip_project IS NOT True"))[0]['total']),
            'active_projects': "{:,}".format(run_query(("SELECT COUNT(*) as total "
                       " FROM projects WHERE skip_project IS NOT True AND project_status='Ongoing'"))[0]['total']),
            'images_public': "{:,}".format(run_query(("SELECT SUM(images_public) as total "
                       " FROM projects_stats WHERE project_id NOT IN (SELECT project_id FROM projects WHERE skip_project IS True)"))[0]['total'])
        }
    elif team == "md":
        team_heading = "Summary of Mass Digitization Team Projects"
        html_title = "Mass Digitization Team Projects, Collections Digitization"

        # MD stats
        summary_stats = {
            'objects_digitized': "{:,}".format(run_query(
                    "SELECT SUM(objects_digitized) as total "
                    "from projects_stats where project_id IN "
                    "   (SELECT project_id FROM projects WHERE project_section = 'MD' AND skip_project IS NOT True)")[0]['total']),
            'images_captured': "{:,}".format(run_query(
                "SELECT SUM(images_taken) as total "
                "from projects_stats WHERE project_id IN "
                "   (SELECT project_id FROM projects WHERE project_section = 'MD' AND skip_project IS NOT True)")[0]['total']),
            'digitization_projects': "{:,}".format(run_query(
                "SELECT COUNT(*) as total "
                "FROM projects WHERE project_section = 'MD' AND "
                " skip_project IS NOT True")[0]['total']),
            'active_projects': "{:,}".format(run_query(
                "SELECT COUNT(*) as total "
                "FROM projects WHERE project_section = 'MD' AND skip_project IS NOT True AND "
                " project_status='Ongoing'")[0]['total']),
            'images_public': "{:,}".format(run_query(("SELECT SUM(images_public) as total "
                      " FROM projects_stats WHERE project_id IN (SELECT project_id "
                      " FROM projects WHERE skip_project IS NOT True AND project_section = 'MD')"))[0]['total'])
        }
        no_items = run_query(("SELECT SUM(objects_digitized) as total from projects_stats where project_id IN (SELECT project_id FROM projects WHERE project_section = 'MD' AND skip_project IS NOT True)"))[0]['total']
        mass_digi_total = math.floor((int(no_items)*1.0)/100000)/10

    elif team == "is":
        team_heading = "Summary of Imaging Services Team Projects"
        html_title = "Imaging Services Team Projects, Collections Digitization"
        # IS stats
        summary_stats = {
            'objects_digitized': "{:,}".format(run_query(
                    "SELECT SUM(objects_digitized) as total "
                    "from projects_stats where project_id IN "
                    "   (SELECT project_id FROM projects WHERE project_section = 'IS' AND skip_project IS NOT True)")[0]['total']),
            'images_captured': "{:,}".format(run_query(
                    "SELECT SUM(images_taken) as total "
                    "from projects_stats where project_id IN "
                    "   (SELECT project_id FROM projects WHERE project_section = 'IS' AND skip_project IS NOT True)")[0]['total']),
            'digitization_projects': "{:,}".format(
                        run_query(
                            "SELECT COUNT(*) as total "
                            "FROM projects WHERE project_section = 'IS' AND "
                            " skip_project IS NOT True")[0]['total']),
            'active_projects': "{:,}".format(run_query(("SELECT COUNT(*) as total "
                            "FROM projects WHERE project_section = 'IS' AND "
                            " skip_project IS NOT True AND project_status='Ongoing'"))[0]['total']),
            'images_public': "{:,}".format(run_query(("SELECT SUM(images_public) as total "
                          " FROM projects_stats WHERE project_id IN "
                          "   (SELECT project_id FROM projects WHERE skip_project IS NOT True AND project_section = 'IS')"))[0]['total'])
        }

    elif team == "inf":
        team_heading = "Summary of Informatics Team Projects"
        html_title = "Summary of the Informatics Team Projects, Collections Digitization"
        # IS stats
        summary_stats = {
            'digitization_projects': "{:,}".format(
                        run_query(
                            "SELECT COUNT(*) as total "
                            "FROM projects_informatics")[0]['total']),
            'active_projects': "{:,}".format(run_query(("SELECT COUNT(*) as total "
                            "FROM projects_informatics WHERE project_status='Ongoing'"))[0]['total']),
            'records': "{:,}".format(run_query(("SELECT SUM(records) as total "
                          " FROM projects_informatics WHERE records_redundant IS False"))[0]['total'])
        }

    section_query = ((" SELECT "
                     " p.projects_order, "
                     " CONCAT('<abbr title=\"', u.unit_fullname, '\" class=\"bg-white\">', p.project_unit, '</abbr>') as project_unit, "
                     "      CASE WHEN "
                     "             p.project_alias IS NULL "
                     "              THEN p.project_title "
                     "      ELSE "
                     "          (CASE WHEN "
                     "              p.project_status = 'Ongoing' and ps.collex_to_digitize != 0 "
                     "              THEN "
                     "              CONCAT('<a href=\"{app_root}/dashboard/', p.project_alias, '\" class=\"bg-white\">', p.project_title, '</a><br>"
                     "                  <small>Estimated Progress: ', ROUND((ps.objects_digitized/ps.collex_to_digitize) * 100), ' % "
                     "                  <div class=\"progress\"> "
                     "                      <div class=\"progress-bar bg-success\" role=\"progressbar\" style=\"width: ', "
                     "                          ROUND((ps.objects_digitized/ps.collex_to_digitize) * 100), '%\" "
                     "                         aria-valuenow=\"', ROUND((ps.objects_digitized/ps.collex_to_digitize) * 100), '\" aria-valuemin=\"0\" aria-valuemax=\"100\"> "
                     "                      </div> "
                     "                   </div></small>"
                     "              ') "
                     "          ELSE "
                     "              CONCAT('<a href=\"{app_root}/dashboard/', p.project_alias, '\" class=\"bg-white\">', p.project_title, '</a>') "
                     "          END) "
                     "      END as project_title, "
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
                     " ORDER BY p.projects_order DESC").format(app_root=settings.app_root))
    list_projects_md = pd.DataFrame(run_query(section_query, {'section': 'MD'}))
    list_projects_md = list_projects_md.drop("images_public", axis=1)
    list_projects_md = list_projects_md.rename(columns={
        "project_unit": "Unit",
        "project_title": "Title",
        "project_status": "Status",
        "project_manager": "<abbr title=\"Project Manager\" class=\"bg-white\">PM</abbr>",
        "project_dates": "Dates",
        "objects_digitized": "Specimens/Objects Digitized",
        "images_taken": "Images Captured"
    })

    list_projects_is = pd.DataFrame(run_query(section_query, {'section': 'IS'}))
    list_projects_is = list_projects_is.drop("images_public", axis=1)

    # Filter 
    if subset is None:
        subset = ""
    else:
        if subset.lower() == "sawhm":
            list_projects_is = list_projects_is[list_projects_is.project_manager == 'Laura M. Whitfield']

    list_projects_is = list_projects_is.rename(columns={
        "project_unit": "Unit",
        "project_title": "Title",
        "project_status": "Status",
        "project_manager": "<abbr title=\"Project Manager\" class=\"bg-white\">PM</abbr>",
        "project_dates": "Dates",
        "objects_digitized": "Specimens/Objects Digitized",
        "images_taken": "Images Captured"
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
    list_projects_inf = pd.DataFrame(run_query(inf_section_query))
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
    list_software = pd.DataFrame(run_query(inf_software))
    list_software = list_software.rename(columns={
        "software_name": "Software",
        "software_details": "Details",
        "repository": "Repository",
        "more_info": "Details"
    })

    # kiosk mode
    kiosk, user_address = kiosk_mode(request, settings.kiosks)
    if settings.site_net == "internal":
        asklogin = True
    else:
        asklogin = False
    return render_template('home.html',
                           form=form, msg=msg, user_exists=user_exists,
                           username=username, summary_stats=summary_stats, team=team,
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
                           asklogin=asklogin, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           last_update=last_update[0]['updated_at'], mass_digi_total=mass_digi_total,
                           kiosk=kiosk, user_address=user_address, team_heading=team_heading,
                           html_title=html_title, analytics_code=settings.analytics_code,
                           app_root=settings.app_root,
                           subset=subset.upper())


@app.route('/login', methods=['POST'], provide_automatic_options=False)
def login():
    """Login into the system with LDAP"""
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
    # Declare the login form
    form = LoginForm(request.form)

    # Flask message injected into the page, in case of any errors
    msg = None
    # check if both http method is POST and form is valid on submit
    if form.validate_on_submit():
        # assign form data to variables
        username = request.form.get('username', type=str).strip().lower()
        password = request.form.get('password', type=str)
        if username[-7:] != "@si.edu":
            logger.error("Login error - missing @si.edu")
            return redirect(url_for('not_user'))
        # Login using LDAP
        server = Server(settings.ldap_server, port = 636, use_ssl = True, get_info=ALL)
        logger.info("LDAP (server): {}".format(server))
        logger.info("LDAP (user): {}".format(username))
        query = ("SELECT user_id, username, user_active, full_name, internal FROM users WHERE email = %(email)s")
        user = run_query(query, {'email': username})
        logger.info("Trying to log in: {}".format(user))
        if len(user) == 1:
            if user[0]['internal'] == "1":
                query = ("SELECT user_id, username, user_active, full_name, internal FROM users WHERE email = %(email)s and pass = %(password)s")
                user = run_query(query, {'email': username, 'password': password})
                if len(user) != 1:
                    logger.error("Internal user failed login: {}".format(username))
                    logger.error("Login error - Internal password error")
                    return redirect(url_for('not_user'))
            else:
                try:
                    set_config_parameter('DEFAULT_SERVER_ENCODING', 'utf-8')
                    conn = Connection(server, user=username, password=password, auto_bind=True)
                    logger.info("LDAP (conn): {}".format(print(conn)))
                    conn.extend.standard.who_am_i()
                    logger.info("LDAP (who_am_i): {}".format(conn.extend.standard.who_am_i()))
                except LDAPBindError as e:
                    # Try latin-1
                    # Pause before trying again
                    time.sleep(3)
                    logger.info("LDAP trying latin-1")
                    set_config_parameter('DEFAULT_SERVER_ENCODING', 'latin-1')
                    try:
                        conn = Connection(server, user=username, password=password, auto_bind=True)
                        logger.info("LDAP latin-1 (conn): {}".format(print(conn)))
                        conn.extend.standard.who_am_i()
                        logger.info("LDAP latin-1 (who_am_i): {}".format(conn.extend.standard.who_am_i()))
                    except LDAPBindError as e:
                        logger.error("LDAP: {} - {}".format(username, e))
                        logger.error("Login error - LDAP")
                        return redirect(url_for('not_user'))
            #
            username = user[0]['username']
            logger.info(user[0]['user_active'])
            if user[0]['user_active']:
                user_obj = User(user[0]['user_id'], user[0]['username'], 
                                user[0]['full_name'], user[0]['user_active'])
                login_user(user_obj)
                return redirect(url_for('home'))
            else:
                # msg = "Error, user not known or password was incorrect"
                logger.error("Login error - user not active")
                return redirect(url_for('not_user'))
        else:
            # msg = "Error, user not known or password was incorrect"
            logger.error("Login error - user not in db")
            return redirect(url_for('not_user'))
    else:
        # msg = "Error, user not known or password was incorrect"
        logger.error("Login error - bad request")
        return redirect(url_for('not_user'))


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
        transcription = 0
    except ValueError:
        try:
            folder_id = UUID(folder_id, version=4)
            transcription = 1
            folder_id = str(folder_id)
        except ValueError:
            error_msg = "Folder not found"
            return render_template('error.html', error_msg=error_msg,
                                    project_alias=project_alias, site_env=site_env, site_net=site_net,
                                    analytics_code=settings.analytics_code), 404

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
    
    # Check if project exists
    if project_alias_exists(project_alias) is False:
        # Check if project alias in list of redirects
        try:
            if project_alias_exists(settings.proj_redirect[project_alias]):
                logger.info("project_alias_redirect: {}".format(project_alias))
                return redirect(url_for('dashboard', project_alias=settings.proj_redirect[project_alias]))
        except KeyError:
            error_msg = "Project was not found."
            return render_template('error.html', error_msg=error_msg,
                                project_alias=project_alias, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404

    project_id_check = run_query("SELECT project_id FROM projects WHERE project_alias = %(project_alias)s",
                                      {'project_alias': project_alias})
    if len(project_id_check) == 0:
        error_msg = "Project was not found."
        return render_template('error.html', error_msg=error_msg,
                               project_alias=project_alias, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404
    else:
        project_id = project_id_check[0]['project_id']

    # Check if folder exists
    if transcription == 0:
        folder_check = run_query(
            ("SELECT folder_id FROM folders "
            " WHERE folder_id = %(folder_id)s AND project_id = %(project_id)s"),
            {'folder_id': folder_id, 'project_id': project_id})
    else:
        folder_check = run_query(
            ("SELECT folder_transcription_id FROM transcription_folders "
            " WHERE folder_transcription_id = %(folder_id)s AND project_id = %(project_id)s"),
            {'folder_id': str(folder_id), 'project_id': project_id})
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
                                       {'username': username, 'project_id': project_id})[0]
        if project_admin['no_results'] > 0:
            project_admin = True
        else:
            project_admin = False
        logger.info("project_admin: {} - {}".format(username, project_admin))
    else:
        project_admin = False
    project_info = run_query("SELECT *, "
                             "      CONCAT(date_format(project_start, '%d-%b-%Y'), "
                             "      CASE WHEN project_end IS NULL THEN '' ELSE CONCAT(' to ', date_format(project_end, '%d-%b-%Y')) END "
                             "          ) as pdates "
                             " FROM projects WHERE project_alias = %(project_alias)s",
                                  {'project_alias': project_alias})[0]
    logger.info(project_info)
    project_manager_link = project_info['project_manager']
    if project_info['project_manager'] == "Jeanine Nault":
        project_manager_link = "<a href=\"https://dpo.si.edu/jeanine-nault\">Jeanine Nault</a>"
    elif project_info['project_manager'] == "Nathan Ian Anderson":
        project_manager_link = "<a href=\"https://dpo.si.edu/nathan-ian-anderson\">Nathan Ian Anderson</a>"
    elif project_info['project_manager'] == "Erin M. Mazzei":
        project_manager_link = "<a href=\"https://dpo.si.edu/erin-mazzei\">Erin M. Mazzei</a>"
    elif project_info['project_manager'] == "Laura M. Whitfield":
        project_manager_link = "<a href=\"https://dpo.si.edu/laura-whitfield\">Laura M. Whitfield</a>"

    projects_links = run_query("SELECT * FROM projects_links WHERE project_id = %(project_id)s ORDER BY table_id",
                                  {'project_id': project_info['project_id']})

    project_statistics = run_query(("SELECT * FROM projects_stats WHERE project_id = %(project_id)s"), {'project_id': project_id})[0]
    project_stats['total'] = format(int(project_statistics['images_taken']), ',d')
    project_stats['ok'] = format(int(project_statistics['project_ok']), ',d')
    project_stats['errors'] = format(int(project_statistics['project_err']), ',d')

    
    if project_info['transcription'] == 1:
        transcription = 1
        no_fold = run_query(("SELECT count(folder) as folders FROM transcription_folders f WHERE f.project_id = %(project_id)s"),
                                        {'project_id': project_id})[0]
        project_stats['no_folders'] = format(int(no_fold['folders']), ',d')
        project_folders = run_query(("SELECT f.folder as project_folder, f.folder_transcription_id as folder_id, coalesce(b1.badge_text, '0 Files') as no_files, "
                                      "f.file_errors, f.status, f.error_info, "
                                      "f.delivered_to_dams, "
                                      " COALESCE(CASE WHEN qcf.qc_status = 0 THEN 'QC Passed' "
                                      "              WHEN qcf.qc_status = 1 THEN 'QC Failed' "
                                      "              WHEN qcf.qc_status = 9 THEN 'QC Pending' END,"
                                      "          'QC Pending') as qc_status,"
                                      "   b.badge_text, "
                                      " f.previews "
                                      "FROM transcription_folders f "
                                      "     LEFT JOIN qc_folders qcf ON (f.folder_transcription_id = qcf.folder_uid) "
                                      "     LEFT JOIN folders_badges b ON (f.folder_transcription_id = b.folder_uid AND b.badge_type = 'verification') "
                                      "     LEFT JOIN folders_badges b1 ON (f.folder_transcription_id = b1.folder_uid AND b1.badge_type = 'no_files') "
                                      " WHERE f.project_id = %(project_id)s and f.delivered_to_dams != 0 "
                                      " ORDER BY f.date DESC, f.folder DESC"),
                                     {'project_id': project_id})
        project_folders_indams = run_query(("SELECT f.folder as project_folder, f.folder_transcription_id as folder_id, coalesce(b1.badge_text, 0) as no_files "
                                      "FROM transcription_folders f "
                                      "     LEFT JOIN folders_badges b1 ON (f.folder_transcription_id = b1.folder_uid AND b1.badge_type = 'no_files') "
                                      " WHERE f.project_id = %(project_id)s and f.delivered_to_dams = 0 "
                                      " ORDER BY f.folder ASC"),
                                     {'project_id': project_id})
    else:
        transcription = 0
        no_fold = run_query(("SELECT count(project_folder) as folders FROM folders f WHERE f.project_id = %(project_id)s"),
                                        {'project_id': project_id})[0]
        project_stats['no_folders'] = format(int(no_fold['folders']), ',d')
        project_folders = run_query(("SELECT f.project_folder, f.folder_id, coalesce(b1.badge_text, '0 Files') as no_files, "
                                      "f.file_errors, f.status, f.error_info, "
                                      "f.delivered_to_dams, "
                                      " COALESCE(CASE WHEN qcf.qc_status = 0 THEN 'QC Passed' "
                                      "              WHEN qcf.qc_status = 1 THEN 'QC Failed' "
                                      "              WHEN qcf.qc_status = 9 THEN 'QC Pending' END,"
                                      "          'QC Pending') as qc_status,"
                                      "   b.badge_text, "
                                      " f.previews "
                                      "FROM folders f "
                                      "     LEFT JOIN qc_folders qcf ON (f.folder_id = qcf.folder_id) "
                                      "     LEFT JOIN folders_badges b ON (f.folder_id = b.folder_id AND b.badge_type = 'verification') "
                                      "     LEFT JOIN folders_badges b1 ON (f.folder_id = b1.folder_id AND b1.badge_type = 'no_files') "
                                      " WHERE f.project_id = %(project_id)s and f.delivered_to_dams != 0 "
                                      " ORDER BY f.date DESC, f.project_folder DESC"),
                                     {'project_id': project_id})
        project_folders_indams = run_query(("SELECT f.project_folder, f.folder_id, coalesce(b1.badge_text, 0) as no_files "
                                      "FROM folders f "
                                      "     LEFT JOIN folders_badges b1 ON (f.folder_id = b1.folder_id AND b1.badge_type = 'no_files') "
                                      " WHERE f.project_id = %(project_id)s and f.delivered_to_dams = 0 "
                                      " ORDER BY f.project_folder ASC"),
                                     {'project_id': project_id})
    # Get objects
    proj_obj = run_query(("SELECT COALESCE(objects_digitized, 0) as no_objects FROM projects_stats WHERE "
                          " project_id = %(project_id)s"),
                         {'project_id': project_id})
    project_stats['objects'] = format(int(proj_obj[0]['no_objects']), ',d')
    project_stats_other = run_query(("SELECT other_icon, other_name, COALESCE(other_stat, 0) as other_stat FROM projects_stats WHERE project_id = %(project_id)s"), {'project_id': project_id})[0]
    project_stats_other['other_stat'] = format(int(project_stats_other['other_stat']), ',d')

    if transcription == 1:
        project_folders_badges = run_query("SELECT f.folder_transcription_id as folder_id, b.badge_type, b.badge_css, b.badge_text FROM folders_badges b, transcription_folders f WHERE b.folder_uid = f.folder_transcription_id and f.project_id = %(project_id)s and b.badge_type != 'no_files' and f.delivered_to_dams != 0", {'project_id': project_id})
    else:
        project_folders_badges = run_query("SELECT b.folder_id, b.badge_type, b.badge_css, b.badge_text FROM folders_badges b, folders f WHERE b.folder_id = f.folder_id and f.project_id = %(project_id)s and b.badge_type != 'no_files' and f.delivered_to_dams != 0", {'project_id': project_id})
    
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
        if transcription == 1:
            folder_id = str(folder_id)
            folder_name = run_query(("SELECT folder as project_folder, date_format(updated_at, '%Y-%b-%d %T') as last_updated FROM transcription_folders "
                                 "WHERE folder_transcription_id = %(folder_id)s and project_id = %(project_id)s"),
                                     {'folder_id': folder_id, 'project_id': project_id})
        else:
            folder_name = run_query(("SELECT project_folder, date_format(updated_at, '%Y-%b-%d %T') as last_updated FROM folders "
                                 "WHERE folder_id = %(folder_id)s and project_id = %(project_id)s"),
                                     {'folder_id': folder_id, 'project_id': project_id})        
        logger.info("folder_name: {}".format(len(folder_name)))
        if len(folder_name) == 0:
            error_msg = "Folder does not exist in this project."
            return render_template('error.html', error_msg=error_msg, project_alias=project_alias,
                                   site_env=site_env, site_net=site_net, site_ver=site_ver), 404
        else:
            folder_name = folder_name[0]
            fol_last_update = folder_name['last_updated']

        if transcription == 1:
            folder_files_df = pd.DataFrame(
                run_query("SELECT file_transcription_id as file_id, file_name FROM transcription_files WHERE folder_transcription_id = %(folder_id)s",
                        {'folder_id': folder_id}))
        else:
            folder_files_df = pd.DataFrame(
                run_query("SELECT file_id, file_name FROM files WHERE folder_id = %(folder_id)s",
                        {'folder_id': folder_id}))
        
        no_items = 25
        if page == 1:
            offset = 0
        else:
            offset = (page - 1) * no_items
        
        if transcription == 1:
            files_df = run_query((
                                 "WITH data AS (SELECT f.file_transcription_id as file_id, CONCAT('{app_root}/preview_image/', f.file_transcription_id, '/?') as preview_image, "
                                 "         f.preview_image as preview_image_ext, f.folder_transcription_id as folder_id, f.file_name "
                                 "           FROM transcription_files f "
                                 " WHERE f.folder_transcription_id = %(folder_id)s)"
                                 " SELECT file_id, preview_image, preview_image_ext, folder_id, file_name, 0 as sensitive_contents "
                                 " FROM data "
                                 " ORDER BY file_name "
                                 "LIMIT {no_items} OFFSET {offset}").format(offset=offset, no_items=no_items, app_root=settings.app_root),
                             {'folder_id': folder_id})
            files_count = run_query("SELECT count(*) as no_files FROM transcription_files WHERE folder_transcription_id = %(folder_id)s",
                                {'folder_id': folder_id})[0]
        else:
            files_df = run_query((
                                 "WITH data AS (SELECT f.file_id, CONCAT('{app_root}/preview_image/', f.file_id, '/?') as preview_image, "
                                 "         f.preview_image as preview_image_ext, f.folder_id, f.file_name, "
                                 "               COALESCE(s.sensitive_contents, 0) as sensitive_contents "
                                 "           FROM files f LEFT JOIN sensitive_contents s ON f.file_id = s.file_id "
                                 " WHERE f.folder_id = %(folder_id)s)"
                                 " SELECT file_id, preview_image, preview_image_ext, folder_id, file_name, sensitive_contents "
                                 " FROM data "
                                 " ORDER BY file_name "
                                 "LIMIT {no_items} OFFSET {offset}").format(offset=offset, no_items=no_items, app_root=settings.app_root),
                             {'folder_id': folder_id})
            files_count = run_query("SELECT count(*) as no_files FROM files WHERE folder_id = %(folder_id)s",
                                {'folder_id': folder_id})[0]
            
        files_count = files_count['no_files']
        if tab == "filechecks":
            filechecks_list_temp = run_query(
                ("SELECT settings_value as file_check FROM projects_settings "
                " WHERE project_setting = 'project_checks' and project_id = %(project_id)s"),
                {'project_id': project_info['project_id']})
            filechecks_list = []
            for fcheck in filechecks_list_temp:
                filechecks_list.append(fcheck['file_check'])
            logger.info("filechecks_list:{}".format(filechecks_list_temp))
            project_postprocessing = []

            page_no = "File Checks"
            if files_count == 0:
                folder_files_df = pd.DataFrame()
                pagination_html = ""
                files_df = ""
                files_count = ""
                folder_stats = {'no_files': 0, 'no_errors': 0}
            else:
                for fcheck in filechecks_list:
                    logger.info("fcheck: {}".format(fcheck))
                    if transcription == 1:
                        list_files = pd.DataFrame(run_query(("SELECT f.file_transcription_id as file_id, "
                                                              "   CASE WHEN check_results = 0 THEN 'OK' "
                                                              "       WHEN check_results = 9 THEN 'Pending' "
                                                              "       WHEN check_results = 1 THEN 'Failed' "
                                                              "       ELSE 'Pending' END as {fcheck} "
                                                              " FROM transcription_files f LEFT JOIN transcription_files_checks c ON (f.file_transcription_id=c.file_transcription_id AND c.file_check = %(file_check)s) "
                                                              "  where f.folder_transcription_id = %(folder_id)s").format(fcheck=fcheck),
                                                             {'file_check': fcheck, 'folder_id': folder_id}))
                    else:
                        list_files = pd.DataFrame(run_query(("SELECT f.file_id, "
                                                              "   CASE WHEN check_results = 0 THEN 'OK' "
                                                              "       WHEN check_results = 9 THEN 'Pending' "
                                                              "       WHEN check_results = 1 THEN 'Failed' "
                                                              "       ELSE 'Pending' END as {fcheck} "
                                                              " FROM files f LEFT JOIN files_checks c ON (f.file_id=c.file_id AND c.file_check = %(file_check)s) "
                                                              "  where f.folder_id = %(folder_id)s").format(fcheck=fcheck),
                                                             {'file_check': fcheck, 'folder_id': folder_id}))
                    logger.info("list_files.size: {}".format(list_files.shape[0]))
                    if list_files.shape[0] > 0:
                        folder_files_df = folder_files_df.merge(list_files, how='outer', on='file_id')
                if transcription == 1:
                    preview_files = pd.DataFrame(run_query(("SELECT f.file_transcription_id as file_id, "
                                                             "  CASE WHEN f.preview_image is NULL THEN CONCAT('/preview_image/', f.file_transcription_id, '/?') ELSE f.preview_image END as preview_image "
                                                             " FROM transcription_files f where f.folder_transcription_id = %(folder_id)s"),
                                                            {'folder_id': folder_id}))
                else:
                    preview_files = pd.DataFrame(run_query(("SELECT f.file_id, "
                                                             "  CASE WHEN f.preview_image is NULL THEN CONCAT('/preview_image/', f.file_id, '/?') ELSE f.preview_image END as preview_image "
                                                             " FROM files f where f.folder_id = %(folder_id)s"),
                                                            {'folder_id': folder_id}))
                folder_files_df = folder_files_df.sort_values(by=['file_name'])
                folder_files_df = folder_files_df.sort_values(by=filechecks_list)
                folder_files_df = folder_files_df.merge(preview_files, how='outer', on='file_id')
                if transcription == 1:
                    folder_files_df['file_name'] = '<a href="{}/file_transcription/'.format(settings.app_root) \
                                               + folder_files_df['file_id'].astype(str) + '/" title="Details of File ' + folder_files_df['file_name'].astype(str) + '">' \
                                               + folder_files_df['file_name'].astype(str) \
                                               + '</a> '
                else:
                    folder_files_df['file_name'] = '<a href="{}/file/'.format(settings.app_root) \
                                               + folder_files_df['file_id'].astype(str) + '/" title="Details of File ' + folder_files_df['file_name'].astype(str) + '">' \
                                               + folder_files_df['file_name'].astype(str) \
                                               + '</a> '
                folder_files_df = folder_files_df.drop(['file_id'], axis=1)
                folder_files_df = folder_files_df.drop(['preview_image'], axis=1)

                if transcription == 1:
                    folder_stats1 = run_query(("SELECT coalesce(f.no_files, 0) as no_files "
                                                    " FROM transcription_folders f WHERE folder_transcription_id = %(folder_id)s"),
                                                {'folder_id': folder_id})
                    folder_stats2 = run_query(("SELECT count(DISTINCT c.file_transcription_id) as no_errors "
                                                    " FROM transcription_files_checks c WHERE file_transcription_id IN (SELECT file_transcription_id from transcription_files WHERE"
                                                    "   folder_transcription_id = %(folder_id)s) AND check_results = 1"),
                                                {'folder_id': folder_id})
                else:
                    folder_stats1 = run_query(("SELECT coalesce(f.no_files, 0) as no_files "
                                                " FROM folders f WHERE folder_id = %(folder_id)s"),
                                               {'folder_id': folder_id})
                    folder_stats2 = run_query(("SELECT count(DISTINCT c.file_id) as no_errors "
                                                " FROM files_checks c WHERE file_id IN (SELECT file_id from files WHERE"
                                                "   folder_id = %(folder_id)s) AND check_results = 1"),
                                               {'folder_id': folder_id})
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
            for f in files_df:
                if transcription == 1:
                    preview_img_path = "image_previews/{}/{}/{}.jpg".format(f['folder_id'], "160", f['file_id'])
                else:
                    preview_img_path = "image_previews/folder{}/{}/{}.jpg".format(f['folder_id'], "160", f['file_id'])
                if os.path.isfile("static/{}".format(preview_img_path)):
                    f['preview_img_path'] = preview_img_path
                else:
                    f['preview_img_path'] = "na_{}.png".format("160")
        elif tab == "postprod":
            project_postprocessing_temp = run_query(
                ("SELECT settings_value as file_check FROM projects_settings "
                " WHERE project_setting = 'project_postprocessing' and project_id = %(project_id)s ORDER BY table_id"),
                {'project_id': project_info['project_id']})
            project_postprocessing = []
            if project_postprocessing_temp is not None:
                for fcheck in project_postprocessing_temp:
                    project_postprocessing.append(fcheck['file_check'])
            filechecks_list = []

            page_no = "Post-Processing Steps"
            folder_files_df = pd.DataFrame()
            post_processing_df = pd.DataFrame(run_query(("SELECT file_id, file_name FROM files "
                                                  " WHERE folder_id = %(folder_id)s ORDER BY file_name"),
                                                 {'folder_id': folder_id}))
            logger.info("project_postprocessing {}".format(project_postprocessing))
            post_processing_df['file_name'] = '<a href="{}/file/'.format(settings.app_root) \
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
                                                             {'file_check': fcheck, 'folder_id': folder_id}))
                    logger.info("list_files.size: {}".format(list_files.shape[0]))
                    if list_files.shape[0] > 0:
                        post_processing_df = post_processing_df.merge(list_files, how='outer', on='file_id')
                post_processing_df = post_processing_df.drop(['file_id'], axis=1)
            else:
                post_processing_df = pd.DataFrame()
        if transcription == 1:
            folder_badges = run_query("SELECT f.folder_transcription_id as folder_id, b.badge_type, b.badge_css, b.badge_text FROM folders_badges b, transcription_folders f WHERE b.folder_uid = f.folder_transcription_id and f.folder_transcription_id = %(folder_id)s and b.badge_type != 'no_files'", {'folder_id': folder_id})
        else:
            folder_badges = run_query("SELECT b.folder_id, b.badge_type, b.badge_css, b.badge_text FROM folders_badges b, folders f WHERE b.folder_id = f.folder_id and f.folder_id = %(folder_id)s and b.badge_type != 'no_files'", {'folder_id': folder_id})
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
        folder_badges = None
    if current_user.is_authenticated:
        user_name = current_user.name
        is_admin = user_perms('', user_type='admin')
    else:
        user_name = ""
        is_admin = False
    folder_links = run_query("SELECT * FROM folders_links WHERE folder_id = %(folder_id)s",
                                  {'folder_id': folder_id})
    logger.info("folder_links: {}".format(folder_links))

    # Reports
    reports = run_query("SELECT * FROM data_reports WHERE project_id = %(project_id)s ORDER BY report_id",
                             {'project_id': project_id})

    if len(reports) > 0:
        proj_reports = True
    else:
        proj_reports = False

    if tab == "filechecks":
        if transcription == 1:
            qc_check = run_query("SELECT * FROM qc_files WHERE folder_uid = %(folder_id)s",
                            {'folder_id': folder_id})
        else:
            qc_check = run_query("SELECT * FROM qc_files WHERE folder_id = %(folder_id)s",
                            {'folder_id': folder_id})
        if len(qc_check) > 0:
            qc_check = True
            if transcription == 1:
                qc_details = pd.DataFrame(run_query(("SELECT f.file_transcription_id as file_id, f.file_name, q.qc_info, "
                                                 "      CASE "
                                                 "           WHEN q.file_qc = 0 THEN '<span class=\"badge bg-success\">Image OK</span>'"
                                                 "           WHEN q.file_qc = 1 THEN '<span class=\"badge bg-danger\">Critical Issue</span>'"
                                                 "           WHEN q.file_qc = 2 THEN '<span class=\"badge bg-warning\">Major Issue</span>'"
                                                 "           WHEN q.file_qc = 3 THEN '<span class=\"badge bg-warning\">Minor Issue</span>' END as file_qc "
                                                 "FROM qc_files q, transcription_files f WHERE q.folder_uid = %(folder_id)s AND q.file_uid = f.file_transcription_id "
                                                 "ORDER BY q.file_qc DESC"),
                                {'folder_id': folder_id}))
                qc_details['file_name'] = '<a href="{}/file_transcription/'.format(settings.app_root) \
                                                + qc_details['file_id'].astype(str) + '/" title="File Details" target="_blank">' \
                                                + qc_details['file_name'].astype(str) \
                                                + '</a>'
                qc_details = qc_details.drop(['file_id'], axis=1)
                qc_folder_info = run_query(("SELECT qc_info from qc_folders where folder_uid = %(folder_id)s"),
                                    {'folder_id': folder_id})
                qc_folder_info=qc_folder_info[0]['qc_info']
            else:
                qc_details = pd.DataFrame(run_query(("SELECT f.file_id, f.file_name, q.qc_info, "
                                                 "      CASE "
                                                 "           WHEN q.file_qc = 0 THEN '<span class=\"badge bg-success\">Image OK</span>'"
                                                 "           WHEN q.file_qc = 1 THEN '<span class=\"badge bg-danger\">Critical Issue</span>'"
                                                 "           WHEN q.file_qc = 2 THEN '<span class=\"badge bg-warning\">Major Issue</span>'"
                                                 "           WHEN q.file_qc = 3 THEN '<span class=\"badge bg-warning\">Minor Issue</span>' END as file_qc "
                                                 "FROM qc_files q, files f WHERE q.folder_id = %(folder_id)s AND q.file_id = f.file_id "
                                                 "ORDER BY q.file_qc DESC"),
                                {'folder_id': folder_id}))
                qc_details['file_name'] = '<a href="{}/file/'.format(settings.app_root) \
                                                + qc_details['file_id'].astype(str) + '/" title="File Details" target="_blank">' \
                                                + qc_details['file_name'].astype(str) \
                                                + '</a>'
                qc_details = qc_details.drop(['file_id'], axis=1)
                qc_folder_info = run_query(("SELECT qc_info from qc_folders where folder_id = %(folder_id)s"),
                                    {'folder_id': folder_id})
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
                              {'project_id': project_id})

    i = 0
    project_disk = "NA"
    for disk in project_disks:
        if i > 0:
            project_disk = "{} / {}: {}".format(project_disk, disk['filetype'], disk['filesize'])
        else:
            project_disk = "{}: {}".format(disk['filetype'], disk['filesize'])
        i += 1

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
    
    recent_images = []

    return render_template('dashboard.html',
                           fol_last_update=fol_last_update,
                           page_no=page_no,
                           project_id=project_id,
                           project_info=project_info,
                           project_alias=project_alias,
                           project_stats=project_stats,
                           project_folders=project_folders,
                           project_folders_indams=project_folders_indams,
                           files_df=files_df,
                           folder_id=folder_id,
                           folder_name=folder_name,
                           recent_images=recent_images,
                           tables=[folder_files_df.to_html(table_id='files_table',
                                                       index=False,
                                                       border=0,
                                                       escape=False,
                                                       classes=["display", "compact", "table-striped", "w-100"])],
                           titles=[''],
                           username=user_name, project_admin=project_admin,
                           is_admin=is_admin, tab=tab, page=page, files_count=files_count,
                           pagination_html=pagination_html, folder_stats=folder_stats,
                           post_processing=[post_processing_df.to_html(table_id='post_processing_table',
                                                       index=False,
                                                       border=0,
                                                       escape=False,
                                                       classes=["display", "compact", "table-striped", "w-100"])],
                           postproc_data=(project_info['project_postprocessing'] != ""),
                           post_processing_rows=post_processing_df.shape[0],
                           folder_links=folder_links,
                           project_folders_badges=project_folders_badges,
                           form=form, proj_reports=proj_reports,
                           reports=reports, site_env=site_env, site_net=site_net,
                           site_ver=site_ver, kiosk=kiosk, user_address=user_address,
                           qc_check=qc_check, qc_folder_info=qc_folder_info,
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
                           files_table_sort=files_table_sort,
                           folder_badges=folder_badges,
                           no_cols=no_cols,
                           transcription=transcription
                           )


@cache.memoize()
@app.route('/dashboard/<project_alias>/', methods=['GET', 'POST'], provide_automatic_options=False)
def dashboard(project_alias=None, folder_id=None):
    """Dashboard for a project"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
    folder_id = request.values.get("folder_id")

    if folder_id != None:
        return redirect(url_for('dashboard_f', project_alias=project_alias, folder_id=folder_id))

    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Declare the login form
    form = LoginForm(request.form)

    project_stats = {}

    # Check if project exists
    if project_alias_exists(project_alias) is False:
        # Check if project alias in list of redirects
        try:
            if project_alias_exists(settings.proj_redirect[project_alias]):
                logger.info("project_alias_redirect: {}".format(project_alias))
                return redirect(url_for('dashboard', project_alias=settings.proj_redirect[project_alias]))
        except KeyError:
            error_msg = "Project was not found."
            return render_template('error.html', error_msg=error_msg,
                                project_alias=project_alias, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404

    project_id = project_alias_exists(project_alias)

    logger.info("project_id: {}".format(project_id))
    logger.info("project_alias: {}".format(project_alias))
    if current_user.is_authenticated:
        username = current_user.name
        project_admin = run_query(("SELECT count(*) as no_results FROM users u, qc_projects p "
                                        " WHERE u.username = %(username)s "
                                        " AND p.project_id = %(project_id)s AND u.user_id = p.user_id"),
                                       {'username': username, 'project_id': project_id})[0]
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
                             "   FROM projects WHERE project_id = %(project_id)s",
                                  {'project_id': project_id})[0]

    project_manager_link = project_info['project_manager']
    if project_info['project_manager'] == "Jeanine Nault":
        project_manager_link = "<a href=\"https://dpo.si.edu/jeanine-nault\" class=\"bg-white\" title=\"Link to Jeanine Nault's staff page\">Jeanine Nault</a>"
    elif project_info['project_manager'] == "Nathan Ian Anderson":
        project_manager_link = "<a href=\"https://dpo.si.edu/nathan-ian-anderson\" class=\"bg-white\" title=\"Link to Nathan Ian Anderson's staff page\">Nathan Ian Anderson</a>"
    elif project_info['project_manager'] == "Erin M. Mazzei":
        project_manager_link = "<a href=\"https://dpo.si.edu/erin-mazzei\" class=\"bg-white\" title=\"Link to Erin M. Mazzei's staff page\">Erin M. Mazzei</a>"
    elif project_info['project_manager'] == "Laura Whitfield":
        project_manager_link = "<a href=\"https://dpo.si.edu/laura-whitfield\" class=\"bg-white\" title=\"Link to Laura Whitfield's staff page\">Erin M. Mazzei</a>"

    projects_links = run_query("SELECT * FROM projects_links WHERE project_id = %(project_id)s ORDER BY table_id",
                               {'project_id': project_info['project_id']})

    project_statistics = run_query(("SELECT * FROM projects_stats WHERE project_id = %(project_id)s"),
                                   {'project_id': project_id})[0]

    project_stats['total'] = format(int(project_statistics['images_taken']), ',d')
    project_stats['ok'] = format(int(project_statistics['project_ok']), ',d')
    project_stats['errors'] = format(int(project_statistics['project_err']), ',d')
    project_stats['objects'] = format(int(project_statistics['objects_digitized']), ',d')

    project_stats_other = run_query(("SELECT other_icon, other_name, COALESCE(other_stat, 0) as other_stat FROM projects_stats WHERE project_id = %(project_id)s"), {'project_id': project_id})[0]
    project_stats_other['other_stat'] = format(int(project_stats_other['other_stat']), ',d')
    
    if project_info['transcription'] == 1:
        transcription = 1
        no_fold = run_query(("SELECT count(folder) as folders FROM transcription_folders f WHERE f.project_id = %(project_id)s"),
                                     {'project_id': project_id})[0]
        project_stats['no_folders'] = format(int(no_fold['folders']), ',d')
        project_folders = run_query(("SELECT f.folder as project_folder, f.folder_transcription_id as folder_id, coalesce(b1.badge_text, 0) as no_files, "
                                        "f.file_errors, f.status, f.error_info, f.delivered_to_dams, "
                                        " COALESCE(CASE WHEN qcf.qc_status = 0 THEN 'QC Passed' "
                                        "              WHEN qcf.qc_status = 1 THEN 'QC Failed' "
                                        "              WHEN qcf.qc_status = 9 THEN 'QC Pending' END,"
                                        "          'QC Pending') as qc_status, "
                                        " f.previews "
                                        "FROM transcription_folders f "
                                        " LEFT JOIN qc_folders qcf ON (f.folder_transcription_id = qcf.folder_uid) "
                                        " LEFT JOIN folders_badges b1 ON (f.folder_transcription_id = b1.folder_uid AND b1.badge_type = 'no_files') "
                                        "WHERE f.project_id = %(project_id)s and f.delivered_to_dams != 0 ORDER BY "
                                        "f.date DESC, f.folder DESC"),
                                        {'project_id': project_id})
        project_folders_indams = run_query(("SELECT f.folder as project_folder, f.folder_transcription_id as folder_id, coalesce(b1.badge_text, 0) as no_files "
                                        "FROM transcription_folders f "
                                        "     LEFT JOIN folders_badges b1 ON (f.folder_transcription_id = b1.folder_uid AND b1.badge_type = 'no_files') "
                                        " WHERE f.project_id = %(project_id)s and f.delivered_to_dams = 0 "
                                        " ORDER BY f.folder ASC"),
                                        {'project_id': project_id})
    else:
        transcription = 0
        no_fold = run_query(("SELECT count(project_folder) as folders FROM folders f WHERE f.project_id = %(project_id)s"),
                                     {'project_id': project_id})[0]
        project_stats['no_folders'] = format(int(no_fold['folders']), ',d')
        project_folders = run_query(("SELECT f.project_folder, f.folder_id, coalesce(b1.badge_text, 0) as no_files, "
                                        "f.file_errors, f.status, f.error_info, f.delivered_to_dams, "
                                        " COALESCE(CASE WHEN qcf.qc_status = 0 THEN 'QC Passed' "
                                        "              WHEN qcf.qc_status = 1 THEN 'QC Failed' "
                                        "              WHEN qcf.qc_status = 9 THEN 'QC Pending' END,"
                                        "          'QC Pending') as qc_status, "
                                        " f.previews "
                                        "FROM folders f "
                                        " LEFT JOIN qc_folders qcf ON (f.folder_id = qcf.folder_id) "
                                        " LEFT JOIN folders_badges b1 ON (f.folder_id = b1.folder_id AND b1.badge_type = 'no_files') "
                                        "WHERE f.project_id = %(project_id)s and f.delivered_to_dams != 0 ORDER BY "
                                        "f.date DESC, f.project_folder DESC"),
                                        {'project_id': project_id})
        project_folders_indams = run_query(("SELECT f.project_folder, f.folder_id, coalesce(b1.badge_text, 0) as no_files "
                                        "FROM folders f "
                                        "     LEFT JOIN folders_badges b1 ON (f.folder_id = b1.folder_id AND b1.badge_type = 'no_files') "
                                        " WHERE f.project_id = %(project_id)s and f.delivered_to_dams = 0 "
                                        " ORDER BY f.project_folder ASC"),
                                        {'project_id': project_id})

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
    folder_stats = {'no_files': 0, 'no_errors': 0}
    post_processing_df = pd.DataFrame()
    if transcription == 1:
        project_folders_badges = run_query(
            "SELECT b.folder_uid as folder_id, b.badge_type, b.badge_css, b.badge_text "
            " FROM folders_badges b, transcription_folders f WHERE b.folder_uid = f.folder_transcription_id and f.project_id = %(project_id)s and f.delivered_to_dams != 0 and b.badge_type != 'no_files'",
            {'project_id': project_id})
    else:
        project_folders_badges = run_query(
            "SELECT b.folder_id, b.badge_type, b.badge_css, b.badge_text "
            " FROM folders_badges b, folders f WHERE b.folder_id = f.folder_id and f.project_id = %(project_id)s and f.delivered_to_dams != 0 and b.badge_type != 'no_files'",
            {'project_id': project_id})
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
                        " WHERE project_id = %(project_id)s ORDER BY report_id",
                             {'project_id': project_id})

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
                              {'project_id': project_id})

    project_disk = "NA"
    i = 0
    for disk in project_disks:
        if i > 0:
            project_disk = "{} / {}: {}".format(project_disk, disk['filetype'], disk['filesize'])
        else:
            project_disk = "{}: {}".format(disk['filetype'], disk['filesize'])
        i += 1

    # Recent images
    if transcription == 1:
        recent_images = []
    else:
        preview_filter = project_info['preview_filter']
        if preview_filter is None:
            if transcription == 1:
                recent_images_pool = run_query("SELECT file_transcription_id as file_id, CONCAT('image_previews/', folder_transcription_id, '/160/', file_transcription_id, '.jpg') as preview FROM transcription_files WHERE folder_transcription_id IN (SELECT folder_transcription_id FROM transcription_folders WHERE project_id = %(project_id)s and status = 0 and previews = 0) ORDER BY file_transcription_id DESC limit 100", {'project_id': project_info['project_id']})
            else:
                recent_images_pool = run_query("SELECT file_id, CONCAT('image_previews/folder', folder_id, '/160/', file_id, '.jpg') as preview FROM files WHERE folder_id IN (SELECT folder_id FROM folders WHERE project_id = %(project_id)s and status = 0 and previews = 0) ORDER BY file_id DESC limit 100", {'project_id': project_info['project_id']})
        else:
            if transcription == 1:
                recent_images_pool = run_query("SELECT file_transcription_id as file_id, CONCAT('image_previews/', folder_transcription_id, '/160/', file_transcription_id, '.jpg') as preview FROM transcription_files WHERE {} folder_transcription_id IN (SELECT folder_transcription_id FROM transcription_folders WHERE project_id = %(project_id)s and status = 0 and previews = 0) ORDER BY file_transcription_id DESC limit 100".format(preview_filter), {'project_id': project_info['project_id']})
            else:
                recent_images_pool = run_query("SELECT file_id, CONCAT('image_previews/folder', folder_id, '/160/', file_id, '.jpg') as preview FROM files WHERE {} folder_id IN (SELECT folder_id FROM folders WHERE project_id = %(project_id)s and status = 0 and previews = 0) ORDER BY file_id DESC limit 100".format(preview_filter), {'project_id': project_info['project_id']})
        recent_images = []
        for img in recent_images_pool:
            if os.path.exists("static/{}".format(img['preview'])):
                recent_images.append(img)
        random.shuffle(recent_images)

    return render_template('dashboard.html',
                           page_no="",
                           project_id=project_id, project_info=project_info,
                           project_alias=project_alias, project_stats=project_stats,
                           project_folders=project_folders,
                           project_folders_indams=project_folders_indams,
                           files_df=files_df, folder_id=folder_id, folder_name=folder_name,
                           folder_qc=folder_qc,
                           recent_images=recent_images[:20],
                           tables=[folder_files_df.to_html(table_id='files_table',
                                                           index=False,
                                                           border=0,
                                                           escape=False,
                                                           classes=["display", "compact", "table-striped"])],
                           titles=[''],
                           username=user_name, project_admin=project_admin,
                           is_admin=is_admin, tab=None, page=1,
                           files_count=files_count, pagination_html=pagination_html,
                           folder_stats=folder_stats,
                           post_processing=[post_processing_df.to_html(table_id='post_processing_table',
                                                                       index=False,
                                                                       border=0,
                                                                       escape=False,
                                                                       classes=["display", "compact",
                                                                                "table-striped"])],
                           postproc_data=(project_info['project_postprocessing'] != ""),
                           folder_links=folder_links, transcription=transcription,
                           project_folders_badges=project_folders_badges,
                           form=form, proj_reports=proj_reports, reports=reports,
                           site_env=site_env, site_net=site_net, site_ver=site_ver,
                           kiosk=kiosk, user_address=user_address, project_disk=project_disk,
                           projects_links=projects_links, project_manager_link=project_manager_link,
                           analytics_code=settings.analytics_code, project_stats_other=project_stats_other, no_cols=None)


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

    # Check if project exists
    if project_alias_exists(project_alias) is False:
        error_msg = "Project was not found."
        return render_template('error.html', error_msg=error_msg,
                                project_alias=project_alias, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404

    project_id_check = run_query("SELECT project_id FROM projects WHERE project_alias = %(project_alias)s",
                                      {'project_alias': project_alias})
    if len(project_id_check) == 0:
        error_msg = "Project was not found."
        return render_template('error.html', error_msg=error_msg,
                               project_alias=project_alias, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404
    else:
        project_id = project_id_check[0]['project_id']

    project_info = run_query("SELECT * FROM projects WHERE project_id = %(project_id)s", {'project_id': project_id})[0]

    proj_stats_steps = run_query("SELECT * FROM projects_detail_statistics_steps WHERE project_id = %(proj_id)s and (stat_type='column' or stat_type='boxplot' or stat_type='area') and active=1 ORDER BY step_order", {'proj_id': project_info['proj_id']})

    proj_stats_vals1 = run_query("SELECT s.step_info, s.step_notes, step_units, s.css, s.round_val, DATE_FORMAT(s.step_updated_on, \"%Y-%m-%d %H:%i:%s\") as step_updated_on, e.step_value FROM projects_detail_statistics_steps s, projects_detail_statistics e WHERE s.project_id = %(proj_id)s and s.stat_type='stat' and e.step_id = s.step_id and s.active=1 ORDER BY s.step_order LIMIT 3", {'proj_id': project_info['proj_id']})

    proj_stats_vals2 = run_query("SELECT s.step_info, s.step_notes, s.step_units, s.css, s.round_val, DATE_FORMAT(s.step_updated_on, \"%Y-%m-%d %H:%i:%s\") as step_updated_on, e.step_value FROM projects_detail_statistics_steps s, projects_detail_statistics e WHERE s.project_id = %(proj_id)s and s.stat_type='stat' and e.step_id = s.step_id and s.active=1 ORDER BY s.step_order LIMIT 3, 3", {'proj_id': project_info['proj_id']})

    # Stats
    project_stats = {}
    project_statistics = run_query(("SELECT * FROM projects_stats WHERE project_id = %(project_id)s"),
                                    {'project_id': project_id})[0]
    project_stats['total'] = format(int(project_statistics['images_taken']), ',d')
    project_stats['ok'] = format(int(project_statistics['project_ok']), ',d')
    project_stats['errors'] = format(int(project_statistics['project_err']), ',d')
    project_stats['objects'] = format(int(project_statistics['objects_digitized']), ',d')

    project_stats_other = run_query(("SELECT other_icon, other_name, COALESCE(other_stat, 0) as other_stat FROM projects_stats WHERE project_id = %(project_id)s"), {'project_id': project_id})[0]
    project_stats_other['other_stat'] = format(int(project_stats_other['other_stat']), ',d')

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

    project_id_check = run_query("SELECT proj_id FROM projects WHERE proj_id = %(proj_id)s",
                                      {'proj_id': project_id})
    if len(project_id_check) == 0:
        error_msg = "Project was not found."
        return render_template('error.html', error_msg=error_msg,
                               project_alias=None, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404

    project_info = run_query("SELECT * FROM projects WHERE proj_id = %(proj_id)s", {'proj_id': project_id})[0]

    proj_stats = run_query("SELECT e.step_info, e.step_notes, e.step_units, s.* FROM projects_detail_statistics_steps e RIGHT JOIN projects_detail_statistics s ON (e.step_id = s.step_id) WHERE e.step_id = %(step_id)s", {'step_id': step_id})

    csv_data = "data_type,info,units,date,value\n"
    for data_row in proj_stats:
        csv_data += f"{data_row['step_info']}, {data_row['step_notes']}, {data_row['step_units']}, {data_row['date']}, {data_row['step_value']}\n"

    current_time = strftime("%Y%m%d_%H%M%S", localtime())

    # Create a direct download response with the CSV data and appropriate headers
    response = Response(csv_data, content_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename={}_stats_{}.csv".format(project_info['project_alias'], current_time)
    return response


@cache.memoize()
@app.route('/dashboard/<project_alias>/statistics2/', methods=['POST', 'GET'], provide_automatic_options=False)
def proj_statistics_plotnine(project_alias=None):
    """Figures with statistics for a project"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
    user_exists = False
    username = None

    # Declare the login form
    form = LoginForm(request.form)

    # Check if project exists
    if project_alias_exists(project_alias) is False:
        error_msg = "Project was not found."
        return render_template('error.html', error_msg=error_msg,
                                project_alias=project_alias, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404

    project_id_check = run_query("SELECT project_id FROM projects WHERE project_alias = %(project_alias)s",
                                      {'project_alias': project_alias})
    if len(project_id_check) == 0:
        error_msg = "Project was not found."
        return render_template('error.html', error_msg=error_msg,
                               project_alias=project_alias, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404
    else:
        project_id = project_id_check[0]['project_id']

    project_info = run_query("SELECT * FROM projects WHERE project_id = %(project_id)s", {'project_id': project_id})[0]

    daily_stats = run_query("SELECT DATE_FORMAT(f.file_timestamp, '%Y-%m-%d') as date, count(f.*) as no_files FROM files f, folders fol WHERE f.folder_id = fol.folder_id and fol.project_id = %(project_id)s GROUP BY date", {'project_id': project_info['proj_id']})

    proj_stats_vals1 = run_query("SELECT s.step_info, s.step_notes, step_units, s.css, s.round_val, DATE_FORMAT(s.step_updated_on, \"%Y-%m-%d %H:%i:%s\") as step_updated_on, e.step_value FROM projects_detail_statistics_steps s, projects_detail_statistics e WHERE s.project_id = %(proj_id)s and s.stat_type='stat' and e.step_id = s.step_id and s.active=1 ORDER BY s.step_order LIMIT 3", {'proj_id': project_info['proj_id']})

    proj_stats_vals2 = run_query("SELECT s.step_info, s.step_notes, s.step_units, s.css, s.round_val, DATE_FORMAT(s.step_updated_on, \"%Y-%m-%d %H:%i:%s\") as step_updated_on, e.step_value FROM projects_detail_statistics_steps s, projects_detail_statistics e WHERE s.project_id = %(proj_id)s and s.stat_type='stat' and e.step_id = s.step_id and s.active=1 ORDER BY s.step_order LIMIT 3, 3", {'proj_id': project_info['proj_id']})

    # Stats
    project_stats = {}
    project_statistics = run_query(("SELECT * FROM projects_stats WHERE project_id = %(project_id)s"),
                                    {'project_id': project_id})[0]
    project_stats['total'] = format(int(project_statistics['images_taken']), ',d')
    project_stats['ok'] = format(int(project_statistics['project_ok']), ',d')
    project_stats['errors'] = format(int(project_statistics['project_err']), ',d')
    project_stats['objects'] = format(int(project_statistics['objects_digitized']), ',d')

    project_stats_other = run_query(("SELECT other_icon, other_name, COALESCE(other_stat, 0) as other_stat FROM projects_stats WHERE project_id = %(project_id)s"), {'project_id': project_id})[0]
    project_stats_other['other_stat'] = format(int(project_stats_other['other_stat']), ',d')

    return render_template('statistics.html',
                           project_alias=project_alias,
                           project_info=project_info,
                           proj_stats_steps=proj_stats_steps,
                           proj_stats_vals1=proj_stats_vals1,
                           proj_stats_vals2=proj_stats_vals2,
                           project_stats=project_stats,
                           project_stats_other=project_stats_other)


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

    # Declare the login form
    form = LoginForm(request.form)

    # Get project info
    project = run_query("SELECT * FROM projects WHERE project_alias = %(project_alias)s ",
                             {'project_alias': project_alias})[0]
    project_id = project['project_id']
    transcription = project['transcription']
    
    username = current_user.name
    project_admin = run_query(("SELECT count(*) as no_results "
                                    "    FROM users u, qc_projects qp, projects p "
                                    "    WHERE u.username = %(username)s "
                                    "        AND p.project_alias = %(project_alias)s "
                                    "        AND qp.project_id = p.project_id "
                                    "        AND u.user_id = qp.user_id"),
                                   {'username': username, 'project_alias': project_alias})
    if project_admin is None:
        # Not allowed
        return redirect(url_for('home'))

    project_settings = run_query(("SELECT * FROM qc_settings "
                                 " WHERE project_id = %(project_id)s"),
                                {'project_id': project_id})

    if len(project_settings) == 0:
        query = ("INSERT INTO qc_settings (project_id, qc_level, qc_percent, "
                 " qc_threshold_critical, qc_threshold_major, qc_threshold_minor, "
                 " qc_normal_percent, qc_reduced_percent, qc_tightened_percent, updated_at) "
                 "  VALUES ("
                 "  %(project_id)s, 'Tightened', 40, 0, 1.5, 4, 10, 5, 40, "
                 "  CURRENT_TIME)")
        q = query_database_insert(query, {'project_id': project_id})
        project_settings = run_query(("SELECT * FROM qc_settings "
                                      " WHERE project_id = %(project_id)s"),
                                     {'project_id': project_id})

    project_settings = project_settings[0]

    project_qc_stats = {}
    if transcription == 1:
        project_qc_ok = run_query(("SELECT count(f.folder_transcription_id) as no_folders FROM transcription_folders f LEFT JOIN qc_folders q on (f.folder_transcription_id = q.folder_uid ) "
                            "WHERE f.project_id = %(project_id)s and f.status = 0 and f.previews = 0 and f.file_errors = 0 and q.qc_status = 0"),
                            {'project_id': project_id})[0]
        project_qc_failed = run_query((
                                    "SELECT count(f.folder_transcription_id) as no_folders FROM transcription_folders f LEFT JOIN qc_folders q on (f.folder_transcription_id = q.folder_uid ) "
                                    "WHERE f.project_id = %(project_id)s and f.status = 0 and f.previews = 0 and f.file_errors = 0 and q.qc_status = 1"),
                                {'project_id': project_id})[0]
        project_qc_count = run_query((
            "SELECT count(f.folder_transcription_id) as no_folders FROM transcription_folders f WHERE f.project_id = %(project_id)s and f.status = 0 and f.file_errors = 0 and f.previews = 0"),
            {'project_id': project_id})[0]
    else:
        project_qc_ok = run_query(("SELECT count(f.folder_id) as no_folders FROM folders f LEFT JOIN qc_folders q on (f.folder_id = q.folder_id ) "
                            "WHERE f.project_id = %(project_id)s and f.status = 0 and f.previews = 0 and f.file_errors = 0 and q.qc_status = 0"),
                            {'project_id': project_id})[0]
        project_qc_failed = run_query((
                                    "SELECT count(f.folder_id) as no_folders FROM folders f LEFT JOIN qc_folders q on (f.folder_id = q.folder_id ) "
                                    "WHERE f.project_id = %(project_id)s and f.status = 0 and f.previews = 0 and f.file_errors = 0 and q.qc_status = 1"),
                                {'project_id': project_id})[0]
        project_qc_count = run_query((
            "SELECT count(f.folder_id) as no_folders FROM folders f WHERE f.project_id = %(project_id)s and f.status = 0 and f.file_errors = 0 and f.previews = 0"),
            {'project_id': project_id})[0]


    project_qc_stats['total'] = project_qc_count['no_folders']
    project_qc_stats['ok'] = project_qc_ok['no_folders']
    project_qc_stats['failed'] = project_qc_failed['no_folders']

    project_qc_stats['pending'] = project_qc_stats['total'] - (project_qc_stats['ok'] + project_qc_stats['failed'])

    if transcription == 1:
        folder_qc_done = run_query(("WITH pfolders AS (SELECT folder_transcription_id as folder_id from transcription_folders WHERE project_id = %(project_id)s),"
                                " errors AS "
                                "         (SELECT folder_uid as folder_id, count(file_id) as no_files "
                                "             FROM qc_files "
                                "             WHERE folder_uid IN (SELECT folder_id from pfolders) "
                                "                 AND file_qc > 0 AND file_qc != 9 "
                                "               GROUP BY folder_uid),"
                                "passed AS "
                                "         (SELECT folder_uid as folder_id, count(file_id) as no_files "
                                "             FROM qc_files "
                                "             WHERE folder_uid IN (SELECT folder_id from pfolders) "
                                "                 AND file_qc = 0 "
                                "               GROUP BY folder_uid),"
                                "total AS (SELECT folder_uid as folder_id, count(file_id) as no_files FROM qc_files "
                                "             WHERE folder_uid IN (SELECT folder_id from pfolders)"
                                "                GROUP BY folder_uid), "
                                " files_total AS (SELECT folder_transcription_id as folder_id, count(file_transcription_id) as no_files FROM transcription_files "
                                "             WHERE folder_transcription_id IN (SELECT folder_id from pfolders)"
                                "                GROUP BY folder_transcription_id) "
                                " SELECT f.folder_transcription_id as folder_id, f.folder, f.delivered_to_dams, "
                                "       ft.no_files, f.file_errors, f.status, f.error_info, q.qc_level, "
                                "   CASE WHEN q.qc_status = 0 THEN 'QC Passed' "
                                "      WHEN q.qc_status = 1 THEN 'QC Failed' "
                                "      ELSE 'QC Pending' END AS qc_status, "
                                "      q.qc_ip, u.username AS qc_by, "
                                "      date_format(q.updated_at, '%Y-%m-%d') AS updated_at, "
                                "       COALESCE(errors.no_files, 0) as qc_stats_no_errors, "
                                "       COALESCE(passed.no_files, 0) as qc_stats_no_passed,"
                                "       COALESCE(total.no_files, 0) as qc_stats_no_files "
                                " FROM transcription_folders f LEFT JOIN qc_folders q ON "
                                "       (f.folder_transcription_id = q.folder_uid)"
                                "       LEFT JOIN users u ON "
                                "           (q.qc_by = u.user_id)"
                                "       LEFT JOIN errors ON "
                                "           (f.folder_transcription_id = errors.folder_id)"
                                "       LEFT JOIN passed ON "
                                "           (f.folder_transcription_id = passed.folder_id)"
                                "       LEFT JOIN total ON "
                                "           (f.folder_transcription_id = total.folder_id)"
                                "       LEFT JOIN files_total ft ON "
                                "           (f.folder_transcription_id = ft.folder_id), "
                                "   projects p "
                                " WHERE f.project_id = p.project_id "
                                "   AND p.project_id = %(project_id)s "
                                "   AND q.qc_status != 9 "
                                "  ORDER BY f.date DESC, f.folder DESC"),
                               {'project_id': project_id})
        folder_qc_info = run_query(("WITH pfolders AS (SELECT folder_transcription_id as folder_id from transcription_folders WHERE project_id = %(project_id)s),"
                                     " errors AS "
                                     "         (SELECT folder_uid as folder_id, count(file_id) as no_files "
                                     "             FROM qc_files "
                                     "             WHERE folder_uid IN (SELECT folder_id from pfolders) "
                                     "                 AND file_qc > 0 AND file_qc != 9 "
                                     "               GROUP BY folder_uid),"
                                     "passed AS "
                                     "         (SELECT folder_uid as folder_id, count(file_id) as no_files "
                                     "             FROM qc_files "
                                     "             WHERE folder_uid IN (SELECT folder_id from pfolders) "
                                     "                 AND file_qc = 0 "
                                     "               GROUP BY folder_uid),"
                                     "total AS (SELECT folder_uid as folder_id, count(file_uid) as no_files FROM qc_files "
                                     "             WHERE folder_uid IN (SELECT folder_id from pfolders)"
                                     "                GROUP BY folder_uid), "
                                     " files_total AS (SELECT folder_transcription_id as folder_id, count(file_transcription_id) as no_files FROM transcription_files "
                                     "             WHERE folder_transcription_id IN (SELECT folder_id from pfolders)"
                                     "                GROUP BY folder_transcription_id), "
                                     " qc as (SELECT f.folder_transcription_id as folder_id, f.folder, f.delivered_to_dams, "
                                     "       ft.no_files, f.file_errors, f.status, f.date, f.error_info, "
                                     "   CASE WHEN q.qc_status = 0 THEN 'QC Passed' "
                                     "      WHEN q.qc_status = 1 THEN 'QC Failed' "
                                     "      ELSE 'QC Pending' END AS qc_status, "
                                     "      q.qc_ip, u.username AS qc_by, "
                                     "      date_format(q.updated_at, '%Y-%m-%d') AS updated_at, "
                                     "       COALESCE(errors.no_files, 0) as qc_stats_no_errors, "
                                     "       COALESCE(passed.no_files, 0) as qc_stats_no_passed,"
                                     "       COALESCE(total.no_files, 0) as qc_stats_no_files "
                                     " FROM transcription_folders f LEFT JOIN qc_folders q ON "
                                     "       (f.folder_transcription_id = q.folder_uid)"
                                     "       LEFT JOIN users u ON "
                                     "           (q.qc_by = u.user_id)"
                                     "       LEFT JOIN errors ON "
                                     "           (f.folder_transcription_id = errors.folder_id)"
                                     "       LEFT JOIN passed ON "
                                     "           (f.folder_transcription_id = passed.folder_id)"
                                     "       LEFT JOIN total ON "
                                     "           (f.folder_transcription_id = total.folder_id)"
                                     "       LEFT JOIN files_total ft ON "
                                     "           (f.folder_transcription_id = ft.folder_id), "
                                     "   projects p "
                                     " WHERE f.project_id = p.project_id AND f.file_errors = 0 AND f.status = 0 AND f.previews = 0 "
                                     "   AND p.project_id = %(project_id)s) "
                                     " SELECT *, folder as project_folder FROM qc WHERE qc_status = 'QC Pending' and qc_by is null "
                                     "  and no_files > 0 "
                                     "  and folder_id not in (SELECT folder_uid from folders_badges where badge_type = 'folder_error' AND folder_uid IS NOT NULL) "
                                     "  and folder_id not in (SELECT folder_uid from folders_badges where badge_type = 'verification' AND folder_uid IS NOT NULL) "
                                     "  ORDER BY date ASC, folder ASC LIMIT 10"),
                                    {'project_id': project_id})
        folder_qc_pending = run_query(("WITH pfolders AS (SELECT folder_transcription_id as folder_id from transcription_folders WHERE project_id = %(project_id)s),"
                                     " errors AS "
                                     "         (SELECT folder_uid as folder_id, count(file_id) as no_files "
                                     "             FROM qc_files "
                                     "             WHERE folder_uid IN (SELECT folder_id from pfolders) "
                                     "                 AND file_qc > 0 AND file_qc != 9 "
                                     "               GROUP BY folder_uid),"
                                     "passed AS "
                                     "         (SELECT folder_uid as folder_id, count(file_id) as no_files "
                                     "             FROM qc_files "
                                     "             WHERE folder_uid IN (SELECT folder_id from pfolders) "
                                     "                 AND file_qc = 0 "
                                     "               GROUP BY folder_uid),"
                                     "total AS (SELECT folder_uid as folder_id, count(file_id) as no_files FROM qc_files "
                                     "             WHERE folder_uid IN (SELECT folder_id from pfolders)"
                                     "                GROUP BY folder_uid), "
                                     " files_total AS (SELECT folder_transcription_id as folder_id, count(file_transcription_id) as no_files FROM transcription_files "
                                     "             WHERE folder_transcription_id IN (SELECT folder_id from pfolders)"
                                     "                GROUP BY folder_transcription_id), "
                                     " qc as (SELECT f.folder_transcription_id as folder_id, f.folder, f.delivered_to_dams, "
                                     "       ft.no_files, f.file_errors, f.status, f.date, f.error_info, "
                                     "   CASE WHEN q.qc_status = 0 THEN 'QC Passed' "
                                     "      WHEN q.qc_status = 1 THEN 'QC Failed' "
                                     "      ELSE 'QC Pending' END AS qc_status, "
                                     "      q.qc_ip, u.username AS qc_by, "
                                     "      date_format(q.updated_at, '%Y-%m-%d') AS updated_at, "
                                     "       COALESCE(errors.no_files, 0) as qc_stats_no_errors, "
                                     "       COALESCE(passed.no_files, 0) as qc_stats_no_passed,"
                                     "       COALESCE(total.no_files, 0) as qc_stats_no_files "
                                     " FROM transcription_folders f LEFT JOIN qc_folders q ON "
                                     "       (f.folder_transcription_id = q.folder_uid)"
                                     "       LEFT JOIN users u ON "
                                     "           (q.qc_by = u.user_id)"
                                     "       LEFT JOIN errors ON "
                                     "           (f.folder_transcription_id = errors.folder_id)"
                                     "       LEFT JOIN passed ON "
                                     "           (f.folder_transcription_id = passed.folder_id)"
                                     "       LEFT JOIN total ON "
                                     "           (f.folder_transcription_id = total.folder_id)"
                                     "       LEFT JOIN files_total ft ON "
                                     "           (f.folder_transcription_id = ft.folder_id), "
                                     "   projects p "
                                     " WHERE f.project_id = p.project_id AND f.file_errors = 0 AND f.previews = 0 "
                                     "   AND p.project_id = %(project_id)s) "
                                     " SELECT * FROM qc WHERE qc_status = 'QC Pending' and qc_by is not null "
                                     "  ORDER BY date ASC, folder ASC"),
                                    {'project_id': project_id})
        return render_template('qc_transcription.html', username=username,
                            project_settings=project_settings,
                            folder_qc_info=folder_qc_info, folder_qc_pending=folder_qc_pending,
                            folder_qc_done=folder_qc_done[:100], folder_qc_done_len=len(folder_qc_done),
                            project=project, form=form, project_qc_stats=project_qc_stats,
                            site_env=site_env, site_net=site_net, site_ver=site_ver,
                            analytics_code=settings.analytics_code)

    else:
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
                               {'project_id': project_id})

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
                                     " WHERE f.project_id = p.project_id AND f.file_errors = 0 AND f.status = 0 AND f.previews = 0 "
                                     "   AND p.project_id = %(project_id)s) "
                                     " SELECT * FROM qc WHERE qc_status = 'QC Pending' and qc_by is null "
                                     "  and no_files > 0 "
                                     "  and folder_id not in (SELECT folder_id from folders_badges where badge_type = 'folder_error' AND folder_id IS NOT NULL) "
                                     "  and folder_id not in (SELECT folder_id from folders_badges where badge_type = 'verification' AND folder_id IS NOT NULL) "
                                     "  ORDER BY date ASC, project_folder ASC LIMIT 10"),
                                    {'project_id': project_id})
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
                                     " WHERE f.project_id = p.project_id AND f.file_errors = 0 AND f.previews = 0 "
                                     "   AND p.project_id = %(project_id)s) "
                                     " SELECT * FROM qc WHERE qc_status = 'QC Pending' and qc_by is not null "
                                     "  ORDER BY date ASC, project_folder ASC"),
                                    {'project_id': project_id})

        return render_template('qc.html', username=username,
                            project_settings=project_settings,
                            folder_qc_info=folder_qc_info, folder_qc_pending=folder_qc_pending,
                            folder_qc_done=folder_qc_done[:100], folder_qc_done_len=len(folder_qc_done),
                            project=project, form=form, project_qc_stats=project_qc_stats,
                            site_env=site_env, site_net=site_net, site_ver=site_ver,
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

    # Declare the login form
    form = LoginForm(request.form)

    try:
        folder_id = int(folder_id)
        transcription = 0
    except:
        try:
            # Allow for UUIDs
            folder_id = UUID(folder_id)
            folder_id = str(folder_id)
            transcription = 1
        except:
            raise InvalidUsage('invalid folder_id value', status_code=400)

    username = current_user.name
    if transcription == 1:
        project_admin = run_query(("SELECT count(*) as no_results FROM users u, qc_projects p, transcription_folders f "
                                    "    WHERE u.username = %(username)s "
                                    "        AND p.project_id = f.project_id "
                                    "        AND f.folder_transcription_id = %(folder_id)s "
                                    "        AND u.user_id = p.user_id"),
                                   {'username': username, 'folder_id': folder_id})[0]
    else:
        project_admin = run_query(("SELECT count(*) as no_results FROM users u, qc_projects p, folders f "
                                    "    WHERE u.username = %(username)s "
                                    "        AND p.project_id = f.project_id "
                                    "        AND f.folder_id = %(folder_id)s "
                                    "        AND u.user_id = p.user_id"),
                                   {'username': username, 'folder_id': folder_id})[0]
    if project_admin['no_results'] == 0:
        # Not allowed
        return redirect(url_for('home'))
    file_id_q = request.values.get('file_id')
    msg = ""
    # check if folder is owned, assigned otherwise
    if transcription == 1:
        folder_owner = run_query(("SELECT f.*, u.username from qc_folders f, users u "
                                        "    WHERE u.user_id = f.qc_by "
                                        "        AND f.folder_uid = %(folder_id)s"),
                                    {'folder_id': folder_id})

        if len(folder_owner) == 1:
            if folder_owner[0]['username'] != username:
                # Not allowed
                project_alias = run_query(("SELECT p.project_alias from transcription_folders f, projects p "
                                        "    WHERE f.project_id = p.project_id "
                                        "        AND f.folder_transcription_id = %(folder_id)s"),
                                    {'folder_id': folder_id})
                return redirect(url_for('qc', project_alias=project_alias[0]['project_alias']))
        else:
            # Assign user
            q = query_database_insert(("UPDATE qc_folders SET qc_by = %(qc_by)s "
                                    " WHERE folder_uid = %(folder_id)s"),
                                {'folder_id': folder_id,
                                    'qc_by': current_user.id
                                    })
    else:
        folder_owner = run_query(("SELECT f.*, u.username from qc_folders f, users u "
                                        "    WHERE u.user_id = f.qc_by "
                                        "        AND f.folder_id = %(folder_id)s"),
                                    {'folder_id': folder_id})

        if len(folder_owner) == 1:
            if folder_owner[0]['username'] != username:
                # Not allowed
                project_alias = run_query(("SELECT p.project_alias from folders f, projects p "
                                        "    WHERE f.project_id = p.project_id "
                                        "        AND f.folder_id = %(folder_id)s"),
                                    {'folder_id': folder_id})
                return redirect(url_for('qc', project_alias=project_alias[0]['project_alias']))
        else:
            # Assign user
            q = query_database_insert(("UPDATE qc_folders SET qc_by = %(qc_by)s "
                                    " WHERE folder_id = %(folder_id)s"),
                                {'folder_id': folder_id,
                                    'qc_by': current_user.id
                                    })
    # File submitted
    if file_id_q is not None:
        qc_info = request.values.get('qc_info')
        qc_val = request.values.get('qc_val')
        user_id = run_query("SELECT user_id FROM users WHERE username = %(username)s",
                                 {'username': username})[0]
        if qc_val != "0" and qc_info == "":
            msg = "Error: The field QC Details can not be empty if the file has an issue.<br>Please try again."
        else:
            if transcription == 1:
                q = query_database_insert(("UPDATE qc_files SET "
                                "      file_qc = %(qc_val)s, "
                                "      qc_by = %(qc_by)s, "
                                "      qc_info = %(qc_info)s "
                                " WHERE file_uid = %(file_id)s"),
                               {'file_id': file_id_q,
                                'qc_info': qc_info,
                                'qc_val': qc_val,
                                'qc_by': user_id['user_id']
                                })
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
                                })
            logger.info("file_id: {}".format(file_id_q))
            return redirect(url_for('qc_process', folder_id=folder_id))
    
    if transcription == 1:
        project_id = run_query("SELECT project_id from transcription_folders WHERE folder_transcription_id = %(folder_id)s",
                                {'folder_id': folder_id})[0]
    else:
        project_id = run_query("SELECT project_id from folders WHERE folder_id = %(folder_id)s",
                                {'folder_id': folder_id})[0]
    
    project_settings = run_query("SELECT * FROM qc_settings WHERE project_id = %(project_id)s",
                                      {'project_id': project_id['project_id']})[0]

    if transcription == 1:
        folder_qc_check = run_query(("SELECT "
                                      "  CASE WHEN q.qc_status = 0 THEN 'QC Passed' "
                                      "          WHEN q.qc_status = 1 THEN 'QC Failed' "
                                      "          ELSE 'QC Pending' END AS qc_status, "
                                      "      qc_ip, u.username AS qc_by, "
                                      "      date_format(q.updated_at, '%Y-%m-%d') AS updated_at"
                                      " FROM qc_folders q, "
                                      "      users u WHERE q.qc_by=u.user_id "
                                      "      AND q.folder_uid = %(folder_id)s"),
                                     {'folder_id': folder_id})
    else:
        folder_qc_check = run_query(("SELECT "
                                      "  CASE WHEN q.qc_status = 0 THEN 'QC Passed' "
                                      "          WHEN q.qc_status = 1 THEN 'QC Failed' "
                                      "          ELSE 'QC Pending' END AS qc_status, "
                                      "      qc_ip, u.username AS qc_by, "
                                      "      date_format(q.updated_at, '%Y-%m-%d') AS updated_at"
                                      " FROM qc_folders q, "
                                      "      users u WHERE q.qc_by=u.user_id "
                                      "      AND q.folder_id = %(folder_id)s"),
                                     {'folder_id': folder_id})
    
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
    
    if transcription == 1:
        folder_stats1 = run_query(("SELECT count(file_transcription_id) as no_files "
                                        "    FROM transcription_files WHERE folder_transcription_id = %(folder_id)s"),
                                    {'folder_id': folder_id})
        folder_stats2 = run_query(("SELECT count(DISTINCT c.file_transcription_id) as no_errors "
                                        "    FROM transcription_files_checks c "
                                        "    WHERE file_transcription_id IN ("
                                        "        SELECT file_transcription_id "
                                        "        FROM transcription_files WHERE folder_transcription_id = %(folder_id)s) "
                                        "        AND check_results = 1"),
                                    {'folder_id': folder_id})
        project_alias = run_query(("SELECT p.project_alias FROM projects p, transcription_folders t WHERE  "
                                    "  t.folder_transcription_id = %(folder_id)s and p.project_id = t.project_id"),
                                   {'folder_id': folder_id})[0]
    else: 
        folder_stats1 = run_query(("SELECT count(file_id) as no_files "
                                        "    FROM files WHERE folder_id = %(folder_id)s"),
                                    {'folder_id': folder_id})
        folder_stats2 = run_query(("SELECT count(DISTINCT c.file_id) as no_errors "
                                        "    FROM files_checks c "
                                        "    WHERE file_id IN ("
                                        "        SELECT file_id "
                                        "        FROM files WHERE folder_id = %(folder_id)s) "
                                        "        AND check_results = 1"),
                                    {'folder_id': folder_id})
        project_alias = run_query(("SELECT p.project_alias FROM projects p, folders t WHERE  "
                                    "  t.folder_id = %(folder_id)s and p.project_id = t.project_id"),
                                   {'folder_id': folder_id})[0]

    folder_stats = {
        'no_files': folder_stats1[0]['no_files'],
        'no_errors': folder_stats2[0]['no_errors']
    }
    logger.info("qc_status: {} | no_files: {}".format(folder_qc['qc_status'], folder_stats['no_files']))
    
    project_qc_settings = run_query(("SELECT * FROM qc_settings WHERE project_id = %(project_id)s"),
                                    {'project_id': project_id['project_id']})[0]
    
    if folder_qc['qc_status'] == "QC Pending" and folder_stats['no_files'] > 0:
        # Setup the files for QC
        if transcription == 1:
            in_qc = run_query("SELECT count(*) as no_files FROM qc_files WHERE folder_uid = %(folder_id)s",
                               {'folder_id': folder_id})
        else:
            in_qc = run_query("SELECT count(*) as no_files FROM qc_files WHERE folder_id = %(folder_id)s",
                               {'folder_id': folder_id})
        
        if in_qc[0]['no_files'] == 0:
            if transcription == 1:
                q = query_database_insert("DELETE FROM qc_folders WHERE folder_uid = %(folder_id)s",
                                    {'folder_id': folder_id})
                q = query_database_insert("INSERT INTO qc_folders (folder_uid, qc_status, qc_level) VALUES (%(folder_id)s, 9, %(qc_level)s)",
                                 {'folder_id': folder_id, 'qc_level': project_qc_settings['qc_level']})
            else:
                q = query_database_insert("DELETE FROM qc_folders WHERE folder_id = %(folder_id)s",
                                    {'folder_id': folder_id})
                q = query_database_insert("INSERT INTO qc_folders (folder_id, qc_status, qc_level) VALUES (%(folder_id)s, 9, %(qc_level)s)",
                                 {'folder_id': folder_id, 'qc_level': project_qc_settings['qc_level']})    
            
            no_files_for_qc = math.ceil(folder_stats['no_files'] * (float(project_settings['qc_percent']) / 100))
            if no_files_for_qc < 10:
                if folder_stats['no_files'] > 10:
                    no_files_for_qc = 10
                else:
                    no_files_for_qc = folder_stats['no_files']
            if project_settings['qc_filenames'] != None:
                if transcription == 1:
                    q = query_database_insert(("INSERT INTO qc_files (folder_uid, file_uid) ("
                                  " SELECT folder_transcription_id, file_transcription_id "
                                  "  FROM transcription_files WHERE folder_transcription_id = %(folder_id)s "
                                  "    AND {} "
                                  "  ORDER BY RAND() LIMIT {})").format(project_settings['qc_filenames'], no_files_for_qc),
                                 {'folder_id': folder_id})
                else:
                    q = query_database_insert(("INSERT INTO qc_files (folder_id, file_id) ("
                                  " SELECT folder_id, file_id "
                                  "  FROM files WHERE folder_id = %(folder_id)s "
                                  "    AND {} "
                                  "  ORDER BY RAND() LIMIT {})").format(project_settings['qc_filenames'], no_files_for_qc),
                                 {'folder_id': folder_id})
            else:
                if transcription == 1:
                    q = query_database_insert(("INSERT INTO qc_files (folder_uid, file_uid) ("
                                  " SELECT folder_transcription_id, file_transcription_id "
                                  "  FROM transcription_files WHERE folder_transcription_id = %(folder_id)s "
                                  "  ORDER BY RAND() LIMIT {})").format(no_files_for_qc),
                                 {'folder_id': folder_id})
                else:
                    q = query_database_insert(("INSERT INTO qc_files (folder_id, file_id) ("
                                  " SELECT folder_id, file_id "
                                  "  FROM files WHERE folder_id = %(folder_id)s "
                                  "  ORDER BY RAND() LIMIT {})").format(no_files_for_qc),
                                 {'folder_id': folder_id})
            logger.info("no_files_for_qc: {}".format(no_files_for_qc))
            return redirect(url_for('qc_loading1', folder_id=folder_id))
        else:
            if transcription == 1:
                qc_stats_q = run_query(("WITH errors AS "
                                         "         (SELECT count(file_uid) as no_files "
                                         "             FROM qc_files "
                                         "             WHERE folder_uid = %(folder_id)s "
                                         "                 AND file_qc > 0 AND file_qc != 9),"
                                         "passed AS "
                                         "         (SELECT count(file_uid) as no_files "
                                         "             FROM qc_files "
                                         "             WHERE folder_uid = %(folder_id)s "
                                         "                 AND file_qc = 0),"
                                         "total AS (SELECT count(file_uid) as no_files FROM qc_files "
                                         "             WHERE folder_uid = %(folder_id)s)"
                                         " SELECT t.no_files, e.no_files as no_errors,"
                                         "         p.no_files as no_passed "
                                         " FROM errors e, total t, passed p "),
                                        {'folder_id': folder_id})[0]
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
                                        {'folder_id': folder_id})[0]
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
            if transcription == 1:
                folder = run_query("SELECT * FROM transcription_folders WHERE folder_transcription_id = %(folder_id)s",
                                    {'folder_id': folder_id})[0]
            else:
                folder = run_query("SELECT * FROM folders WHERE folder_id = %(folder_id)s",
                                    {'folder_id': folder_id})[0]
            if qc_stats['no_files'] != int(qc_stats['no_errors']) + int(qc_stats['passed']):
                if transcription == 1:
                    file_qc = run_query(("SELECT f.file_transcription_id as file_id FROM qc_files q, transcription_files f "
                                          "  WHERE q.file_uid = f.file_transcription_id "
                                          "     AND f.folder_transcription_id = %(folder_id)s AND q.file_qc = 9 order by file_uid "
                                          "  LIMIT 1 "),
                                         {'folder_id': folder_id})[0]
                    file_details = run_query(("SELECT f.file_transcription_id as file_id, f.folder_transcription_id as folder_id, f.file_name, 0 as sensitive_contents "
                                               " FROM transcription_files f WHERE f.file_transcription_id = %(file_id)s"),
                                              {'file_id': file_qc['file_id']})[0]
                    file_checks = run_query(("SELECT file_check, check_results, "
                                              "       CASE WHEN check_info = '' THEN 'Check passed.' "
                                              "           ELSE check_info END AS check_info "
                                              "   FROM transcription_files_checks WHERE file_transcription_id = %(file_id)s"),
                                             {'file_id': file_qc['file_id']})
                    file_metadata = pd.DataFrame()
                    folder = run_query(
                        ("SELECT fol.* FROM transcription_folders fol, transcription_files f where f.folder_transcription_id = fol.folder_transcription_id and f.file_transcription_id = %(file_id)s"),
                        {'file_id': file_qc['file_id']})[0]
                else:
                    file_qc = run_query(("SELECT f.file_id FROM qc_files q, files f "
                                          "  WHERE q.file_id = f.file_id "
                                          "     AND f.folder_id = %(folder_id)s AND q.file_qc = 9 order by file_id "
                                          "  LIMIT 1 "),
                                         {'folder_id': folder_id})[0]
                    file_details = run_query(("SELECT f.file_id, f.folder_id, f.file_name, COALESCE(s.sensitive_contents, 0) as sensitive_contents "
                                               " FROM files f LEFT JOIN sensitive_contents s ON f.file_id = s.file_id WHERE f.file_id = %(file_id)s"),
                                              {'file_id': file_qc['file_id']})[0]
                    file_checks = run_query(("SELECT file_check, check_results, "
                                              "       CASE WHEN check_info = '' THEN 'Check passed.' "
                                              "           ELSE check_info END AS check_info "
                                              "   FROM files_checks WHERE file_id = %(file_id)s"),
                                             {'file_id': file_qc['file_id']})
                    file_metadata = pd.DataFrame(run_query(("SELECT tag, taggroup, tagid, value "
                                                             "   FROM files_exif "
                                                             "   WHERE file_id = %(file_id)s "
                                                             "       AND lower(filetype) = 'tif' "
                                                             "   ORDER BY taggroup, tag "),
                                                            {'file_id': file_qc['file_id']}))
                    folder = run_query(
                        ("SELECT * FROM folders "
                        "  WHERE folder_id IN (SELECT folder_id FROM files WHERE file_id = %(file_id)s)"),
                        {'file_id': file_qc['file_id']})[0]

                # DZI zoomable image
                if transcription == 1:
                    zoom_filename = '../../static/image_previews/{}/{}.dzi'.format(file_details['folder_id'], file_qc['file_id'])
                    print(os.path.isfile('static/image_previews/{}/{}.dzi'.format(file_details['folder_id'], file_qc['file_id'])))
                    if os.path.isfile('static/image_previews/{}/{}.dzi'.format(file_details['folder_id'], file_qc['file_id'])):
                        tarimgfile = "static/image_previews/{}/{}_files.tar".format(file_details['folder_id'], file_qc['file_id'])
                        imgfolder = "static/image_previews/{}/".format(file_details['folder_id'])
                        if os.path.isfile(tarimgfile):
                            if os.path.isdir("static/image_previews/{}/{}_files".format(file_details['folder_id'], file_qc['file_id'])) is False:
                                try:
                                    with tarfile.open(tarimgfile, "r") as tf:
                                        tf.extractall(path=imgfolder)
                                except: 
                                    logger.error("Couln't open {}".format(tarimgfile))
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
                    # Transcriptions
                    tables = {}
                    i = 0
                    t_sources = run_query("SELECT transcription_source_id, transcription_source_name, CONCAT(transcription_source_notes, ' ', transcription_source_date) as source_notes FROM transcription_sources WHERE project_id = %(project_id)s", {'project_id': project_id['project_id']})
                    for t_source in t_sources:
                        transcription_text = pd.DataFrame(run_query(("""
                                                    SELECT fields.field_name as field, COALESCE(t.transcription_text, '') as value 
                                                        FROM transcription_fields fields LEFT JOIN transcription_files_text t ON (fields.field_id = t.field_id) 
                                                        WHERE fields.transcription_source_id = %(source_id)s and t.file_transcription_id = %(file_id)s
                                                        ORDER BY fields.sort_by
                                                        """), {'source_id': t_source['transcription_source_id'], 'file_id': file_qc['file_id']}))
                        tables[i] = {'name': t_source['transcription_source_name'],
                                        'table': transcription_text.to_html(table_id='transcription_text', index=False, border=0,
                                                                            escape=True,
                                                                            classes=["display", "compact", "table-striped"]),
                                        'source_info': t_source['source_notes']}
                        i += 1
                        
                else:
                    zoom_filename = '../../static/image_previews/folder{}/{}.dzi'.format(file_details['folder_id'], file_qc['file_id'])
                    
                    if os.path.isfile('static/image_previews/folder{}/{}.dzi'.format(file_details['folder_id'], file_qc['file_id'])):
                        tarimgfile = "static/image_previews/folder{}/{}_files.tar".format(file_details['folder_id'], file_qc['file_id'])
                        imgfolder = "static/image_previews/folder{}/".format(file_details['folder_id'])
                        if os.path.isfile(tarimgfile):
                            if os.path.isdir("static/image_previews/folder{}/{}_files".format(file_details['folder_id'], file_qc['file_id'])) is False:
                                try:
                                    with tarfile.open(tarimgfile, "r") as tf:
                                        tf.extractall(path=imgfolder)
                                except: 
                                    logger.error("Couln't open {}".format(tarimgfile))
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
                if transcription == 1:
                    return render_template("qc_file_transcription.html",
                                    transcription=transcription,
                                    zoom_exists=zoom_exists, zoom_filename=zoom_filename,
                                    zoom_js=zoom_js, folder=folder, qc_stats=qc_stats,
                                    folder_id=folder_id, file_qc=file_qc, project_settings=project_settings,
                                    file_details=file_details, file_checks=file_checks, username=username,
                                    project_alias=project_alias['project_alias'],
                                    msg=msg, form=form,
                                    site_env=site_env, site_net=site_net, site_ver=site_ver,
                                    analytics_code=settings.analytics_code)
                else:
                    return render_template("qc_file.html",
                                        zoom_exists=zoom_exists, zoom_filename=zoom_filename,
                                        zoom_js=zoom_js, folder=folder, qc_stats=qc_stats,
                                        folder_id=folder_id, file_qc=file_qc, project_settings=project_settings,
                                        file_details=file_details, file_checks=file_checks, username=username,
                                        project_alias=project_alias['project_alias'],
                                        tables=[file_metadata.to_html(table_id='file_metadata', index=False, border=0,
                                                                        escape=False,
                                                                        classes=["display", "compact", "table-striped"])],
                                        msg=msg, form=form,
                                        site_env=site_env, site_net=site_net, site_ver=site_ver,
                                        analytics_code=settings.analytics_code)
            else:
                if transcription == 1:
                    error_files = run_query(("SELECT f.file_name, "
                                         " CASE WHEN q.file_qc = 1 THEN 'Critical Issue' "
                                         " WHEN q.file_qc = 2 THEN 'Major Issue' "
                                         " WHEN q.file_qc = 3 THEN 'Minor Issue' END as file_qc, "
                                         " q.qc_info FROM qc_files q, transcription_files f "
                                              "  WHERE q.folder_uid = %(folder_id)s "
                                              "  AND q.file_qc > 0 AND q.file_uid = f.file_transcription_id"),
                                             {'folder_id': folder_id})
                else:
                    error_files = run_query(("SELECT f.file_name, "
                                         " CASE WHEN q.file_qc = 1 THEN 'Critical Issue' "
                                         " WHEN q.file_qc = 2 THEN 'Major Issue' "
                                         " WHEN q.file_qc = 3 THEN 'Minor Issue' END as file_qc, "
                                         " q.qc_info FROM qc_files q, files f "
                                              "  WHERE q.folder_id = %(folder_id)s "
                                              "  AND q.file_qc > 0 AND q.file_id = f.file_id"),
                                             {'folder_id': folder_id})
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
                if transcription == 1:    
                    return render_template('qc_transcription_done.html',
                                        folder_id=folder_id, folder=folder, qc_stats=qc_stats,
                                        project_settings=project_settings, username=username,
                                        error_files=error_files, qc_folder_result=qc_folder_result,
                                        form=form, site_env=site_env, site_net=site_net, site_ver=site_ver,
                                        analytics_code=settings.analytics_code)
                else:
                    return render_template('qc_done.html',
                                        folder_id=folder_id, folder=folder, qc_stats=qc_stats,
                                        project_settings=project_settings, username=username,
                                        error_files=error_files, qc_folder_result=qc_folder_result,
                                        form=form, site_env=site_env, site_net=site_net, site_ver=site_ver,
                                        analytics_code=settings.analytics_code)
    else:
        error_msg = "Folder is not available for QC."
        return render_template('error.html', error_msg=error_msg,
                               project_alias=project_alias['project_alias'], site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 400


@app.route('/qc_prep/<folder_id>/', methods=['POST', 'GET'], provide_automatic_options=False)
@login_required
def qc_loading1(folder_id):
    """Prepare QC for a folder"""
    return render_template('qc_prep.html', folder_id=folder_id, 
                               project_alias="", site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code)


@app.route('/qc_loading/<folder_id>/', methods=['POST', 'GET'], provide_automatic_options=False)
@login_required
def qc_loading2(folder_id):
    """Prepare QC for a folder"""
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    username = current_user.name

    try:
        folder_id = int(folder_id)
        transcription = 0
    except:
        try:
            # Allow for UUIDs
            folder_id = UUID(folder_id)
            transcription = 1
        except:
            raise InvalidUsage('invalid folder_id value', status_code=400)
    folder_id = str(folder_id)
    # Expand the tars for the selected images
    if transcription == 1:
        files_qc = run_query(("SELECT file_uid as file_id FROM qc_files WHERE folder_uid = %(folder_id)s ORDER BY file_uid LIMIT 2 "),
                                {'folder_id': folder_id})
        for f in files_qc:
            tarimgfile = "static/image_previews/{}/{}_files.tar".format(folder_id, f['file_id'])
            imgfolder = "static/image_previews/{}/".format(folder_id)
            if os.path.isfile(tarimgfile):
                if os.path.isdir("static/image_previews/{}/{}_files".format(folder_id, f['file_id'])) is False:
                    try:
                        with tarfile.open(tarimgfile, "r") as tf:
                            tf.extractall(path=imgfolder)
                    except: 
                        logger.error("Couln't open {}".format(tarimgfile))
    else:
        files_qc = run_query(("SELECT file_id FROM qc_files WHERE folder_id = %(folder_id)s ORDER BY file_id LIMIT 2 "),
                                {'folder_id': folder_id})
        for f in files_qc:
            tarimgfile = "static/image_previews/folder{}/{}_files.tar".format(folder_id, f['file_id'])
            imgfolder = "static/image_previews/folder{}/".format(folder_id)
            if os.path.isfile(tarimgfile):
                if os.path.isdir("static/image_previews/folder{}/{}_files".format(folder_id, f['file_id'])) is False:
                    try:
                        with tarfile.open(tarimgfile, "r") as tf:
                            tf.extractall(path=imgfolder)
                    except: 
                        logger.error("Couln't open {}".format(tarimgfile))
    subprocess.Popen(["python3", "extract_previews.py", folder_id, "&"])
    return redirect(url_for('qc_process', folder_id=folder_id))


@app.route('/qc_done/<folder_id>/', methods=['POST', 'GET'], provide_automatic_options=False)
@login_required
def qc_done(folder_id):
    """Run QC on a folder"""
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    username = current_user.name

    try:
        folder_id = int(folder_id)
        transcription = 0
    except:
        try:
            # Allow for UUIDs
            folder_id = UUID(folder_id)
            folder_id = str(folder_id)
            transcription = 1
        except:
            raise InvalidUsage('invalid folder_id value', status_code=400)
        
    if transcription == 1:
        project_admin = run_query(("SELECT count(*) as no_results "
                                    "    FROM users u, qc_projects p, transcription_folders f "
                                    "    WHERE u.username = %(username)s "
                                    "        AND p.project_id = f.project_id "
                                    "        AND f.folder_transcription_id = %(folder_id)s "
                                    "        AND u.user_id = p.user_id"),
                                   {'username': username, 'folder_id': folder_id})[0]
    else:
        project_admin = run_query(("SELECT count(*) as no_results "
                                    "    FROM users u, qc_projects p, folders f "
                                    "    WHERE u.username = %(username)s "
                                    "        AND p.project_id = f.project_id "
                                    "        AND f.folder_id = %(folder_id)s "
                                    "        AND u.user_id = p.user_id"),
                                   {'username': username, 'folder_id': folder_id})[0]
    if project_admin['no_results'] == 0:
        # Not allowed
        return redirect(url_for('home'))
    if transcription == 1:
        project_info = run_query(("SELECT project_id, project_alias "
                                 "   FROM projects "
                                 "   WHERE project_id IN "
                                 "   (SELECT project_id "
                                 "       FROM transcription_folders "
                                 "       WHERE folder_transcription_id = %(folder_id)s)"),
                                {'folder_id': folder_id})[0]
    else:
        project_info = run_query(("SELECT project_id, project_alias "
                                 "   FROM projects "
                                 "   WHERE project_id IN "
                                 "   (SELECT project_id "
                                 "       FROM folders "
                                 "       WHERE folder_id = %(folder_id)s)"),
                                {'folder_id': folder_id})[0]
    project_id = project_info['project_id']
    project_alias = project_info['project_alias']
    qc_info = request.values.get('qc_info')
    qc_status = request.values.get('qc_status')
    user_id = run_query("SELECT user_id FROM users WHERE username = %(username)s",
                             {'username': username})[0]

    project_qc_settings = run_query(("SELECT * FROM qc_settings WHERE project_id = %(project_id)s"),
                                    {'project_id': project_id})[0]
    if transcription == 1:
        fold_id = "folder_uid"
    else:
        fold_id = "folder_id"
    q = query_database_insert((f"UPDATE qc_folders SET qc_status = %(qc_status)s, qc_by = %(qc_by)s, qc_info = %(qc_info)s, qc_level = %(qc_level)s WHERE {fold_id} = %(folder_id)s"),
                         {'folder_id': folder_id,
                          'qc_status': qc_status,
                          'qc_info': qc_info,
                          'qc_by': user_id['user_id'],
                          'qc_level': project_qc_settings['qc_level']
                          })
    # Create folder badge
    clear_badges = run_query(f"DELETE FROM folders_badges WHERE {fold_id} = %(folder_id)s and badge_type = 'qc_status'",
            {'folder_id': folder_id})
    if qc_status == "0":
        badgecss = "bg-success"
        qc_info = "QC Passed"
    elif qc_status == "1":
        badgecss = "bg-danger"
        qc_info = "QC Failed"
    print(qc_status)
    print(badgecss)
    if transcription == 1:
        query = (
            "INSERT INTO folders_badges (folder_uid, badge_type, badge_css, badge_text, updated_at) "
            " VALUES (%(folder_id)s, 'qc_status', %(badgecss)s, %(msg)s, CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(msg)s,"
            " badge_css = %(badgecss)s, updated_at = CURRENT_TIMESTAMP")
    else:
        query = (
            "INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text, updated_at) "
            " VALUES (%(folder_id)s, 'qc_status', %(badgecss)s, %(msg)s, CURRENT_TIMESTAMP) ON DUPLICATE KEY UPDATE badge_text = %(msg)s,"
            " badge_css = %(badgecss)s, updated_at = CURRENT_TIMESTAMP")
    res = query_database_insert(query, {'folder_id': folder_id, 'badgecss': badgecss, 'msg': qc_info})
    # Change inspection level, if needed
    project_qc_settings = run_query(("SELECT * FROM qc_settings WHERE project_id = %(project_id)s"),
                             {'project_id': project_id})[0]
    if transcription == 1:
        project_qc_hist = run_query(("SELECT q.* FROM qc_folders q, transcription_folders f "
                                 " WHERE f.project_id = %(project_id)s AND q.folder_uid = f.folder_transcription_id "
                                 "    AND q.qc_status != 9 "
                                 " ORDER BY updated_at DESC LIMIT 5"),
                                    {'project_id': project_id})
    else:
        project_qc_hist = run_query(("SELECT q.* FROM qc_folders q, folders f "
                                 " WHERE f.project_id = %(project_id)s AND q.folder_id = f.folder_id "
                                 "    AND q.qc_status != 9 "
                                 " ORDER BY updated_at DESC LIMIT 5"),
                                    {'project_id': project_id})
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
                                {'project_id': project_id, 'qc_level': level})
    return redirect(url_for('qc', project_alias=project_alias))


@app.route('/home/', methods=['GET'], provide_automatic_options=False)
@login_required
def home():
    """Home for user, listing projects and options"""
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Declare the login form
    form = LoginForm(request.form)

    user_name = current_user.name
    is_admin = user_perms('', user_type='admin')
    logger.info("is_admin:{}".format(is_admin))
    ip_addr = request.environ['REMOTE_ADDR']
    projects = run_query(("select p.project_title, p.project_id, p.project_alias, date_format(p.project_start, '%b-%Y') as project_start, "
                               "     date_format(p.project_end, '%b-%Y') as project_end, p.qc_status, p.project_unit "
                               " FROM qc_projects qp, "
                               "       users u, projects p "
                               " WHERE qp.project_id = p.project_id AND qp.user_id = u.user_id AND u.username = %(username)s "
                               "     AND p.project_alias IS NOT NULL AND p.project_status != 'Completed' "
                               " GROUP BY p.project_title, p.project_id, p.project_alias, "
                               "     p.project_start, p.project_end, p.qc_status, p.project_unit "
                               " ORDER BY p.projects_order DESC"),
                              {'username': user_name})
    project_list = []
    for project in projects:
        logger.info("project: {}".format(project).encode("utf-8"))
        project_total = run_query(("SELECT count(*) as no_files "
                                        "    FROM files "
                                        "    WHERE folder_id IN ("
                                        "        SELECT folder_id FROM folders WHERE project_id = %(project_id)s)"),
                                       {'project_id': project['project_id']})
        project_ok = run_query(("WITH a AS ("
                                     "   SELECT file_id FROM files WHERE folder_id IN "
                                     "       (SELECT folder_id from folders WHERE project_id = %(project_id)s)"
                                     "  ),"
                                     "   data AS ("
                                     "   SELECT c.file_id, sum(check_results) as check_results "
                                     "   FROM files_checks c, a "
                                     "   WHERE c.file_id = a.file_id "
                                     "   GROUP BY c.file_id) "
                                     " SELECT count(file_id) as no_files FROM data WHERE check_results = 0"),
                                    {'project_id': project['project_id']})
        project_err = run_query(
            ("SELECT count(distinct file_id) as no_files FROM files_checks WHERE check_results "
             "= 1 AND "
             "file_id in (SELECT file_id from files where folder_id IN (SELECT folder_id from folders WHERE project_id = %(project_id)s))"),
            {'project_id': project['project_id']})
        project_public = run_query(("SELECT COALESCE(images_public, 0) as no_files FROM projects_stats WHERE "
                                         " project_id = %(project_id)s"),
                                        {'project_id': project['project_id']})
        project_running = run_query(("SELECT count(distinct file_id) as no_files FROM files_checks WHERE "
                                          "check_results "
                                          "= 9 AND "
                                          "file_id in ("
                                          "SELECT file_id FROM files WHERE folder_id IN (SELECT folder_id FROM folders "
                                          "WHERE project_id = %(project_id)s))"),
                                         {'project_id': project['project_id']})
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
                               username=username, full_name=full_name,
                               is_admin=is_admin, msg=msg,
                               today_date=datetime.today().strftime('%Y-%m-%d'),
                               form=form, site_env=site_env, site_net=site_net, site_ver=site_ver,
                               analytics_code=settings.analytics_code)


@app.route('/invoice/', methods=['GET'], provide_automatic_options=False)
@login_required
def invoice(msg=None):
    """Invoice Reconciliation"""
    
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
        project_list = run_query(("select p.project_title, p.project_id, p.project_alias, date_format(p.project_start, '%b-%Y') as project_start, "
                               "     date_format(p.project_end, '%b-%Y') as project_end, p.qc_status, p.project_unit "
                               " FROM qc_projects qp, "
                               "       users u, projects p "
                               " WHERE qp.project_id = p.project_id AND qp.user_id = u.user_id AND u.username = %(username)s "
                               "     AND p.project_alias IS NOT NULL AND p.project_status != 'Completed' "
                               " GROUP BY p.project_title, p.project_id, p.project_alias, "
                               "     p.project_start, p.project_end, p.qc_status, p.project_unit "
                               " ORDER BY p.projects_order DESC"),
                              {'username': username})
        msg = ""
        return render_template('invoice.html',
                               username=username, project_list=project_list,
                               is_admin=is_admin, msg=msg,
                               today_date=datetime.today().strftime('%Y-%m-%d'),
                               form=form, site_env=site_env, site_net=site_net, site_ver=site_ver,
                               analytics_code=settings.analytics_code)


@app.route('/invoice_recon/', methods=['POST'], provide_automatic_options=False)
@login_required
def invoice_recon(msg=None):
    """Invoice Reconciliation"""
    
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
        def checkval(query, file_name):
            res = run_query(query, {'file_name': file_name})
            return res 
        project_id = request.values.get('project_id')
        f = request.files.get('file')
        files = pd.read_csv(f) # read csv
        files = files.set_axis(['files'], axis=1)
        files['files'] = files['files'].str.replace('.tif','')
        randomval = random.randint(1000, 9999)
        files['randomval'] = randomval
        files.dropna(inplace = True)
        files = files[files['files'] != '']
        res = [tuple(x) for x in files.to_numpy()]
        results = cur.executemany("INSERT INTO invoice_recon (file_name, randomint) VALUES (%s, %s)", res)
        # Update table
        res = run_query(("with data as (select f.file_id, f.file_name from files f, folders fol where f.folder_id = fol.folder_id and fol.project_id = %(project_id)s) UPDATE invoice_recon i join data d on i.file_name = d.file_name SET i.file_id = d.file_id where randomint = %(randomint)s"), {'randomint': randomval, 'project_id': project_id})
        res = run_query(("with data as (select f.file_id, f.file_name, f.dams_uan from files f, folders fol where f.folder_id = fol.folder_id and fol.project_id = %(project_id)s) UPDATE invoice_recon i join data d on i.file_name = d.file_name SET i.dams_uan = d.dams_uan where randomint = %(randomint)s"), {'randomint': randomval, 'project_id': project_id})
        no_files = run_query(("SELECT count(*) as no_files FROM invoice_recon WHERE randomint = %(randomint)s"), {'randomint': randomval})[0]['no_files']
        no_files_osprey = run_query(("SELECT count(*) as no_files FROM invoice_recon WHERE randomint = %(randomint)s and file_id IS NOT NULL"), {'randomint': randomval})[0]['no_files']
        no_files_dams = run_query(("SELECT count(*) as no_files FROM invoice_recon WHERE randomint = %(randomint)s AND dams_uan IS NOT NULL"), {'randomint': randomval})[0]['no_files']
        msg = ""
        if int(no_files_osprey) < int(no_files):
            count_msg = "Reconciliation failed: {:,} files not in Osprey".format(int(no_files) - int(no_files_osprey))
            count_msg_css = "danger"
        elif int(no_files_dams) < int(no_files):
            count_msg = "Reconciliation failed: {:,} files not in DAMS".format(int(no_files) - int(no_files_dams))
            count_msg_css = "danger"
        elif (int(no_files_osprey) == int(no_files)) and (int(no_files_dams) == int(no_files)):
            count_msg = "Reconciliation passed: all files accounted for."
            count_msg_css = "success"
        else:
            count_msg = "Reconciliation failed: SYSTEM ERROR"
            count_msg_css = "danger"
        project_info = run_query(("SELECT * FROM projects WHERE project_id = %(project_id)s"), {'project_id': project_id})[0]
        now = datetime.now()
        return render_template('invoice_recon.html',
                               username=username, 
                               no_files="{:,}".format(no_files),
                               no_files_osprey="{:,}".format(no_files_osprey),
                               no_files_dams="{:,}".format(no_files_dams),
                               is_admin=is_admin, msg=msg,
                               now=now, randomint=randomval,
                               project_info=project_info,
                               count_msg=count_msg, count_msg_css=count_msg_css,
                               today_date=datetime.today().strftime('%Y-%m-%d'),
                               form=form, site_env=site_env, site_net=site_net, site_ver=site_ver,
                               analytics_code=settings.analytics_code)


@app.route('/invoice_recon_dl/', methods=['POST'], provide_automatic_options=False)
@login_required
def invoice_recon_dl(randomint=None):
    """Download Invoice Reconciliation"""
    
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
        randomint = request.values.get('randomint')
        current_time = strftime("%Y%m%d_%H%M%S", localtime())
        # from https://stackoverflow.com/a/68136716
        buffer = io.BytesIO()
        data = pd.DataFrame(run_query(("SELECT i.file_name, i.file_id, i.dams_uan, fol.project_folder FROM invoice_recon i left join files f on (i.file_id = f.file_id) left join folders fol on (f.folder_id = fol.folder_id) WHERE i.randomint = %(randomint)s"), {'randomint': randomint})).to_excel(buffer, index=False)
        headers = {
            'Content-Disposition': 'attachment; filename=invoice_reconciliation_{}.xlsx'.format(current_time),
            'Content-type': 'application/vnd.ms-excel'
        }
        return Response(buffer.getvalue(), mimetype='application/vnd.ms-excel', headers=headers)
        


@app.route('/create_new_project/', methods=['POST'], provide_automatic_options=False)
@login_required
def create_new_project():
    """Create a new project"""
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))

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
    # p_unitstaff = request.values.get('p_unitstaff')
    project_id = query_database_insert(("INSERT INTO projects  "
                              "   (project_title, project_unit, project_alias, project_description, "
                              "    project_coordurl, project_area, project_section, project_method, "
                              "    project_manager, project_status, project_type, project_datastorage,"
                              "    project_start, projects_order, stats_estimated) "
                              "  (SELECT "
                              "            %(p_title)s, %(p_unit)s, %(p_alias)s, %(p_desc)s, "
                              "            %(p_coordurl)s, %(p_area)s, %(p_md)s, %(p_method)s, "
                              "            %(p_manager)s, 'Ongoing', %(p_prod)s, %(p_storage)s, "
                              "            %(p_start)s, max(projects_order) + 1, 0 FROM projects)"),
                             {'p_title': p_title, 'p_unit': p_unit, 'p_alias': p_alias, 'p_desc': p_desc,
                              'p_url': p_url, 'p_coordurl': p_coordurl, 'p_area': p_area, 'p_md': p_md,
                              'p_noobjects': p_noobjects, 'p_method': p_method, 'p_manager': p_manager,
                              'p_prod': p_prod, 'p_storage': p_storage, 'p_start': p_start
                              }, return_res = True)
    logger.debug("PROJECT ID: {}".format(project_id))
    project = query_database_insert(("INSERT INTO projects_stats (project_id, collex_total, collex_to_digitize) VALUES (%(project_id)s, %(collex_total)s, %(collex_total)s)"),
                             {'project_id': project_id,
                              'collex_total': int(p_noobjects)})
    user_project = query_database_insert(("INSERT INTO qc_projects (project_id, user_id) VALUES (%(project_id)s, %(user_id)s)"),
                                    {'project_id': project_id,
                                     'user_id': current_user.id})
    if current_user.id != '101':
        user_project = query_database_insert(("INSERT INTO qc_projects (project_id, user_id) VALUES (%(project_id)s, %(user_id)s)"),
                                        {'project_id': project_id,
                                         'user_id': '101'})
    # if p_unitstaff != '':
    #     unitstaff = p_unitstaff.split(',')
    #     logger.info("unitstaff: {}".format(p_unitstaff))
    #     logger.info("len_unitstaff: {}".format(len(unitstaff)))
    #     if len(unitstaff) > 0:
    #         for staff in unitstaff:
    #             staff_user_id = run_query("SELECT user_id FROM users WHERE username = %(username)s",
    #                                            {'username': staff.strip()})
    #             if len(staff_user_id) == 1:
    #                 user_project = query_database_insert(("INSERT INTO qc_projects (project_id, user_id) VALUES "
    #                                                  "    (%(project_id)s, %(user_id)s)"),
    #                                                 {'project_id': project_id,
    #                                                  'user_id': staff_user_id[0]['user_id']})
    #             else:
    #                 user_project = query_database_insert(("INSERT INTO users (username, user_active, is_admin) VALUES "
    #                                                "    (%(username)s, 'T', 'F')"),
    #                                               {'username': staff.strip()})
    #                 get_user_project = run_query(("SELECT user_id FROM users WHERE username = %(username)s"),
    #                                                      {'username': staff.strip()})
    #                 user_project = query_database_insert(("INSERT INTO qc_projects (project_id, user_id) VALUES "
    #                                                  "    (%(project_id)s, %(user_id)s)"),
    #                                                 {'project_id': project_id,
    #                                                  'user_id': get_user_project[0]['user_id']})
    fcheck_query = ("INSERT INTO projects_settings (project_id, project_setting, settings_value) VALUES (%(project_id)s, 'project_checks', %(value)s)")
    fcheck_insert = query_database_insert(fcheck_query, {'project_id': project_id, 'value': 'unique_file'})
    fcheck_insert = query_database_insert(fcheck_query, {'project_id': project_id, 'value': 'tifpages'})
    fcheck_insert = query_database_insert(fcheck_query, {'project_id': project_id, 'value': 'md5'})
    file_check = request.values.get('raw_pair')
    if file_check == "1":
        fcheck_insert = query_database_insert(fcheck_query, {'project_id': project_id, 'value': 'raw_pair'})
        fcheck_insert = query_database_insert(fcheck_query, {'project_id': project_id, 'value': 'md5_raw'})
    file_check = request.values.get('tif_compression')
    if file_check == "1":
        fcheck_insert = query_database_insert(fcheck_query, {'project_id': project_id, 'value': 'tif_compression'})
    file_check = request.values.get('magick')
    if file_check == "1":
        fcheck_insert = query_database_insert(fcheck_query, {'project_id': project_id, 'value': 'magick'})
    file_check = request.values.get('jhove')
    if file_check == "1":
        fcheck_insert = query_database_insert(fcheck_query, {'project_id': project_id, 'value': 'jhove'})
    file_check = request.values.get('sequence')
    if file_check == "1":
        fcheck_insert = query_database_insert(fcheck_query, {'project_id': project_id, 'value': 'sequence'})
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
                                   {'username': username, 'project_alias': project_alias})
    if len(project_admin) == 0:
        # Not allowed
        return redirect(url_for('home'))
    project = run_query(("SELECT p.project_id, p.project_alias, "
                              " p.project_title, p.project_alias, p.project_start, p.project_end, "
                              " p.project_unit, p.project_section, p.project_status, NULL as project_url, "
                              " COALESCE(p.project_description, '') as project_description, "
                              " COALESCE(s.collex_to_digitize, 0) AS collex_to_digitize "
                              " FROM projects p LEFT JOIN projects_stats s "
                              "     ON (p.project_id = s.project_id) "
                              " WHERE p.project_alias = %(project_alias)s"),
                             {'project_alias': project_alias})[0]
    return render_template('edit_project.html',
                           username=username,
                           is_admin=is_admin,
                           project=project,
                           form=form,
                           site_env=site_env,
                           site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code)



@app.route('/infprojects/', methods=['GET'], provide_automatic_options=False)
@login_required
def infprojects():
    """Home for informatics projects"""
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Declare the login form
    form = LoginForm(request.form)

    user_name = current_user.name
    is_admin = user_perms('', user_type='admin')
    logger.info("is_admin:{}".format(is_admin))
    ip_addr = request.environ['REMOTE_ADDR']
    inf_section_query = (" SELECT "
                     " CONCAT('<abbr title=\"', u.unit_fullname, '\">', p.project_unit, '</abbr>') as project_unit, "
                     " CONCAT('<strong><a href=\"/infprojects/', p.proj_id, '\">', p.project_title, '</a></strong><br>', p.summary) as project_title, "
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
    list_projects_inf = pd.DataFrame(run_query(inf_section_query))
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
    
    return render_template('infprojects.html', 
                           tables_inf=[list_projects_inf.to_html(table_id='list_projects_inf', index=False,
                                                               border=0, escape=False,
                                                               classes=["display", "w-100"])],
                           form=form,
                           site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code)


@app.route('/infprojects/<proj_id>/', methods=['GET'], provide_automatic_options=False)
@login_required
def infprojects_edit(proj_id=None):
    """Home for informatics projects"""
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Declare the login form
    form = LoginForm(request.form)

    user_name = current_user.name
    is_admin = user_perms('', user_type='admin')
    logger.info("is_admin:{}".format(is_admin))
    ip_addr = request.environ['REMOTE_ADDR']
    proj = ("SELECT * FROM projects_informatics WHERE proj_id = %(proj_id)s")
    project = run_query(proj, {'proj_id': proj_id})[0]
    # units
    units = ("SELECT * FROM si_units")
    si_units = run_query(units)
    
    return render_template('infproject.html', 
                           project=project, si_units=si_units, form=form,
                           site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code)


@app.route('/infprojects/new/', methods=['GET'], provide_automatic_options=False)
@login_required
def new_infprojects():
    """Home for informatics projects"""
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Declare the login form
    form = LoginForm(request.form)

    user_name = current_user.name
    is_admin = user_perms('', user_type='admin')
    logger.info("is_admin:{}".format(is_admin))
    ip_addr = request.environ['REMOTE_ADDR']
    # units
    units = ("SELECT * FROM si_units")
    si_units = run_query(units)
    
    return render_template('newinfproject.html', 
                           si_units=si_units, form=form,
                           site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code)


@app.route('/infprojects/edit/', methods=['POST'], provide_automatic_options=False)
@login_required
def edit_inf_proj():
    """Create or edit an informatics project"""
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))

    username = current_user.name
    if username not in ['villanueval', 'dipietroc']:
        # Not allowed
        return redirect(url_for('home'))
    proj_edit = request.values.get('proj_edit')
    proj_id = request.values.get('proj_id')
    project_title = request.values.get('project_title')
    project_unit = request.values.get('project_unit')
    summary = request.values.get('summary')
    records = request.values.get('records')
    pm = request.values.get('pm')
    project_status = request.values.get('project_status')
    github_link = request.values.get('github_link')
    if github_link == "" or github_link == "None":
        github_link = "NULL"
    else:
        github_link = "'{}'".format(github_link)
    info_link = request.values.get('info_link')
    if info_link == "" or info_link == "None":
        info_link = "NULL"
    else:
        info_link = "'{}'".format(info_link)
    project_start = request.values.get('project_start')
    project_end = request.values.get('project_end')
    if project_end == "":
        project_end = "NULL"
    else:
        project_end = "'{}'".format(project_end)
    if proj_edit == "0":
        # New project
        project_id = query_database_insert(("INSERT INTO projects_informatics "
                              "     (proj_id, project_title, project_unit, summary, records, pm, project_status, github_link, info_link, project_start, project_end) VALUES "
                              "     (%(proj_id)s, %(project_title)s, %(project_unit)s, %(summary)s, %(records)s, %(pm)s, %(project_status)s, {}, {}, %(project_start)s, {})".format(github_link, info_link, project_end)),
                             {  
                                'project_title': project_title, 
                                'project_unit': project_unit, 
                                'summary': summary, 
                                'records': records, 
                                'pm': pm, 
                                'project_status': project_status, 
                                'project_start': project_start,
                                'proj_id': proj_id                                
                              }, return_res = True)
        return redirect(url_for('infprojects_edit', proj_id = proj_id))
    elif proj_edit == "1":
        # Edit existing
        project_id = query_database_insert(("UPDATE projects_informatics SET "
                              "     project_title = %(project_title)s, "
                              "     project_unit = %(project_unit)s, "
                              "     summary = %(summary)s, "
                              "     records = %(records)s, "
                              "     pm = %(pm)s, "
                              "     project_status = %(project_status)s, "
                              "     github_link = {}, "
                              "     info_link = {}, "
                              "     project_start = %(project_start)s, "
                              "     project_end = {} "
                              " WHERE proj_id = %(proj_id)s".format(github_link, info_link, project_end)),
                             {  
                                'project_title': project_title, 
                                'project_unit': project_unit, 
                                'summary': summary, 
                                'records': records, 
                                'pm': pm, 
                                'project_status': project_status, 
                                'github_link': github_link, 
                                'info_link': info_link,
                                'project_start': project_start,
                                'proj_id': proj_id                                
                              }, return_res = False)
        return redirect(url_for('infprojects_edit', proj_id = proj_id))


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
                                   {'username': username, 'project_alias': project_alias})
    if len(project_admin) == 0:
        # Not allowed
        return redirect(url_for('home'))
    project = run_query(("SELECT p.project_id, p.project_alias, "
                              " p.project_title, p.project_alias, p.project_start, p.project_end, "
                              " p.project_unit, p.project_section, p.project_status, NULL as project_url, "
                              " COALESCE(p.project_description, '') as project_description, "
                              " COALESCE(s.collex_to_digitize, 0) AS collex_to_digitize "
                              " FROM projects p LEFT JOIN projects_stats s "
                              "     ON (p.project_id = s.project_id) "
                              " WHERE p.project_alias = %(project_alias)s"),
                             {'project_alias': project_alias})[0]

    projects_links = run_query("SELECT * FROM projects_links WHERE project_id = %(project_id)s ORDER BY table_id",
                               {'project_id': project['project_id']})

    return render_template('proj_links.html',
                           username=username, is_admin=is_admin, project=project,
                           form=form, projects_links=projects_links, site_env=site_env,
                           site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code)


@app.route('/add_links/', methods=['POST'], provide_automatic_options=False)
@login_required
def add_links(project_alias=None):
    """Create a new project"""
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
    username = current_user.name
    is_admin = user_perms('', user_type='admin')
    if is_admin is False:
        # Not allowed
        return redirect(url_for('home'))
    project_alias = request.values.get('project_alias')

    project = run_query(("SELECT project_id "
                         " FROM projects  "
                         " WHERE project_alias = %(project_alias)s"),
                        {'project_alias': project_alias})[0]

    link_title = request.values.get('link_title')
    link_type = request.values.get('link_type')
    link_url = request.values.get('link_url')
    new_link = query_database_insert(("INSERT INTO projects_links "
                              "   (project_id, link_type, link_title, url) "
                              "  (SELECT %(project_id)s, %(link_type)s, %(link_title)s, %(url)s)"),
                             {'project_id': project['project_id'],
                              'link_type': link_type,
                              'link_title': link_title,
                              'url': link_url
                              })
    return redirect(url_for('proj_links', project_alias=project_alias))


@app.route('/project_update/<project_alias>', methods=['POST'], provide_automatic_options=False)
@login_required
def project_update(project_alias):
    """Save edits to a project"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
    username = current_user.name
    is_admin = user_perms('', user_type='admin')
    if is_admin is False:
        # Not allowed
        return redirect(url_for('home'))
    project_id = run_query(("SELECT project_id FROM projects WHERE project_alias = %(project_alias)s"),
                                   {'project_alias': project_alias})
    project_id = project_id[0]['project_id']
    project_admin = run_query(("SELECT count(*) as no_results "
                                    "    FROM users u, qc_projects qp, projects p "
                                    "    WHERE u.username = %(username)s "
                                    "        AND p.project_alias = %(project_alias)s "
                                    "        AND qp.project_id = p.project_id "
                                    "        AND u.user_id = qp.user_id"),
                                   {'username': username, 'project_alias': project_alias})
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
                              'project_alias': project_alias})
    if p_desc != '':
        project = query_database_insert(("UPDATE projects SET "
                                  "   project_description = %(p_desc)s "
                                  " WHERE project_alias = %(project_alias)s"),
                                 {'p_desc': p_desc,
                                  'project_alias': project_alias})
    if p_end != 'None':
        project = query_database_insert(("UPDATE projects SET "
                                  "   project_end = CAST(%(p_end)s AS date) "
                                  " WHERE project_alias = %(project_alias)s "),
                                 {'p_end': p_end,
                                  'project_alias': project_alias})

    if p_noobjects != '0':
        project = query_database_insert(("UPDATE projects_stats SET "
                                  "   collex_to_digitize = %(p_noobjects)s, "
                                  "   collex_ready = %(p_noobjects)s "
                                  " WHERE project_id = %(project_id)s "),
                                 {'project_id': project_id,
                                  'p_noobjects': p_noobjects})

    return redirect(url_for('home'))


@app.route('/file/<file_id>/', methods=['GET'], provide_automatic_options=False)
def file(file_id=None):
    """File details"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))

    if file_id is None:
        error_msg = "File ID is missing."
        return render_template('error.html', error_msg=error_msg, project_alias=None, site_env=site_env, site_net=site_net, site_ver=site_ver), 400
    try:
        file_id = int(file_id)
    except:
        error_msg = "File ID is not valid."
        return render_template('error.html', error_msg=error_msg, project_alias=None, site_env=site_env, site_net=site_net, site_ver=site_ver), 400
            
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Declare the login form
    form = LoginForm(request.form)

    file_id_check = check_file_id(file_id)
    
    if file_id_check is False:
        error_msg = "File ID not found."
        return render_template('error.html', error_msg=error_msg, project_alias=None, site_env=site_env, site_net=site_net, site_ver=site_ver), 400
    
    # Folder info
    folder_info = run_query(
        "SELECT * FROM folders WHERE folder_id IN (SELECT folder_id FROM files WHERE file_id = %(file_id)s)",
        {'file_id': file_id})
    if len(folder_info) == 0:
        error_msg = "Invalid File ID."
        return render_template('error.html', error_msg=error_msg, project_alias=None, site_env=site_env, site_net=site_net, site_ver=site_ver), 400
    else:
        folder_info = folder_info[0]
    file_details = run_query(("WITH data AS ("
                                "         SELECT file_id, "
                                "             CONCAT(%(preview)s, file_id) as preview_image, "
                                "             preview_image as preview_image_ext, "
                                "             folder_id, file_name, dams_uan, file_ext, "
                                "             date_format(created_at, '%Y-%b-%d %T') as created_at, DATEDIFF(NOW(), created_at) as datediff "
                                "             FROM files "
                                "                 WHERE folder_id = %(folder_id)s AND folder_id IN (SELECT folder_id FROM folders)"
                                " UNION "
                                "         SELECT file_id, CONCAT(%(preview)s, file_id) as preview_image, preview_image as preview_image_ext, "
                                "                folder_id, file_name, dams_uan, file_ext, "
                                "             date_format(created_at, '%Y-%b-%d %T') as created_at, DATEDIFF(created_at, NOW()) as datediff "
                                "             FROM files "
                                "                 WHERE folder_id = %(folder_id)s AND folder_id NOT IN (SELECT folder_id FROM folders)"
                                "             ORDER BY file_name"
                                "),"
                                "data2 AS (SELECT file_id, preview_image, file_ext, preview_image_ext, folder_id, file_name, dams_uan, created_at, datediff, "
                                "         lag(file_id,1) over (order by file_name) prev_id,"
                                "         lead(file_id,1) over (order by file_name) next_id "
                                " FROM data)"
                                " SELECT "
                                " file_id, "
                                "     CASE WHEN position('?' in preview_image)>0 THEN preview_image ELSE CONCAT(preview_image, '?') END AS preview_image, "
                                " preview_image_ext, folder_id, file_name, dams_uan, prev_id, next_id, file_ext, created_at, datediff "
                                " FROM data2 WHERE file_id = %(file_id)s LIMIT 1"),
                                {'folder_id': folder_info['folder_id'], 'file_id': file_id,
                                'preview': '/preview_image/'})

    file_details = file_details[0]
    project_alias = run_query(("SELECT COALESCE(project_alias, CAST(project_id AS char)) as project_id FROM projects "
                    " WHERE project_id = %(project_id)s"),
                   {'project_id': folder_info['project_id']})[0]
    project_alias = project_alias['project_id']

    file_checks = run_query(("SELECT file_check, check_results, CASE WHEN check_info = '' THEN 'Check passed.' "
                                " ELSE check_info END AS check_info "
                                " FROM files_checks WHERE file_id = %(file_id)s"),
                                {'file_id': file_id})
    file_postprocessing = run_query(("SELECT post_step, post_results, CASE WHEN post_info = '' THEN 'Step completed.' "
                                    " WHEN post_info IS NULL THEN 'Step completed.' "
                                " ELSE post_info END AS post_info "
                                " FROM file_postprocessing WHERE file_id = %(file_id)s"),
                                {'file_id': file_id})

    image_url = '/preview_image/' + str(file_id)
    file_metadata = pd.DataFrame(run_query(("SELECT tag, taggroup, tagid, value "
                                                 " FROM files_exif "
                                                 " WHERE file_id = %(file_id)s AND "
                                                 "       lower(filetype) = %(file_ext)s AND "
                                                 "       lower(taggroup) != 'system' "
                                                 " ORDER BY taggroup, tag "),
                                                {'file_id': str(file_id), 'file_ext': file_details['file_ext']}))
    
    file_links = run_query("SELECT link_name, link_url, link_aria FROM files_links WHERE file_id = %(file_id)s ",
                                {'file_id': file_id})
        
    file_sensitive = []
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

    # kiosk mode
    kiosk, user_address = kiosk_mode(request, settings.kiosks)

    # New direct link to image
    preview_img_path = "image_previews/folder{}/{}/{}.jpg".format(file_details['folder_id'], "600", file_id)
    if os.path.isfile("static/{}".format(preview_img_path)):
        file_details['preview_img_path'] = preview_img_path
    else:
        file_details['preview_img_path'] = "na_{}.png".format("160")

    # DZI zoomable image
    zoom_filename = '../../static/image_previews/folder{}/{}.dzi'.format(file_details['folder_id'], file_id)

    if os.path.isfile('static/image_previews/folder{}/{}.dzi'.format(file_details['folder_id'], file_id)):
        tarimgfile = "static/image_previews/folder{}/{}_files.tar".format(file_details['folder_id'], file_id)
        imgfolder = "static/image_previews/folder{}/".format(file_details['folder_id'])
        if os.path.isfile(tarimgfile):
            if os.path.isdir("static/image_previews/folder{}/{}_files".format(file_details['folder_id'], file_id)) is False:
                try:
                    with tarfile.open(tarimgfile, "r") as tf:
                        tf.extractall(path=imgfolder)
                except: 
                    logger.error("Couln't open {}".format(tarimgfile))
        zoom_exists = 1
    else:
        zoom_exists = 0
        zoom_filename = None
    transcription_text = ""
    
    return render_template('file.html',
                           zoom_exists=zoom_exists, zoom_filename=zoom_filename, folder_info=folder_info,
                           file_details=file_details, file_checks=file_checks, 
                           file_postprocessing=file_postprocessing, username=user_name, image_url=image_url,
                           is_admin=is_admin, project_alias=project_alias,
                           tables=[file_metadata.to_html(table_id='file_metadata', index=False, border=0,
                                                         escape=False,
                                                         classes=["display", "compact", "table-striped"])],
                           file_metadata_rows=file_metadata.shape[0],
                           file_links=file_links, file_sensitive=str(file_sensitive),
                           
                           sensitive_info=sensitive_info, form=form, site_env=site_env,
                           site_net=site_net, site_ver=site_ver, kiosk=kiosk, user_address=user_address,
                           analytics_code=settings.analytics_code)



@app.route('/file_transcription/<file_id>/', methods=['GET'], provide_automatic_options=False)
def file_transcription(file_id=None):
    """File details from a transcription project"""
    
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

    file_id_check = check_file_id_transcription(file_id)
    if file_id_check is None:
        error_msg = "File ID is missing."
        return render_template('error.html', error_msg=error_msg, project_alias=None, site_env=site_env, site_net=site_net, site_ver=site_ver), 400

    folder_info = run_query("""SELECT * FROM transcription_folders WHERE folder_transcription_id IN 
                                    (SELECT folder_transcription_id as folder_id FROM transcription_files WHERE file_transcription_id = %(file_id)s)""",
                            {'file_id': file_id})
    if len(folder_info) == 0:
        error_msg = "Invalid File ID."
        return render_template('error.html', error_msg=error_msg, project_alias=None, site_env=site_env, site_net=site_net, site_ver=site_ver), 400
    else:
        folder_info = folder_info[0]

    #Transcription project?
    transcription = run_query(("SELECT transcription FROM projects WHERE project_id = %(project_id)s"), {'project_id': folder_info['project_id']})[0]
    transcription = int(transcription['transcription'])

    if transcription != 1:
        error_msg = "File ID error."
        return render_template('error.html', error_msg=error_msg, project_alias=None, site_env=site_env, site_net=site_net, site_ver=site_ver), 400
    
    tables = {}
    i = 0
    t_sources = run_query("SELECT transcription_source_id, transcription_source_name, CONCAT(transcription_source_notes, ' ', transcription_source_date) as source_notes FROM transcription_sources WHERE project_id = %(project_id)s", {'project_id': folder_info['project_id']})
    for t_source in t_sources:
        transcription_text = pd.DataFrame(run_query(("""
                                    SELECT fields.field_name as field, COALESCE(t.transcription_text, '') as value 
                                        FROM transcription_fields fields LEFT JOIN transcription_files_text t ON (fields.field_id = t.field_id) 
                                        WHERE fields.transcription_source_id = %(source_id)s
                                                     and t.file_transcription_id = %(file_id)s
                                        ORDER BY fields.sort_by
                                        """), {'source_id': t_source['transcription_source_id'], 'file_id': file_id}))
        tables[i] = {'name': t_source['transcription_source_name'],
                        'table': transcription_text.to_html(table_id='transcription_text', index=False, border=0,
                                                            escape=True,
                                                            classes=["display", "compact", "table-striped"]),
                        'source_info': t_source['source_notes']}
        i += 1
        
    # file_details = run_query(("SELECT *, DATEDIFF(created_at, NOW()) as datediff FROM transcription_files WHERE file_transcription_id = %(file_id)s"),
    #                {'file_id': file_id})[0]
    file_details = run_query(("WITH data AS ("
                                "         SELECT file_transcription_id, "
                                "             folder_transcription_id, file_name, dams_uan, "
                                "             date_format(created_at, '%Y-%b-%d %T') as created_at, DATEDIFF(NOW(), created_at) as datediff "
                                "             FROM transcription_files "
                                "                 WHERE folder_transcription_id = %(folder_id)s AND folder_transcription_id IN (SELECT folder_transcription_id FROM transcription_folders)"
                                " UNION "
                                "         SELECT file_transcription_id,  "
                                "                folder_transcription_id, file_name, dams_uan, "
                                "             date_format(created_at, '%Y-%b-%d %T') as created_at, DATEDIFF(created_at, NOW()) as datediff "
                                "             FROM transcription_files "
                                "                 WHERE folder_transcription_id = %(folder_id)s AND folder_transcription_id NOT IN (SELECT folder_transcription_id FROM transcription_folders)"
                                "             ORDER BY file_name"
                                "),"
                                "data2 AS (SELECT file_transcription_id, folder_transcription_id, file_name, dams_uan, created_at, datediff, "
                                "         lag(file_transcription_id,1) over (order by file_name) prev_id,"
                                "         lead(file_transcription_id,1) over (order by file_name) next_id "
                                " FROM data)"
                                " SELECT "
                                " file_transcription_id as file_id, "
                                "     folder_transcription_id, file_name, dams_uan, prev_id, next_id, created_at, datediff "
                                " FROM data2 WHERE file_transcription_id = %(file_id)s LIMIT 1"),
                                {'folder_id': folder_info['folder_transcription_id'], 'file_id': file_id,
                                'preview': '/preview_image/'})[0]
    
    project_alias = run_query(("SELECT COALESCE(project_alias, CAST(project_id AS char)) as project_id FROM projects "
                    " WHERE project_id = %(project_id)s"),
                   {'project_id': folder_info['project_id']})[0]
    project_alias = project_alias['project_id']

    file_checks = run_query(("SELECT file_check, check_results, CASE WHEN check_info = '' THEN 'Check passed.' "
                                  " ELSE check_info END AS check_info "
                                  " FROM transcription_files_checks WHERE file_transcription_id = %(file_id)s"),
                                 {'file_id': file_id})
    image_url = '/preview_image/' + str(file_id)
    
    file_links = run_query("SELECT link_name, link_url, link_aria FROM files_links WHERE file_id = %(file_id)s ",
                                {'file_id': file_id})
    
    if current_user.is_authenticated:
        user_name = current_user.name
        is_admin = user_perms('', user_type='admin')
    else:
        user_name = ""
        is_admin = False
    logger.info("project_alias: {}".format(project_alias))

    # kiosk mode
    kiosk, user_address = kiosk_mode(request, settings.kiosks)

    # New direct link to image
    preview_img_path = "image_previews/{}/{}/{}.jpg".format(file_details['folder_transcription_id'], "160", file_id)
    if os.path.isfile("static/{}".format(preview_img_path)):
        file_details['preview_img_path'] = preview_img_path
    else:
        file_details['preview_img_path'] = "na_{}.png".format("160")

    # DZI zoomable image
    zoom_filename = '../../static/image_previews/{}/{}.dzi'.format(file_details['folder_transcription_id'], file_id)
    print(os.path.isfile('static/image_previews/{}/{}.dzi'.format(file_details['folder_transcription_id'], file_id)))
    if os.path.isfile('static/image_previews/{}/{}.dzi'.format(file_details['folder_transcription_id'], file_id)):
        tarimgfile = "static/image_previews/{}/{}_files.tar".format(file_details['folder_transcription_id'], file_id)
        imgfolder = "static/image_previews/{}/".format(file_details['folder_transcription_id'])
        if os.path.isfile(tarimgfile):
            if os.path.isdir("static/image_previews/{}/{}_files".format(file_details['folder_transcription_id'], file_id)) is False:
                try:
                    with tarfile.open(tarimgfile, "r") as tf:
                        tf.extractall(path=imgfolder)
                except: 
                    logger.error("Couln't open {}".format(tarimgfile))
        zoom_exists = 1
    else:
        zoom_exists = 0
        zoom_filename = None
    
    return render_template('file_transcription.html',
                           folder_info=folder_info, zoom_exists=zoom_exists, zoom_filename=zoom_filename,
                           file_details=file_details, file_checks=file_checks, username=user_name, image_url=image_url,                            
                           is_admin=is_admin, project_alias=project_alias, file_links=file_links, 
                           transcription=transcription, tables=tables,
                           form=form, site_env=site_env,
                           site_net=site_net, site_ver=site_ver, kiosk=kiosk, analytics_code=settings.analytics_code)


@app.route('/file/', methods=['GET'], provide_automatic_options=False)
def file_empty():
    return redirect(url_for('homepage'))


@app.route('/file_transcription/', methods=['GET'], provide_automatic_options=False)
def file_t_empty():
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
                                  {'project_alias': project_alias})[0]
    if q is None:
        error_msg = "No search query was submitted."
        # cur.close()
        # conn.close()
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
                                      'q': '%' + q + '%'})
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
                                      'q': '%' + q + '%'})

    # kiosk mode
    kiosk, user_address = kiosk_mode(request, settings.kiosks)

    return render_template('search_files.html',
                           results=results, project_info=project_info, project_alias=project_alias,
                           q=q, form=form, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           kiosk=kiosk, user_address=user_address, analytics_code=settings.analytics_code)


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
    
    q = request.values.get('q')
    page = request.values.get('page')
    if page is None:
        page = 0
    offset = page * 50
    project_info = run_query("SELECT * FROM projects WHERE project_alias = %(project_alias)s",
                                  {'project_alias': project_alias})[0]
    if q is None:
        error_msg = "No search query was submitted."
        # cur.close()
        # conn.close()
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
                                  'q': '%' + q + '%'})
    results_df = pd.DataFrame({'folder': [], 'no_files': []})
    for row in results:
        results_df.loc[len(results_df.index)] = ['<a href="{}/dashboard/'.format(settings.app_root) + project_alias \
                                                 + '/' \
                                                 + str(row['folder_id']) \
                                                 + '/" title="Folder Details">' \
                                                 + row['project_folder'] \
                                                 + '</a> ', str(row['no_files'])]

    # kiosk mode
    kiosk, user_address = kiosk_mode(request, settings.kiosks)

    return render_template('search_folders.html',
                           tables=[results_df.to_html(table_id='results',
                                                      index=False,
                                                      border=0,
                                                      escape=False,
                                                      classes=["display", "compact", "table-striped"])],
                           project_info=project_info, project_alias=project_alias, q=q,
                           form=form, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           kiosk=kiosk, user_address=user_address, analytics_code=settings.analytics_code)


@app.route('/folder_update/<project_alias>/<folder_id>', methods=['GET'], provide_automatic_options=False)
@login_required
def update_folder_dams(project_alias=None, folder_id=None):
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
    if folder_id is None or project_alias is None:
        return redirect(url_for('home'))

    """Update folder when sending to DAMS"""
    
    # Set as in the way to DAMS
    damsupdate = query_database_insert(
        ("UPDATE folders SET delivered_to_dams = 1 WHERE folder_id = %(folder_id)s"),
        {'folder_id': folder_id})
        
    # Del DAMS status badge, if exists
    delbadge = query_database_insert(
            ("DELETE FROM folders_badges WHERE folder_id = %(folder_id)s AND badge_type = 'dams_status'"),
                {'folder_id': folder_id})

    # Set as Ready for DAMS
    delbadge = query_database_insert(
            ("INSERT INTO folders_badges (folder_id, badge_type, badge_css, badge_text) "
             " VALUES (%(folder_id)s, 'dams_status', 'bg-secondary', 'Ready for DAMS')"),
                {'folder_id': folder_id})

    # Update post-proc
    delbadge = query_database_insert(
            ("""
                INSERT INTO file_postprocessing
                    (file_id, post_results, post_step)
                (
                    SELECT file_id, 0 as post_results, 'ready_for_dams' as post_step
                    FROM (SELECT file_id FROM files WHERE folder_id = %(folder_id)s) a
                ) ON
                DUPLICATE KEY UPDATE
                post_results = 0
            """),
                {'folder_id': folder_id})

    # Update DAMS UAN
    delbadge = query_database_insert(
            ("""
                UPDATE files f,
                (
                    SELECT f.file_id, d.dams_uan
                    FROM
                        dams_cdis_file_status_view_dpo d, files f, folders fold, projects p
                    WHERE
                        fold.folder_id = f.folder_id AND
                        fold.project_id = p.project_id AND
                        d.project_cd = p.dams_project_cd AND
                        d.file_name = CONCAT(f.file_name, '.tif') AND
                        f.folder_id =   %(folder_id)s
                ) d
                SET f.dams_uan = d.dams_uan WHERE f.file_id = d.file_id
            """),
                {'folder_id': folder_id})

    # Update in DAMS
    damsupdate = query_database_insert(
            ("""
                INSERT INTO file_postprocessing
                    (file_id, post_results, post_step)
                (
                    SELECT
                         file_id, 0 as post_results, 'in_dams' as post_step
                    FROM
                     (
                     SELECT file_id FROM files
                     WHERE folder_id = %(folder_id)s AND 
                        dams_uan != '' AND dams_uan IS NOT NULL
                     ) a
                ) ON DUPLICATE KEY UPDATE post_results = 0
            """),
                {'folder_id': folder_id})

    no_files_ready = run_query(
        ("SELECT COUNT(*) as no_files FROM files WHERE folder_id = %(folder_id)s AND dams_uan != '' AND dams_uan IS NOT NULL"),
        {'folder_id': folder_id})

    no_files_pending = run_query(
        ("SELECT COUNT(*) as no_files FROM files WHERE folder_id = %(folder_id)s AND (dams_uan = '' OR dams_uan IS NULL)"),
        {'folder_id': folder_id})

    if no_files_ready[0]['no_files'] > 0 and no_files_pending[0]['no_files'] == 0:
        # Update in DAMS
        damsupdate = query_database_insert(
            ("UPDATE folders SET delivered_to_dams = 0 WHERE folder_id = %(folder_id)s"),
            {'folder_id': folder_id})
        damsupdate = query_database_insert(
            ("DELETE FROM folders_badges WHERE folder_id = %(folder_id)s AND badge_type = 'dams_status'"),
            {'folder_id': folder_id})
        damsupdate = query_database_insert(
            ("""
                INSERT INTO folders_badges 
                    (folder_id, badge_type, badge_css, badge_text) VALUES 
                    (%(folder_id)s, 'dams_status', 'bg-success', 'Delivered to DAMS')
            """), {'folder_id': folder_id})
    return redirect(url_for('dashboard_f', project_alias=project_alias, folder_id=folder_id))


@app.route('/update_image/', methods=['POST'], provide_automatic_options=False)
@login_required
def update_image():
    """Update image as having sensitive contents"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
        user_id = current_user.id
    else:
        return redirect(url_for('homepage'))

    file_id = int(request.form['file_id'])
    sensitive_info = request.form['sensitive_info']

    update = query_database_insert(
        ("INSERT INTO sensitive_contents (file_id, sensitive_contents, sensitive_info, user_id) VALUES (%(file_id)s, 1, %(sensitive_info)s, %(user_id)s) ON DUPLICATE KEY UPDATE sensitive_contents = 1"),
            {'file_id': file_id, 'sensitive_info': sensitive_info, 'user_id': current_user.id})

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



@app.route('/reports/<project_alias>/<report_id>/', methods=['GET'], provide_automatic_options=False)
def data_reports(project_alias=None, report_id=None):
    """Report of a project"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    
    # Declare the login form
    form = LoginForm(request.form)

    if project_alias is None:
        error_msg = "Project is not available."
        return render_template('error.html', error_msg=error_msg, project_alias=None, site_env=site_env, site_net=site_net), 404

    # Declare the login form
    form = LoginForm(request.form)

    project_id = run_query(("SELECT project_id FROM projects WHERE project_alias = %(project_alias)s"),
                                {'project_alias': project_alias})

    if len(project_id) == 0:
        error_msg = "Project was not found."
        return render_template('error.html', error_msg=error_msg, project_alias=project_id,
                               site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404

    project_id = project_id[0]['project_id']
    project_report = run_query(("SELECT *, date_format(updated_at, '%Y-%b-%d %T') as updated_at_f FROM data_reports WHERE "
                                     " project_id = %(project_id)s AND report_id = %(report_id)s"),
                                    {'project_id': project_id, 'report_id': report_id})
    if len(project_report) == 0:
        error_msg = "Report was not found."
        return render_template('error.html', error_msg=error_msg, project_alias=project_alias,
                               site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404

    report_data_updated = run_query(project_report[0]['query_updated'])[0]['updated_at']

    if project_report[0]['pregenerated'] == 1:
        # Delete old versions
        files_todel = glob.glob("static/reports/{}_*.csv".format(project_report[0]['pregen_filename']))
        for file in files_todel:
            try:
                os.remove(file)
            except FileNotFoundError:
                continue
        files_todel = glob.glob("static/reports/{}_*.xlsx".format(project_report[0]['pregen_filename']))
        for file in files_todel:
            try:
                os.remove(file)
            except FileNotFoundError:
                continue
        rep_timestamp = localtime()
        current_datetime = strftime("%Y%m%d_%H%M%S", rep_timestamp)
        current_datetime_formatted = strftime("%Y-%m-%d %H:%M:%S", rep_timestamp)
        report_data = pd.DataFrame(run_query(project_report[0]['query']))
        # CSV
        data_file = "reports/{}_{}.csv".format(project_report[0]['pregen_filename'], current_datetime)
        report_data.to_csv("static/{}".format(data_file), index=False)
        # Excel
        data_file_e = "reports/{}_{}.xlsx".format(project_report[0]['pregen_filename'], current_datetime)
        report_data.to_excel("static/{}".format(data_file_e))      
        pregenerated = 1
    else:
        report_data = pd.DataFrame(run_query(project_report[0]['query']))
        data_file = ""
        data_file_e = ""
        current_datetime_formatted = ""
        pregenerated = 0
    project_info = run_query("SELECT * FROM projects WHERE project_id = %(project_id)s",
                                  {'project_id': project_id})[0]

    return render_template('reports.html',
                           project_id=project_id, project_alias=project_alias, project_info=project_info,
                           report=project_report[0],
                           tables=[report_data.to_html(table_id='report_data',
                                                       index=False,
                                                       border=0,
                                                       escape=False,
                                                       classes=["display", "compact", "table-striped"])],
                           data_file_e=data_file_e, report_data_updated=report_data_updated, form=form,
                           data_file=data_file, pregenerated=pregenerated, report_date=current_datetime_formatted, 
                           site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code)


@cache.memoize()
@app.route('/preview_image/<file_id>', methods=['GET'], provide_automatic_options=False)
@app.route('/preview_image/<file_id>/<max>', methods=['GET'], provide_automatic_options=False)
def get_preview(file_id=None, max=None, sensitive=None):
    """Return image previews"""
    if file_id is None:
        raise InvalidUsage('file_id missing', status_code=400)
    try:
        file_id = int(file_id)
    except:
        try:
            # Allow for UUIDs
            file_id = UUID(file_id)
        except:
            raise InvalidUsage('invalid file_id value', status_code=400)
    
    data = run_query("SELECT folder_id, file_name FROM files WHERE file_id = %(file_id)s LIMIT 1", {'file_id': file_id})
    logger.info(data)
    if max is None:
        max = request.args.get('max')
    dl = request.args.get('dl')
    
    if len(data) == 0:
        if max in ["160", "200", "600", "1200"]:
            filename = "static/na_{}.png".format(max)
        else:
            filename = "static/na.jpg"
        return send_file(filename, mimetype='image/jpeg')
    else:
        if max == "160":
            folder_id = data[0]['folder_id']
            filename = "static/image_previews/folder{}/160/{}.jpg".format(folder_id, file_id)
            if os.path.isfile(filename):
                logger.info("preview_160: {}".format(filename))
                if dl == "1":
                    dl_filename = Path(filename).stem
                    return send_file(filename, mimetype='image/jpeg', download_name=dl_filename, as_attachment=True)
                else:
                    try:
                        return send_file(filename, mimetype='image/jpeg')
                    except:
                        return send_file("static/na_160.jpg", mimetype='image/jpeg')
        try:
            folder_id = data[0]['folder_id']
            if max is not None:
                width = max
            else:
                width = None
            filename = "static/image_previews/folder{}/{}.jpg".format(folder_id, file_id)
            img = Image.open(filename)
            wsize, hsize = img.size
            if width is not None:
                if os.path.isfile(filename):
                    img_resized = "static/image_previews/folder{}/{}/{}.jpg".format(folder_id, width, file_id)
                    if os.path.isfile(img_resized):
                        filename = img_resized
                    else:
                        logger.info(filename)
                        # img = Image.open(filename)
                        wpercent = (int(width) / float(img.size[0]))
                        hsize = int((float(img.size[1]) * float(wpercent)))
                        img = img.resize((int(width), hsize), Image.LANCZOS)
                        filename = "/tmp/{}_{}.jpg".format(file_id, width)
                        img.save(filename, icc_profile=img.info.get('icc_profile'))
                else:
                    logger.info(filename)
                    if width in ["160", "200", "600", "1200"]:
                        filename = "static/na_{}.png".format(width)
                    else:
                        filename = "static/na.jpg"
        except:
            if max in ["160", "200", "600", "1200"]:
                filename = "static/na_{}.png".format(max)
            else:
                filename = "static/na.jpg"
    if not os.path.isfile(filename):
        if max in ["160", "200", "600", "1200"]:
            filename = "static/na_{}.png".format(max)
        else:
            filename = "static/na.jpg"
    logger.debug("preview_request: {} - {}".format(file_id, filename))
    
    # Check for sensitive contents
    img = run_query("SELECT * FROM sensitive_contents WHERE file_id = %(file_id)s", {'file_id': file_id})
    if len(img) == 0:
        img_sen = 0
    else:
        try:
            img_sen = img[0]['sensitive_contents']
        except:
            img_sen = 0
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
            if max in ["160", "200", "600", "1200"]:
                filename = "static/na_{}.png".format(max)
            else:
                filename = "static/na.jpg"
    if dl == "1":
        dl_filename = "{}.jpg".format(Path(data[0]['file_name']).stem)
        return send_file(filename, mimetype='image/jpeg', download_name=dl_filename, as_attachment=True)
    else:
        try:
            return send_file(filename, mimetype='image/jpeg')
        except:
            return send_file("static/na.jpg", mimetype='image/jpeg')


@cache.memoize()
@app.route('/fullsize/<file_id>/', methods=['GET', 'POST'], provide_automatic_options=False)
def get_fullsize(file_id=None):
    """Return the fullsize image, adjusted to 100%"""
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api_route_list'))
    if file_id is None:
        raise InvalidUsage('file_id missing', status_code=400)
    try:
        file_id = int(file_id)
    except:
        try:
            # Allow for UUIDs
            file_id = UUID(file_id)
        except:
            raise InvalidUsage('invalid file_id value', status_code=400)
    # Get DPR - https://github.com/Smithsonian/Osprey/issues/64
    try:
        dpr = request.headers.get('Sec-CH-DPR')
        logger.info("DPR: {}".format(dpr))
    except:
        dpr = None
        logger.warning("DPR could not be determined")
    # Hard code fix for Firefox/Safari, assume 1.5
    if dpr is None:
        dpr = 1.5

    data = run_query("SELECT file_name, folder_id FROM files WHERE file_id = %(file_id)s LIMIT 1", {'file_id': file_id})
    logger.info(data)
    if len(data) == 0:
        filename = "static/na.jpg"
    else:
        try:
            folder_id = data[0]['folder_id']
            file_name = data[0]['file_name']
            filename = "static/image_previews/folder{}/{}.jpg".format(folder_id, file_id)
            img = Image.open(filename)
            wsize, hsize = img.size
            wsize_o = wsize
            hsize_o = hsize
        except:
            filename = "static/na.jpg"
            file_name = "NA"
            img = Image.open(filename)
            wsize, hsize = img.size 
            wsize_o = wsize
            hsize_o = hsize
    if dpr is not None:
        wsize = int((wsize*1.0)/float(dpr))
        hsize = int((hsize*1.0)/float(dpr))
    if not os.path.isfile(filename):
        filename = "static/na.jpg"
        file_name = "NA"
        img = Image.open(filename)
        wsize, hsize = img.size 
        wsize_o = wsize
        hsize_o = hsize
    logger.debug("fullsize_request: {} - {}".format(file_id, filename))
    return render_template('fullsize.html',
                           file_id=file_id, filename=filename, file_title=file_name,
                           wsize=wsize, hsize=hsize, wsize_o=wsize_o, hsize_o=hsize_o)


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

    if barcode_split[0] == 'nmnhbot':
        query = ("SELECT file_id, folder_id, preview_image FROM files "
                 "WHERE file_name = %(file_name)s AND folder_id IN "
                 "(SELECT folder_id FROM folders WHERE project_id in(100,131)) LIMIT 1")
        data = run_query(query, {'file_name': barcode_split[1]})
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
                        img.save(filename, icc_profile=img.info.get('icc_profile'))
                    else:
                        filename = "static/na.jpg"
        if not os.path.isfile(filename):
            logger.info(filename)
            filename = "static/na.jpg"
    logger.debug("barcode_request: {} - {}".format(barcode, filename))
    try:
        return send_file(filename, mimetype='image/jpeg')
    except:
        return send_file("static/na.jpg", mimetype='image/jpeg')


#####################################
if __name__ == '__main__':
    if site_env == "dev":
        app.run(threaded=False, debug=True)
    else:
        app.run(threaded=False, debug=False)
