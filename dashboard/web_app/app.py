#!flask/bin/python
#
# DPO Dashboard
#
# Import flask
from flask import Flask
from flask import render_template
from flask import request
from flask import jsonify
from flask import redirect
from flask import url_for

# caching
from flask_caching import Cache

import logging
import locale
import os
import math
import pandas as pd
import json
import time

import psycopg2
import psycopg2.extras
import psycopg2.extensions

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

# Plotly
import plotly
import plotly.express as px

import settings

site_ver = "2.2.1"

cur_path = os.path.abspath(os.getcwd())

# Logging
current_time = time.strftime("%Y%m%d_%H%M%S", time.localtime())
logging.basicConfig(filename='app_{}.log'.format(current_time),
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

# Cache config
config = {
    "DEBUG": True,  # some Flask specific configs
    "CACHE_TYPE": "FileSystemCache",  # Flask-Caching related configs
    "CACHE_DIR": "{}/cache".format(os.getcwd()),
    "CACHE_DEFAULT_TIMEOUT": 600
}
app = Flask(__name__)
app.secret_key = settings.secret_key
app.config.from_mapping(config)
cache = Cache(app)


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
    return render_template('error.html', form=form, error_msg=error_msg, project_alias=None), 404


@app.errorhandler(500)
def sys_error(e):
    logging.error(e)
    error_msg = "System error: {}".format(e)
    # Declare the login form
    form = LoginForm(request.form)
    return render_template('error.html', form=form, error_msg=error_msg, project_alias=None), 500


# Database
try:
    conn = psycopg2.connect(host=settings.host,
                            database=settings.database,
                            user=settings.user,
                            password=settings.password)
    conn.autocommit = True
except psycopg2.Error as e:
    logging.error(e)
    raise InvalidUsage('System error')


def query_database(query, parameters=""):
    logging.info("parameters: {}".format(parameters))
    logging.info("query: {}".format(query))
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    except Exception as error:
        logging.error("Error: {}".format(error))
        logging.error("cur.query: {}".format(cur.query))
        # Declare the login form
        form = LoginForm(request.form)
        return render_template('error.html', form=form, error_msg="System error", project_alias=None), 500
        # raise InvalidUsage('System error', status_code=500)
    cur.execute('SET statement_timeout = 5000')
    cur.execute("SET CLIENT_ENCODING TO 'utf-8'")
    # Run query
    try:
        cur.execute(query, parameters)
        logging.info("cur.query: {}".format(cur.query))
    except Exception as error:
        logging.error("Error: {}".format(error))
        logging.error("cur.query: {}".format(cur.query))
        # raise InvalidUsage('System error', status_code=500)
        # Declare the login form
        form = LoginForm(request.form)
        return render_template('error.html', form=form, error_msg="System error", project_alias=None), 500
    logging.info(cur.rowcount)
    if cur.rowcount == -1:
        data = None
    else:
        data = cur.fetchall()
    cur.close()
    return data


def query_database_2(query, parameters=""):
    logging.info("parameters: {}".format(parameters))
    logging.info("query: {}".format(query))
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('SET statement_timeout = 5000')
    cur.execute("SET CLIENT_ENCODING TO 'utf-8'")
    # Run query
    try:
        cur.execute(query, parameters)
        logging.info("cur.query: {}".format(cur.query))
    except Exception as error:
        logging.error("cur.query: {}".format(cur.query))
        # raise InvalidUsage('System error', status_code=500)
        # Declare the login form
        form = LoginForm(request.form)
        return render_template('error.html', form=form, error_msg="System error", project_alias=None), 500
    logging.info(cur.rowcount)
    if cur.rowcount == -1:
        cur.close()
        return False
    else:
        cur.close()
        return True


def user_perms(project_id, user_type='user'):
    try:
        user_name = current_user.name
    except:
        return False
    if user_type == 'user':
        is_user = query_database("SELECT COUNT(*) as is_user "
                                 "  FROM qc_projects p, qc_users u "
                                 "  WHERE p.user_id = u.user_id "
                                 "      AND p.project_id = %(project_id)s "
                                 "      AND u.username = %(user_name)s",
                         {'project_id': project_id, 'user_name': user_name})
        return is_user[0]['is_user'] == 1
    if user_type == 'admin':
        is_admin = query_database("SELECT is_admin FROM qc_users WHERE username = %(user_name)s",
                                 {'user_name': user_name})
        return is_admin[0]['is_admin'] == 1
    else:
        return False


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
        user = query_database("SELECT user_active FROM qc_users WHERE username = %(username)s",
                              {'username': name})
        return user

    def is_anonymous(self):
        return False

    def is_authenticated(self):
        return True


@login_manager.user_loader
def load_user(username):
    u = query_database("SELECT username, user_id, user_active, full_name "
                       "    FROM qc_users "
                       "    WHERE username = %(username)s",
                        {'username': username})
    if u is None:
        return User(None, None, None, False)
    else:
        return User(u[0]['username'], u[0]['user_id'], u[0]['full_name'], u[0]['user_active'])


###################################
# System routes
###################################
@cache.memoize()
@app.route('/', methods=['GET', 'POST'])
def login():
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

    # check if both http method is POST and form is valid on submit
    if form.validate_on_submit():

        # assign form data to variables
        username = request.form.get('username', '', type=str)
        password = request.form.get('password', '', type=str)
        user = query_database("SELECT user_id, username, user_active, full_name "
                              "     FROM qc_users "
                              "     WHERE username = %(username)s AND pass = MD5(%(password)s)",
                              {'username': username, 'password': password})
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
                msg = "Error, user not known or password was incorrect"
                return redirect(url_for('not_user'))
        else:
            msg = "Error, user not known or password was incorrect"
            return redirect(url_for('not_user'))
    projects = query_database("select project_title, project_id, filecheck_link, project_alias, "
                              "     to_char(project_start, 'Mon-YYYY') as project_start, "
                              "     to_char(project_end, 'Mon-YYYY') as project_end,"
                              "     project_unit "
                              " FROM projects where project_alias is not null "
                              " ORDER BY projects_order DESC")

    # Summary table
    df = pd.DataFrame(query_database("with d as ("
                        "select date, sum(images_captured) as images_captured, sum(objects_digitized) as objects_digitized  from projects_stats_detail where time_interval ='monthly' group by date)"
                    "select "
                          " to_char(d1.date, 'Mon YYYY') as Date, "
                          " to_char(sum(d1.images_captured) over (order by d1.date asc rows between unbounded preceding and current row), 'FM9,999,999,999') as Images, "
                          " to_char(sum(d2.objects_digitized) over (order by d2.date asc rows between unbounded preceding and current row), 'FM9,999,999,999') as Objects "
                        " from d d1, d d2 "
                     "      WHERE d1.date = d2.date "
                        " order by d1.date DESC "
                     ))

    summary_datatable = pd.DataFrame(df)
    columns = summary_datatable.columns
    summary_datatable.columns = [x.title() for x in columns]

    # Summary chart
    df = pd.DataFrame(query_database("with d as ("
                        "select date, sum(images_captured) as images_captured, sum(objects_digitized) as objects_digitized  from projects_stats_detail where time_interval ='monthly' group by date)"
                    "select "
                          " date, 'Images' as itype, "
                          " sum(images_captured) over (order by date asc rows between unbounded preceding and current row)  as no_images "
                        " from d "
                        " union "
                        " select date,"
                          "'Objects' as itype,"
                          "sum(objects_digitized) over (order by date asc rows between unbounded preceding and current row) as no_images "
                        " from d "
                        " order by date "
                     ))

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
    summary_stats = {}
    summary_stats['objects_digitized'] = "{:,}".format(query_database("SELECT SUM(objects_digitized) as total from projects_stats where project_id NOT IN (SELECT project_id FROM projects WHERE skip_project IS True)")[0]['total'])
    summary_stats['images_captured'] = "{:,}".format(query_database("SELECT SUM(images_taken) as total from projects_stats where project_id NOT IN (SELECT project_id FROM projects WHERE skip_project IS True)")[0]['total'])
    summary_stats['digitization_projects'] = "{:,}".format(query_database("SELECT COUNT(*) as total FROM projects WHERE skip_project IS NOT True")[0]['total'])
    summary_stats['active_projects'] = "{:,}".format(query_database("SELECT COUNT(*) as total FROM projects WHERE skip_project IS NOT True AND project_status='Ongoing'")[0]['total'])
    summary_stats['images_public'] = "{:,}".format(query_database("SELECT SUM(images_public) as total FROM projects_stats WHERE project_id NOT IN (SELECT project_id FROM projects WHERE skip_project IS True)")[0]['total'])

    # MD stats
    md_stats = {}
    md_stats['objects_digitized'] = "{:,}".format(query_database(
            "SELECT SUM(objects_digitized) as total "
            "from projects_stats "
            "where project_id IN "
            "   (SELECT project_id FROM projects WHERE project_section = 'MD' AND skip_project IS NOT True)"
                )[0]['total'])
    md_stats['images_captured'] = "{:,}".format(query_database(
            "SELECT SUM(images_taken) as total "
            "from projects_stats "
            "WHERE project_id IN "
            "   (SELECT project_id FROM projects WHERE project_section = 'MD' AND skip_project IS NOT True)"
                )[0]['total'])
    md_stats['digitization_projects'] = "{:,}".format(query_database(
           "SELECT COUNT(*) as total "
           "FROM projects "
           "WHERE project_section = 'MD' AND"
           " skip_project IS NOT True")[0]['total'])
    md_stats['active_projects'] = "{:,}".format(query_database(
            "SELECT COUNT(*) as total "
            "FROM projects "
            "WHERE project_section = 'MD' AND"
            " skip_project IS NOT True AND"
            " project_status='Ongoing'")[0]['total'])
    md_stats['images_public'] = "{:,}".format(query_database(
            "SELECT SUM(images_public) as total FROM projects_stats WHERE project_id IN (SELECT project_id FROM projects WHERE skip_project IS NOT True AND project_section = 'MD')")[0]['total'])

    # IS stats
    is_stats = {}
    is_stats['objects_digitized'] = "{:,}".format(query_database(
            "SELECT SUM(objects_digitized) as total "
            "from projects_stats "
            "where project_id IN "
            "   (SELECT project_id FROM projects WHERE project_section = 'IS' AND skip_project IS NOT True)"
    )[0]['total'])
    is_stats['images_captured'] = "{:,}".format(query_database(
            "SELECT SUM(images_taken) as total "
            "from projects_stats "
            "where project_id IN "
            "   (SELECT project_id FROM projects WHERE project_section = 'IS' AND skip_project IS NOT True)"
    )[0]['total'])
    is_stats['digitization_projects'] = "{:,}".format(
        query_database(
            "SELECT COUNT(*) as total "
            "FROM projects "
            "WHERE project_section = 'IS' AND"
            " skip_project IS NOT True")[0]['total'])
    is_stats['active_projects'] = "{:,}".format(query_database(
            "SELECT COUNT(*) as total "
            "FROM projects "
            "WHERE project_section = 'IS' AND"
            " skip_project IS NOT True AND"
            " project_status='Ongoing'")[0]['total'])
    is_stats['images_public'] = "{:,}".format(query_database(
            "SELECT SUM(images_public) as total"
            " FROM projects_stats "
            " WHERE project_id IN "
            "   (SELECT project_id FROM projects WHERE skip_project IS NOT True AND project_section = 'IS')")[0]['total'])

    list_projects_md = pd.DataFrame(query_database(
               " SELECT " 
               " p.projects_order, p.project_unit, "
                        " CASE WHEN p.project_alias IS NULL THEN p.project_title ELSE '<a href=\"/dashboard/' || p.project_alias || '\">' || p.project_title || '</a>' END as project_title, "
               " p.project_status, "
               " p.project_manager, "
                               " CASE WHEN to_char(p.project_start, 'YYYY-MM') = to_char(p.project_end, 'YYYY-MM') THEN "
                               "    to_char(p.project_start, 'DD') || '-' || to_char(p.project_end, 'DD Mon YYYY') "
               "                    WHEN p.project_end IS NULL THEN to_char(p.project_start, 'DD Mon YYYY') "
                               "    ELSE to_char(p.project_start, 'DD Mon YYYY') || ' to ' || to_char(p.project_end, 'DD Mon YYYY') END"
                               "         as project_dates, "
               " '<div class=\"progress\" style=\"height: 20px;\"><div class=\"progress-bar\" role=\"progressbar\" aria-label=\"Progress of the project\" style=\"width: ' "
                               " || coalesce(round((ps.objects_digitized::numeric/ps.collex_to_digitize::numeric) * 100, 2), 0)  ||"
                               " '%%;\" aria-valuenow=\"'"
                               " || coalesce(round((ps.objects_digitized::numeric/ps.collex_to_digitize::numeric) * 100, 2), 0)  ||"
                               " '\" aria-valuemin=\"0\" aria-valuemax=\"100\">'"
                               " || coalesce(round((ps.objects_digitized::numeric/ps.collex_to_digitize::numeric) * 100, 2), 0)  ||"
                               "'%%</div></div>' as project_progress,"
               " CASE WHEN p.objects_estimated IS True THEN coalesce(to_char(ps.objects_digitized, 'FM9,999,999,999'), 0::text) || '**' ELSE "
                                    " coalesce(to_char(ps.objects_digitized, 'FM9,999,999,999'), 0::text) END as objects_digitized, "
               " CASE WHEN p.images_estimated IS True THEN coalesce(to_char(ps.images_taken, 'FM9,999,999,999'), 0::text) || '**' ELSE coalesce(to_char(ps.images_taken, 'FM9,999,999,999'), 0::text) END as images_taken, "
               " CASE WHEN p.images_estimated IS True THEN coalesce(to_char(ps.images_public, 'FM9,999,999,999'), 0::text) || '**' ELSE coalesce(to_char(ps.images_public, 'FM9,999,999,999'), 0::text) END as images_public "
               " FROM projects p LEFT JOIN projects_stats ps ON (p.project_id = ps.project_id) "
               " WHERE p.skip_project IS NOT True AND p.project_section = 'MD' "
               " GROUP BY "
               "        p.project_id, p.project_title, p.project_unit, p.project_acronym, p.project_status, p.project_description, "
               "        p.project_method, p.project_manager, p.project_url, p.project_start, p.project_end, p.updated_at, p.projects_order, p.project_type, "
               "        ps.collex_to_digitize, p.images_estimated, p.objects_estimated, ps.images_taken, ps.objects_digitized, ps.images_public"
               " ORDER BY p.projects_order DESC"))

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
    logging.info(list_projects_md)
    list_projects_is = pd.DataFrame(query_database(
               "SELECT "
               " p.projects_order, p.project_unit, "
               " CASE WHEN p.project_alias IS NULL THEN p.project_title ELSE '<a href=\"/dashboard/' || p.project_alias || '\">' || p.project_title || '</a>' END as project_title, "
               " p.project_status, "
               " p.project_manager, "
               " CASE WHEN to_char(p.project_start, 'YYYY-MM') = to_char(p.project_end, 'YYYY-MM') THEN "
               "    to_char(p.project_start, 'DD') || '-' || to_char(p.project_end, 'DD Mon YYYY') "
"                    WHEN p.project_end IS NULL THEN to_char(p.project_start, 'DD Mon YYYY') "
               "    ELSE to_char(p.project_start, 'DD Mon YYYY') || ' to ' || to_char(p.project_end, 'DD Mon YYYY') END"
               "         as project_dates, "
               " '<div class=\"progress\" style=\"height: 20px;\"><div class=\"progress-bar\" role=\"progressbar\" aria-label=\"Progress of the project\" style=\"width: ' "
               " || coalesce(round((ps.objects_digitized::numeric/ps.collex_to_digitize::numeric) * 100, 2), 0)  ||"
               " '%%;\" aria-valuenow=\"'"
               " || coalesce(round((ps.objects_digitized::numeric/ps.collex_to_digitize::numeric) * 100, 2), 0)  ||"
               " '\" aria-valuemin=\"0\" aria-valuemax=\"100\">'"
               " || coalesce(round((ps.objects_digitized::numeric/ps.collex_to_digitize::numeric) * 100, 2), 0)  ||"
               "'%%</div></div>' as project_progress,"
               " coalesce(to_char(ps.objects_digitized, 'FM9,999,999,999'), 0::text) as objects_digitized, "
               " coalesce(to_char(ps.images_taken, 'FM9,999,999,999'), 0::text) as images_taken, "
               " coalesce(to_char(ps.images_public, 'FM9,999,999,999'), 0::text) as images_public "
               " FROM projects p LEFT JOIN projects_stats ps ON (p.project_id = ps.project_id) "
               " WHERE p.skip_project IS NOT True AND p.project_section = 'IS' "
               " GROUP BY "
               "        p.project_id, p.project_title, p.project_unit, p.project_acronym, p.project_status, p.project_description, "
               "        p.project_method, p.project_manager, p.project_url, p.project_start, p.project_end, p.updated_at, p.projects_order, p.project_type, "
               "        ps.collex_to_digitize, p.images_estimated, p.objects_estimated, ps.images_taken, ps.objects_digitized, ps.images_public"
               " ORDER BY p.projects_order DESC"))

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

    return render_template('home.html',
                           projects=projects,
                           form=form,
                           msg=msg,
                           user_exists=user_exists,
                           username=username,
                           graphJSON_summary=graphJSON_summary,
                           summary_stats=summary_stats,
                           md_stats=md_stats,
                           is_stats=is_stats,
                           tables_md=[list_projects_md.to_html(table_id='list_projects_md', index=False,
                                                border=0, escape=False,
                                                classes=["display", "compact", "table-striped", "w-100"])],
                           tables_is=[list_projects_is.to_html(table_id='list_projects_is', index=False,
                                                               border=0, escape=False,
                                                               classes=["display", "compact", "table-striped", "w-100"])],
                           asklogin=True,
                           summary_datatable=[summary_datatable.to_html(table_id='summary_datatable', index=False,
                                                               border=0, escape=False,
                                                               classes=["display", "compact", "table-striped",
                                                                        "w-100"])]
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

    # Declare the login form
    form = LoginForm(request.form)
    return render_template('about.html', site_ver=site_ver, form=form)


@app.route('/qc_process/<folder_id>/', methods=['GET','POST'], strict_slashes=False)
@login_required
def qc_process(folder_id):
    """Run QC on a folder"""
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Declare the login form
    form = LoginForm(request.form)

    username = current_user.name
    project_admin = query_database("SELECT count(*) as no_results FROM qc_users u, qc_projects p, folders f "
                                   "    WHERE u.username = %(username)s "
                                   "        AND p.project_id = f.project_id "
                                   "        AND f.folder_id = %(folder_id)s "
                                   "        AND u.user_id = p.user_id",
                                   {'username': username, 'folder_id': folder_id})[0]
    if project_admin['no_results'] == 0:
        # Not allowed
        return redirect(url_for('home'))
    file_id_q = request.values.get('file_id')
    msg = ""
    if file_id_q is not None:
        qc_info = request.values.get('qc_info')
        qc_val = request.values.get('qc_val')
        user_id = query_database("SELECT user_id FROM qc_users WHERE username = %(username)s",
                                        {'username': username})[0]
        if qc_val == "1" and qc_info == "":
            msg = "Error: The field QC Details can not be empty if the file failed the QC."
        else:
            q = query_database("UPDATE qc_files SET "
                             "      file_qc = %(qc_val)s, "
                             "      qc_by = %(qc_by)s, "
                             "      qc_info = %(qc_info)s "
                             " WHERE file_id = %(file_id)s RETURNING file_id",
                             {'file_id': file_id_q,
                              'qc_info': qc_info,
                              'qc_val': qc_val,
                              'qc_by': user_id['user_id']
                              })[0]
            logging.info("file_id: {}".format(q['file_id']))
            return redirect(url_for('qc_process', folder_id=folder_id))
    project_id = query_database("SELECT project_id from folders WHERE folder_id = %(folder_id)s",
                                   {'folder_id': folder_id})[0]
    project_settings = query_database("SELECT qc_percent FROM qc_settings "
                                   " WHERE project_id = %(project_id)s",
                                   {'project_id': project_id['project_id']})
    if len(project_settings) == 0:
        project_settings= {'qc_percent': 0.1}
    else:
        project_settings = project_settings[0]
    folder_qc_check = query_database("SELECT "
                                     "  CASE WHEN q.qc_status = 0 THEN 'QC Passed' "
                                     "          WHEN q.qc_status = 1 THEN 'QC Failed' "
                                     "          ELSE 'QC Pending' END AS qc_status, "
                                     "      qc_ip, u.username AS qc_by, "
                                     "      TO_CHAR(updated_at, 'yyyy-mm-dd') AS updated_at"
                                     " FROM qc_folders q, "
                                     "      qc_users u WHERE q.qc_by=u.user_id "
                                     "      AND q.folder_id = %(folder_id)s",
                                     {'folder_id': folder_id})
    folder_qc = {}
    folder_qc['qc_status'] = 'QC Pending'
    folder_qc['qc_by'] = ''
    folder_qc['updated_at'] = ''
    folder_qc['qc_ip'] = ''
    if folder_qc_check != None:
        if len(folder_qc_check) > 0:
            folder_qc['qc_status'] = folder_qc_check[0]['qc_status']
            folder_qc['qc_by'] = folder_qc_check[0]['qc_by']
            folder_qc['updated_at'] = folder_qc_check[0]['updated_at']
            folder_qc['qc_ip'] = folder_qc_check[0]['qc_ip']
    folder_stats1 = query_database("SELECT count(file_id) as no_files "
                                   "    FROM files "
                                   "    WHERE folder_id = %(folder_id)s",
                                   {'folder_id': folder_id})
    folder_stats2 = query_database("SELECT count(DISTINCT c.file_id) as no_errors "
                                   "    FROM file_checks c "
                                   "    WHERE file_id IN ("
                                   "        SELECT file_id "
                                   "        FROM files "
                                   "        WHERE folder_id = %(folder_id)s"
                                   "        ) "
                                   "        AND check_results = 1",
                                   {'folder_id': folder_id})
    folder_stats = {
        'no_files': folder_stats1[0]['no_files'],
        'no_errors': folder_stats2[0]['no_errors']
    }
    logging.info("qc_status: {} | no_files: {}".format(folder_qc['qc_status'], folder_stats['no_files']))
    project_alias = query_database("SELECT project_alias FROM projects WHERE project_id IN "
                                   "   (SELECT project_id "
                                   "       FROM folders "
                                   "       WHERE folder_id = %(folder_id)s)",
                                   {'folder_id': folder_id})[0]
    if folder_qc['qc_status'] == "QC Pending" and folder_stats['no_files'] > 0:
        # Setup the files for QC
        in_qc = query_database("SELECT count(*) as no_files FROM qc_files WHERE folder_id = %(folder_id)s",
                           {'folder_id': folder_id})
        if in_qc[0]['no_files'] == 0:
            q = query_database_2("DELETE FROM qc_folders WHERE folder_id = %(folder_id)s",
                               {'folder_id': folder_id})
            q = query_database_2("INSERT INTO qc_folders (folder_id, qc_status) "
                                 "      VALUES (%(folder_id)s, 9)",
                           {'folder_id': folder_id})
            no_files_for_qc = math.ceil(folder_stats['no_files'] * project_settings['qc_percent'])
            q = query_database_2("INSERT INTO qc_files (folder_id, file_id) ("
                                    " SELECT folder_id, file_id "
                                    "  FROM files "
                                    "  WHERE folder_id = %(folder_id)s "
                                    "  ORDER BY RANDOM() LIMIT %(qlimit)s)",
                               {'folder_id': folder_id, 'qlimit': psycopg2.extensions.AsIs(no_files_for_qc)})
            return redirect(url_for('qc_process', folder_id=folder_id))
        else:
            qc_stats_q = query_database("WITH errors AS "
                                      "         (SELECT count(file_id) as no_files "
                                      "             FROM qc_files "
                                      "             WHERE folder_id = %(folder_id)s "
                                      "                 AND file_qc = 1),"
                                      "passed AS "
                                      "         (SELECT count(file_id) as no_files "
                                      "             FROM qc_files "
                                      "             WHERE folder_id = %(folder_id)s "
                                      "                 AND file_qc = 0),"
                                      "total AS (SELECT count(file_id) as no_files FROM qc_files "
                                      "             WHERE folder_id = %(folder_id)s)"
                                      " SELECT t.no_files, e.no_files as no_errors,"
                                      "         p.no_files as no_passed "
                                      " FROM errors e, total t, passed p ",
                               {'folder_id': folder_id})[0]
            qc_stats = {}
            qc_stats['no_files'] = int(qc_stats_q['no_files'])
            qc_stats['no_errors'] = int(qc_stats_q['no_errors'])
            qc_stats['passed'] = int(qc_stats_q['no_passed'])
            if qc_stats_q['no_files'] == qc_stats_q['no_errors']:
                qc_stats['percent_failed'] = 100
                qc_stats['percent_passed'] = 0
            else:
                qc_stats['percent_failed'] = round((int(qc_stats_q['no_errors']) / int(qc_stats_q['no_files'])) * 100, 3)
                qc_stats['percent_passed'] = round((int(qc_stats_q['no_passed']) / int(qc_stats_q['no_files'])) * 100, 3)
            folder = query_database("SELECT * FROM folders WHERE folder_id = %(folder_id)s",
                                          {'folder_id': folder_id})[0]
            if qc_stats['no_files'] != int(qc_stats['no_errors']) + int(qc_stats['passed']):
                file_qc = query_database("SELECT f.* FROM qc_files q, files f "
                                         "  WHERE q.file_id = f.file_id "
                                         "     AND f.folder_id = %(folder_id)s"
                                         "     AND q.file_qc = 9 "
                                         "  LIMIT 1 ",
                                       {'folder_id': folder_id})[0]
                file_details = query_database("SELECT file_id, folder_id, file_name "
                                              " FROM files WHERE file_id = %(file_id)s",
                                              {'file_id': file_qc['file_id']})[0]
                file_checks = query_database(
                            "SELECT file_check, check_results, "
                            "       CASE WHEN check_info = '' THEN 'Check passed.' "
                            "           ELSE check_info END AS check_info "
                            "   FROM file_checks "
                            "   WHERE file_id = %(file_id)s",
                            {'file_id': file_qc['file_id']})
                image_url = settings.jpg_previews + str(file_qc['file_id']) + '/?'
                file_metadata = pd.DataFrame(query_database("SELECT tag, taggroup, tagid, value "
                                                            "   FROM files_exif "
                                                            "   WHERE file_id = %(file_id)s "
                                                            "       AND filetype ilike 'TIF' "
                                                            "   ORDER BY taggroup, tag ",
                                                            {'file_id': file_qc['file_id']}))
                folder = query_database(
                            "SELECT * FROM folders "
                            "       WHERE folder_id IN ("
                            "               SELECT folder_id "
                            "                   FROM files "
                            "                   WHERE file_id = %(file_id)s)",
                            {'file_id': file_qc['file_id']})[0]

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
                                       form=form
                                       )
            else:
                error_files = query_database("SELECT f.file_name, q.* FROM qc_files q, files f "
                                             "  WHERE q.folder_id = %(folder_id)s "
                                             "  AND q.file_qc=1 AND q.file_id = f.file_id",
                                            {'folder_id': folder_id})
                return render_template('qc_done.html',
                                       folder_id=folder_id,
                                       folder=folder,
                                       qc_stats=qc_stats,
                                       project_settings=project_settings,
                                       username=username,
                                       error_files=error_files,
                                       form=form)
    else:
        error_msg = "Folder is not available for QC."
        return render_template('error.html', form=form, error_msg=error_msg, project_alias=project_alias['project_alias']), 400


@app.route('/qc_done/<folder_id>/', methods=['POST', 'GET'], strict_slashes=False)
@login_required
def qc_done(folder_id):
    """Run QC on a folder"""
    username = current_user.name
    project_admin = query_database("SELECT count(*) as no_results "
                                   "    FROM qc_users u, qc_projects p, folders f "
                                   "    WHERE u.username = %(username)s "
                                   "        AND p.project_id = f.project_id "
                                   "        AND f.folder_id = %(folder_id)s "
                                   "        AND u.user_id = p.user_id",
                                   {'username': username, 'folder_id': folder_id})[0]
    if project_admin['no_results'] == 0:
        # Not allowed
        return redirect(url_for('home'))
    project_id = query_database("SELECT project_alias "
                                "   FROM projects "
                                "   WHERE project_id IN "
                                "   (SELECT project_id "
                                "       FROM folders "
                                "       WHERE folder_id = %(folder_id)s)",
                                {'folder_id': folder_id})[0]
    qc_info = request.values.get('qc_info')
    qc_status = request.values.get('qc_status')
    user_id = query_database("SELECT user_id FROM qc_users WHERE username = %(username)s",
                             {'username': username})[0]
    q = query_database_2("UPDATE qc_folders SET "
                             "      qc_status = %(qc_status)s, "
                             "      qc_by = %(qc_by)s, "
                             "      qc_info = %(qc_info)s "
                             " WHERE folder_id = %(folder_id)s RETURNING folder_id",
                             {'folder_id': folder_id,
                              'qc_status': qc_status,
                              'qc_info': qc_info,
                              'qc_by': user_id['user_id']
                              })
    return redirect(url_for('qc', project_id=project_id['project_alias']))


@app.route('/qc/<project_id>/', methods=['POST', 'GET'], strict_slashes=False)
@login_required
def qc(project_id):
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Declare the login form
    form = LoginForm(request.form)
    """List the folders and QC status"""
    username = current_user.name
    project_admin = query_database("SELECT count(*) as no_results "
                                   "    FROM qc_users u, qc_projects qp, projects p "
                                   "    WHERE u.username = %(username)s "
                                   "        AND p.project_alias = %(project_alias)s "
                                   "        AND qp.project_id = p.project_id "
                                   "        AND u.user_id = qp.user_id",
                                   {'username': username, 'project_alias': project_id})
    if project_admin == None:
        # Not allowed
        return redirect(url_for('home'))
    project_settings = query_database("SELECT coalesce(s.qc_percent, 0.1) as qc_percent FROM projects p "
                                      "     LEFT JOIN qc_settings s ON (s.project_id = p.project_id) "
                                   " WHERE p.project_alias = %(project_id)s ",
                                   {'project_id': project_id})
    if len (project_settings) == 0:
        project_settings = {'qc_percent': 0.1}
    else:
        project_settings = project_settings[0]
    project = query_database("SELECT * FROM projects "
                             " WHERE project_alias = %(project_id)s ",
                             {'project_id': project_id})[0]
    folder_qc_info = query_database("WITH pfolders AS (SELECT folder_id from folders WHERE project_id = %(pid)s),"
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
                                    "       f.no_files, f.file_errors, "
                                     "   CASE WHEN q.qc_status = 0 THEN 'QC Passed' "
                                     "      WHEN q.qc_status = 1 THEN 'QC Failed' "
                                     "      ELSE 'QC Pending' END AS qc_status, "
                                     "      q.qc_ip, u.username AS qc_by, "
                                     "      TO_CHAR(q.updated_at, 'yyyy-mm-dd') AS updated_at, "
                                    "       COALESCE(errors.no_files, 0) as qc_stats_no_errors, "
                                    "       COALESCE(passed.no_files, 0) as qc_stats_no_passed,"
                                    "       COALESCE(total.no_files, 0) as qc_stats_no_files "
                                    " FROM folders f LEFT JOIN qc_folders q ON "
                                    "       (f.folder_id = q.folder_id)"
                                    "       LEFT JOIN qc_users u ON "
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
                                    "  ORDER BY q.qc_status DESC, f.project_folder DESC",
                                     {'project_alias': project_id, 'pid': project['project_id']})
    return render_template('qc.html', site_ver=site_ver,
                               username=username,
                               project_settings=project_settings,
                               folder_qc_info=folder_qc_info,
                               project=project,
                               form=form)


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

    # Declare the login form
    form = LoginForm(request.form)

    user_name = current_user.name
    is_admin = user_perms('', user_type='admin')
    logging.info(is_admin)
    ip_addr = request.environ['REMOTE_ADDR']
    projects = query_database("select p.project_title, p.project_id, p.filecheck_link, p.project_alias, "
                              "     to_char(p.project_start, 'Mon-YYYY') as project_start, "
                              "     to_char(p.project_end, 'Mon-YYYY') as project_end,"
                              "     p.qc_status, p.project_unit "
                              " FROM qc_projects qp, "
                              "       qc_users u, "
                              "       projects p "
                              " WHERE qp.project_id = p.project_id "
                              "     AND qp.user_id = u.user_id "
                              "     AND u.username = %(username)s "
                              "     AND p.project_alias IS NOT NULL "
                              " GROUP BY p.project_title, p.project_id, p.filecheck_link, p.project_alias, "
                              "     p.project_start, p.project_end,"
                              "     p.qc_status, p.project_unit "
                              " ORDER BY p.projects_order DESC",
                                  {'username': user_name})
    project_list = []
    for project in projects:
        logging.info("project: {}".format(project))
        project_total = query_database("SELECT count(*) as no_files "
                                       "    FROM files "
                                       "    WHERE folder_id IN ("
                                       "            SELECT folder_id "
                                       "              FROM folders "
                                       "              WHERE project_id = %(project_id)s)",
                                       {'project_id': project['project_id']})
        project_ok = query_database("WITH a AS ("
                                    "   SELECT file_id FROM files WHERE folder_id IN "
                                    "       (SELECT folder_id from folders WHERE project_id = %(project_id)s)"
                                    "  ),"
                                    "   data AS ("
                                    "   SELECT c.file_id, sum(check_results) as check_results "
                                    "   FROM file_checks c, a "
                                    "   WHERE c.file_id = a.file_id "
                                    "   GROUP BY c.file_id) "
                                    " SELECT count(file_id) as no_files "
                                    " FROM data WHERE check_results = 0",
                                    {'project_id': project['project_id']})
        project_err = query_database("SELECT count(distinct file_id) as no_files FROM file_checks WHERE check_results "
                                     "= 1 AND "
                                     "file_id in (SELECT file_id from files where folder_id IN (SELECT folder_id from folders WHERE project_id = %(project_id)s))",
                                     {'project_id': project['project_id']})
        project_public = query_database("SELECT COALESCE(images_public, 0) as no_files FROM projects_stats WHERE "
                                        " project_id = %(project_id)s",
                                        {'project_id': project['project_id']})
        project_running = query_database("SELECT count(distinct file_id) as no_files FROM file_checks WHERE "
                                         "check_results "
                                         "= 9 AND "
                                         "file_id in ("
                                         "SELECT file_id FROM files WHERE folder_id IN (SELECT folder_id FROM folders "
                                         "WHERE project_id = %(project_id)s))",
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
        logging.info("project_alias: {}".format(project_alias))
        project_list.append({
                'project_title': project['project_title'],
                'project_id': project['project_id'],
                'filecheck_link': project['filecheck_link'],
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
                           is_admin=is_admin, ip_addr=ip_addr, form=form)


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
    if is_admin == False:
        # Not allowed
        return redirect(url_for('home'))
    else:
        msg=""
        return render_template('new_project.html',
                               username=username,
                               full_name=full_name,
                               is_admin=is_admin,
                               msg=msg,
                               today_date=datetime.today().strftime('%Y-%m-%d'),
                               form=form)


@app.route('/create_new_project/', methods=['POST'], strict_slashes=False)
@login_required
def create_new_project():
    """Create a new project"""
    username = current_user.name
    is_admin = user_perms('', user_type='admin')
    if is_admin == False:
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
    project = query_database("INSERT INTO projects  " 
                              "   (project_title, "
                               "    project_unit, "
                               "    project_alias,"
                               "    project_description, "
                               "    project_url, "
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
                               "            %(p_url)s, "
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
                             "              'F'"
                               "          FROM projects "
                               ") "
                              " RETURNING project_id ",
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
                               })[0]
    project_id = project['project_id']
    project = query_database("INSERT INTO projects_stats "
                             "  (project_id, collex_total, collex_to_digitize) VALUES  "
                             "   ( %(project_id)s, %(collex_total)s, %(collex_total)s) RETURNING project_id",
                             {'project_id': project_id,
                                 'collex_total': p_noobjects})
    user_project = query_database_2("INSERT INTO qc_projects (project_id, user_id) VALUES "
                               "    (%(project_id)s, %(user_id)s) RETURNING id",
                               {'project_id': project_id,
                                'user_id': current_user.id})
    if current_user.id != '101':
        user_project = query_database_2("INSERT INTO qc_projects (project_id, user_id) VALUES "
                                    "    (%(project_id)s, %(user_id)s) RETURNING id",
                                    {'project_id': project_id,
                                     'user_id': '101'})
    if current_user.id != '106':
        user_project = query_database_2("INSERT INTO qc_projects (project_id, user_id) VALUES "
                                    "    (%(project_id)s, %(user_id)s) RETURNING id",
                                    {'project_id': project_id,
                                     'user_id': '106'})
    if p_unitstaff != '':
        unitstaff = p_unitstaff.split(',')
        logging.info("unitstaff: {}".format(p_unitstaff))
        logging.info("len_unitstaff: {}".format(len(unitstaff)))
        if len(unitstaff) > 0:
            for staff in unitstaff:
                staff_user_id = query_database("SELECT user_id FROM qc_users WHERE username = %(username)s",
                                     {'username': staff.strip()})
                if len(staff_user_id) == 1:
                    user_project = query_database_2("INSERT INTO qc_projects (project_id, user_id) VALUES "
                                                "    (%(project_id)s, %(user_id)s) RETURNING id",
                                                {'project_id': project_id,
                                                 'user_id': staff_user_id[0]['user_id']})
                else:
                    user_project = query_database("INSERT INTO qc_users (username, user_active, is_admin) VALUES "
                                                    "    (%(username)s, 'T', 'F') RETURNING user_id",
                                                    {'username': staff.strip()})
                    user_project = query_database_2("INSERT INTO qc_projects (project_id, user_id) VALUES "
                                                    "    (%(project_id)s, %(user_id)s) RETURNING id",
                                                    {'project_id': project_id,
                                                     'user_id': user_project[0]['user_id']})
    return redirect(url_for('home', _anchor=p_alias))


@app.route('/edit_project/<project_id>/', methods=['GET'], strict_slashes=False)
@login_required
def edit_project(project_id):
    """Edit a project"""
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
    if is_admin == False:
        # Not allowed
        return redirect(url_for('home'))
    project_admin = query_database("SELECT count(*) as no_results "
                                   "    FROM qc_users u, qc_projects qp, projects p "
                                   "    WHERE u.username = %(username)s "
                                   "        AND p.project_alias = %(project_alias)s "
                                   "        AND qp.project_id = p.project_id "
                                   "        AND u.user_id = qp.user_id",
                                   {'username': username, 'project_alias': project_id})
    if project_admin == None:
        # Not allowed
        return redirect(url_for('home'))
    project = query_database("SELECT p.project_id, p.project_alias, "
                              " p.project_title, "
                              " p.project_acronym, "
                              " p.project_start, "
                              " p.project_end, "
                              " p.project_unit, "
                              " p.project_section, "
                              " p.project_status, " 
                              " COALESCE(p.project_url, '') as project_url, "
                              " COALESCE(p.project_description, '') as project_description, "
                              " COALESCE(s.collex_to_digitize, 0) AS collex_to_digitize "
                              " FROM projects p LEFT JOIN projects_stats s "
                              "     ON (p.project_id = s.project_id) "
                              " WHERE p.project_alias = %(project_alias)s",
                                   {'project_alias': project_id})[0]
    return render_template('edit_project.html',
                               username=username,
                               is_admin=is_admin,
                               project=project,
                               form=form)


@app.route('/project_update/<project_alias>', methods=['POST'], strict_slashes=False)
@login_required
def project_update(project_alias):
    """Save edits to a project"""
    username = current_user.name
    is_admin = user_perms('', user_type='admin')
    if is_admin == False:
        # Not allowed
        return redirect(url_for('home'))
    project_admin = query_database("SELECT count(*) as no_results "
                                   "    FROM qc_users u, qc_projects qp, projects p "
                                   "    WHERE u.username = %(username)s "
                                   "        AND p.project_alias = %(project_alias)s "
                                   "        AND qp.project_id = p.project_id "
                                   "        AND u.user_id = qp.user_id",
                                   {'username': username, 'project_alias': project_alias})
    if project_admin == None:
        # Not allowed
        return redirect(url_for('home'))
    p_title = request.values.get('p_title')
    p_desc = request.values.get('p_desc')
    p_url = request.values.get('p_url')
    p_status = request.values.get('p_status')
    p_start = request.values.get('p_start')
    p_end = request.values.get('p_end')
    p_noobjects = request.values.get('p_noobjects')
    project = query_database("UPDATE projects SET " 
                              "   project_title = %(p_title)s, " 
                              "   project_status = %(p_status)s, " 
                              "   project_start = CAST(%(p_start)s AS date) " 
                              " WHERE project_alias = %(project_alias)s"
                              " RETURNING project_id ",
                              {'p_title': p_title,
                               'p_status': p_status,
                               'p_start': p_start,
                               'project_alias': project_alias})[0]
    project_id = project['project_id']
    if p_desc != '':
        project = query_database("UPDATE projects SET "
                                 "   project_description = %(p_desc)s, "
                                 " WHERE project_alias = %(project_alias)s"
                                 " RETURNING project_id ",
                                 {'p_desc': p_desc,
                                  'project_alias': project_alias})
    if p_url != '':
        project = query_database("UPDATE projects SET "
                             "   project_url = %(p_url)s, "
                             " WHERE project_alias = %(project_alias)s"
                             " RETURNING project_id ",
                             {'p_url': p_url,
                              'project_alias': project_alias})
    if p_end != 'None':
        project = query_database("UPDATE projects SET "
                              "   project_end = CAST(%(p_end)s AS date) "
                              " WHERE project_alias = %(project_alias)s "
                              " RETURNING project_id ",
                              {'p_end': p_end,
                               'project_alias': project_alias})

    if p_noobjects != '0':
        project = query_database("UPDATE projects_stats SET "
                                  "   collex_to_digitize = %(p_noobjects)s, "
                                  "   collex_ready = %(p_noobjects)s "
                                  " WHERE project_id = %(project_id)s "
                                  " RETURNING project_id ",
                                  {'project_id': project_id,
                                   'p_noobjects': p_noobjects})
    return redirect(url_for('home', _anchor=project_alias))


@cache.memoize(60)
@app.route('/dashboard/<project_id>/<folder_id>/', methods=['POST', 'GET'], strict_slashes=False)
def dashboard_f(project_id=None, folder_id=None):
    """Dashboard for a project"""
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Declare the login form
    form = LoginForm(request.form)

    # Check if folder exists
    folder_check = query_database("SELECT folder_id FROM folders WHERE folder_id = %(folder_id)s AND project_id IN (SELECT project_id FROM projects WHERE project_alias = %(project_id)s)",
                                      {'folder_id': folder_id, 'project_id': project_id})
    if folder_check is None:
        error_msg = "Folder was not found."
        return render_template('error.html', form=form, error_msg=error_msg, project_alias=project_id), 404

    # Declare the login form
    form = LoginForm(request.form)

    tab = request.values.get('tab')
    if tab is None or tab == '':
        tab = 0
    else:
        try:
            tab = int(tab)
        except:
            error_msg = "Invalid tab ID."
            return render_template('error.html', form=form, error_msg=error_msg, project_alias=project_id), 400
    logging.info("tab: {}".format(tab))
    page = request.values.get('page')
    if page is None or page == '':
        page = 1
    else:
        try:
            page = int(page)
        except:
            error_msg = "Invalid page number."
            return render_template('error.html', form=form, error_msg=error_msg, project_alias=project_id), 400
    logging.info("page: {}".format(page))
    project_stats = {}
    if project_id is None:
        error_msg = "Project is not available."
        return render_template('error.html', form=form, error_msg=error_msg, project_alias=project_id), 404

    project_id_check = query_database("SELECT project_id FROM projects WHERE "
                                      " project_alias = %(project_id)s",
                                      {'project_id': project_id})
    if len(project_id_check) == 0:
        error_msg = "Project was not found."
        return render_template('error.html', form=form, error_msg=error_msg, project_alias=project_id), 404
    else:
        project_alias = project_id
        project_id = project_id_check[0]['project_id']
    logging.info("project_id: {}".format(project_id))
    logging.info("project_alias: {}".format(project_alias))
    if current_user.is_authenticated:
        username = current_user.name
        project_admin = query_database("SELECT count(*) as no_results FROM qc_users u, qc_projects p "
                                       " WHERE u.username = %(username)s "
                                       " AND p.project_id = %(project_id)s "
                                       " AND u.user_id = p.user_id",
                         {'username': username, 'project_id': project_id})[0]
        if project_admin['no_results'] > 0:
            project_admin = True
        else:
            project_admin = False
        logging.info("project_admin: {} - {}".format(username, project_admin))
    else:
        project_admin = False
    project_info = query_database("SELECT * FROM projects WHERE project_id = %(project_id)s",
                         {'project_id': project_id})[0]
    try:
        filechecks_list = project_info['project_checks'].split(',')
    except:
        error_msg = "Project is not available."
        return render_template('error.html', form=form, error_msg=error_msg, project_alias=project_alias), 404
    project_total = query_database("SELECT count(*) as no_files "
                                   "    FROM files "
                                   "    WHERE folder_id IN (SELECT folder_id "
                                   "                        FROM folders "
                                   "                        WHERE project_id = %(project_id)s)",
                                   {'project_id': project_id})
    project_stats['total'] = format(int(project_total[0]['no_files']), ',d')
    project_ok = query_database("WITH "
                                "folders_q as (SELECT folder_id from folders WHERE project_id = %(project_id)s), "
                                "files_q as (SELECT file_id FROM files f, folders_q fol WHERE f.folder_id = fol.folder_id), "
                                "data AS (SELECT "
                                "       f.file_id, sum(check_results) as check_results "
                                "       FROM file_checks f, files_q q "
                                "       WHERE f.file_id = q.file_id "
                                "   GROUP BY f.file_id) "
                                " SELECT count(file_id) as no_files "
                                " FROM data WHERE check_results = 0",
                                   {'project_id': project_id})
    project_stats['ok'] = format(int(project_ok[0]['no_files']), ',d')
    project_err = query_database("SELECT count(distinct file_id) as no_files FROM file_checks WHERE check_results "
                                 "= 1 AND "
                                 "file_id in (SELECT file_id from files where folder_id IN (SELECT folder_id from folders WHERE project_id = %(project_id)s))",
                                   {'project_id': project_id})
    project_stats['errors'] = format(int(project_err[0]['no_files']), ',d')
    project_running = query_database("SELECT count(distinct file_id) as no_files FROM file_checks WHERE "
                                   "check_results "
                                 "= 9 AND "
                                 "file_id in (" 
                                 "SELECT file_id FROM files WHERE folder_id IN (SELECT folder_id FROM folders "
                                 "WHERE project_id = %(project_id)s))",
                                 {'project_id': project_id})
    project_stats['running'] = format(int(project_running[0]['no_files']), ',d')
    project_public = query_database("SELECT COALESCE(images_public, 0) as no_files FROM projects_stats WHERE "
                                    " project_id = %(project_id)s",
                                    {'project_id': project_id})
    project_stats['public'] = format(int(project_public[0]['no_files']), ',d')
    project_folders = query_database("SELECT f.project_folder, f.folder_id, coalesce(f.no_files, 0) as no_files, "
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
                                     "WHERE f.project_id = %(project_id)s ORDER BY "
                                     "f.date DESC, f.project_folder DESC",
                                 {'project_id': project_id})
    folder_name = None
    folder_qc = {
        'qc_status': "QC Pending",
        'qc_by': "",
        'updated_at': "",
        'qc_ip': ""
    }
    if folder_id is not None and folder_id != '':
        folder_name = query_database("SELECT project_folder FROM folders WHERE folder_id = %(folder_id)s and "
                                     "project_id = %(project_id)s",
                                     {'folder_id': folder_id, 'project_id': project_id})
        logging.info("folder_name: {}".format(len(folder_name)))
        if len(folder_name) == 0:
            error_msg = "Folder does not exist in this project."
            return render_template('error.html', form=form, error_msg=error_msg, project_alias=project_alias), 404
        else:
            folder_name = folder_name[0]
        folder_files_df = pd.DataFrame(query_database("SELECT file_id, file_name FROM files WHERE folder_id = %("
                                                      "folder_id)s",
                                                      {'folder_id': folder_id}))
        no_items = 25
        if page is 1:
            offset = 0
        else:
            offset = (page - 1) * no_items
        files_df = query_database(
            "WITH data AS (SELECT file_id, COALESCE(preview_image, %(preview)s || file_id || '/?') as preview_image, "
            "         folder_id, file_name FROM files "
            "WHERE folder_id = %(folder_id)s)"
            " SELECT file_id, preview_image, folder_id, file_name"
            " FROM data "
            " ORDER BY file_name "
            "LIMIT %(no_items)s OFFSET %(offset)s",
            {'folder_id': folder_id, 'preview': settings.jpg_previews, 'no_items': psycopg2.extensions.AsIs(no_items), 'offset': psycopg2.extensions.AsIs(offset)})
        files_count = query_database("SELECT count(*) as no_files FROM files WHERE folder_id = %(folder_id)s",
                                  {'folder_id': folder_id})[0]
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
                list_files = pd.DataFrame(query_database("SELECT f.file_id, "
                                            "   CASE WHEN check_results = 0 THEN 'OK' "
                                            "       WHEN check_results = 9 THEN 'Pending' "
                                            "       WHEN check_results = 1 THEN 'Failed' "
                                            "       ELSE 'Pending' END as %(fcheck)s "
                                            " FROM files f LEFT JOIN file_checks c ON (f.file_id=c.file_id AND c.file_check = %(file_check)s) "
                                            "  where  "
                                            "   f.folder_id = %(folder_id)s",
                                            {'fcheck': psycopg2.extensions.AsIs(fcheck), 'file_check': fcheck, 'folder_id': folder_id}))
                logging.info("list_files.size: {}".format(list_files.shape[0]))
                preview_files = pd.DataFrame(query_database("SELECT f.file_id, "
                                                         "  COALESCE(f.preview_image, %(jpg_previews)s || f.file_id || '/?') as preview_image "
                                                         " FROM files f "
                                                         "  where  "
                                                         "   f.folder_id = %(folder_id)s",
                                                         {'jpg_previews': settings.jpg_previews, 'folder_id': folder_id}))
                if list_files.shape[0] > 0:
                    folder_files_df = folder_files_df.merge(list_files, how='outer', on='file_id')
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
                                           + '" data-bs-text = "Details of the file ' + folder_files_df['file_name'].astype(str) \
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
                                                    "tabindex=\"-1\" aria-disabled=\"true\">Previous</a></li>"
            else:
                pagination_html = pagination_html + "<li class=\"page-item\"><a class=\"page-link\" " \
                                                    "href=\"" + url_for('dashboard_f', project_id=project_alias, folder_id=folder_id) \
                                                    + "?tab=1&page={}\">Previous</a></li>".format(page - 1)
            # Ellipsis for first pages
            if page > 5:
                pagination_html = pagination_html + "<li class=\"page-item\"><a class=\"page-link\" " \
                                                    + "href=\"" + url_for('dashboard_f', project_id=project_alias, folder_id=folder_id) \
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
                                                        + url_for('dashboard_f', project_id=project_alias, folder_id=folder_id) \
                                                        + "?tab=1&page={}\">{}</a>".format(i, i) \
                                                        + "</li>"
            if (no_pages - page) > 4:
                pagination_html = pagination_html + "<li class=\"page-item disabled\"><a class=\"page-link\" " \
                                                    "href=\"#\">...</a></li>"
                pagination_html = pagination_html + "<li class=\"page-item\"><a class=\"page-link\" " \
                                  + "href=\"" + url_for('dashboard_f', project_id=project_alias, folder_id=folder_id) \
                                  + "?tab=1&page={last}\">{last}</a></li>".format(last=(no_pages))
            if page == no_pages:
                pagination_html = pagination_html + "<li class=\"page-item disabled\"><a class=\"page-link\" " \
                                                    "href=\"#\">Next</a></li>"
            else:
                if no_pages == 0:
                    pagination_html = pagination_html + "<li class=\"page-item disabled\"><a class=\"page-link\" " \
                                                        "href=\"#\">Next</a></li>"
                else:
                    pagination_html = pagination_html + "<li class=\"page-item\"><a class=\"page-link\" " \
                                                    + "href=\"" + url_for('dashboard_f', project_id=project_alias, folder_id=folder_id) \
                                                    + "?tab=1&page={}\">".format(page + 1) \
                                                    + "Next</a></li>"
            pagination_html = pagination_html + "</ul></nav>"
            folder_qc_check = query_database("SELECT "
                                             "  CASE WHEN q.qc_status = 0 THEN 'QC Passed' "
                                             "      WHEN q.qc_status = 1 THEN 'QC Failed' "
                                             "      WHEN q.qc_status = 9 THEN 'QC Pending' END AS qc_status, "
                                             " qc_ip, u.username AS qc_by, "
                                             " TO_CHAR(updated_at, 'yyyy-mm-dd') AS updated_at"
                                             " FROM qc_folders q, "
                                             " qc_users u WHERE q.qc_by=u.user_id AND "
                                             " q.folder_id = %(folder_id)s",
                                      {'folder_id': folder_id})
            if folder_qc_check != None:
                if len(folder_qc_check) > 0:
                    folder_qc['qc_status'] = folder_qc_check[0]['qc_status']
                    folder_qc['qc_by'] = folder_qc_check[0]['qc_by']
                    folder_qc['updated_at'] = folder_qc_check[0]['updated_at']
                    folder_qc['qc_ip'] = folder_qc_check[0]['qc_ip']
            folder_stats1 = query_database("SELECT coalesce(f.no_files, 0) as no_files "
                                           " FROM folders f WHERE folder_id = %(folder_id)s",
                                           {'folder_id': folder_id})
            folder_stats2 = query_database("SELECT count(DISTINCT c.file_id) as no_errors "
                                           " FROM file_checks c WHERE file_id IN (SELECT file_id from files WHERE"
                                           "        folder_id = %(folder_id)s) AND "
                                           "       check_results = 1",
                                           {'folder_id': folder_id})
            folder_stats = {
                'no_files': folder_stats1[0]['no_files'],
                'no_errors': folder_stats2[0]['no_errors']
            }
            post_processing_df = pd.DataFrame(query_database("SELECT file_id, file_name FROM files "
                                                             " WHERE folder_id = %(folder_id)s"
                                                             " ORDER BY file_name",
                                                {'folder_id': folder_id}))
            logging.info("project_postprocessing {}".format(project_info['project_postprocessing']))
            post_processing_df['file_name'] = '<a href="/file/' \
                                           + post_processing_df['file_id'].astype(str) + '/" title="File Details">' \
                                           + post_processing_df['file_name'].astype(str) \
                                           + '</a>'
            if project_info['project_postprocessing'] is not None:
                project_postprocessing = project_info['project_postprocessing'].split(',')
                for fcheck in project_postprocessing:
                    post_processing_vals = pd.DataFrame(query_database("SELECT f.file_id, "
                                                                       "  CASE WHEN fp.post_results = 0 THEN 'Completed' "
                                                                       "      WHEN fp.post_results = 9 THEN 'Pending' "
                                                                       "      WHEN fp.post_results = 1 THEN 'Failed' "
                                                                       "        ELSE 'Pending' END as %(fcheck)s "
                                                                       " FROM files f LEFT JOIN file_postprocessing fp "
                                                                       "        ON (f.file_id = fp.file_id "
                                                                       "            AND fp.post_step = %(post_step)s) "
                                                                       " WHERE f.folder_id = %(folder_id)s",
                                                                       {'fcheck': psycopg2.extensions.AsIs(fcheck),
                                                                            'folder_id': folder_id,
                                                                            'post_step': fcheck}))
                    if post_processing_vals.size != 0:
                        post_processing_df = post_processing_df.merge(post_processing_vals, how='outer', on='file_id')
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
    if int(project_ok[0]['no_files']) > 0:
        project_stats['ok_percent'] = round((int(project_ok[0]['no_files']) / int(project_total[0]['no_files'])) * 100, 5)
    else:
        project_stats['ok_percent'] = 0
    if int(project_err[0]['no_files']) > 0:
        project_stats['error_percent'] = round((int(project_err[0]['no_files']) / int(project_total[0]['no_files'])) * 100, 5)
    else:
        project_stats['error_percent'] = 0
    if int(project_running[0]['no_files']) > 0:
        project_stats['running_percent'] = round((int(project_running[0]['no_files']) / int(project_total[0]['no_files'])) * 100, 5)
    else:
        project_stats['running_percent'] = 0
    if current_user.is_authenticated:
        user_name = current_user.name
        is_admin = user_perms('', user_type='admin')
    else:
        user_name = ""
        is_admin = False
    folder_links = query_database("SELECT * FROM folders_links WHERE folder_id = %(folder_id)s",
                                                       {'folder_id': folder_id})
    logging.info("folder_links: {}".format(folder_links))
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
                                                       classes=["display", "compact", "table-striped", "w-100"])],
                       titles=[''],
                       username=user_name,
                       project_admin=project_admin,
                       is_admin=is_admin,
                       tab=tab,
                       files_count=files_count,
                       pagination_html=pagination_html,
                       pagination_html2=pagination_html,
                       jpg_previews=settings.jpg_previews,
                       folder_stats=folder_stats,
                       post_processing=[post_processing_df.to_html(table_id='post_processing_table',
                                                           index=False,
                                                           border=0,
                                                           escape=False,
                                                           classes=["display", "compact", "table-striped", "w-100"])],
                       folder_links=folder_links,
                       form=form
                       )


@cache.memoize(60)
@app.route('/dashboard/<project_id>/', methods=['GET','POST'], strict_slashes=False)
def dashboard(project_id):
    """Dashboard for a project"""
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Declare the login form
    form = LoginForm(request.form)

    project_stats = {}
    if project_id is None:
        error_msg = "Project is not available."
        return render_template('error.html', form=form, error_msg=error_msg, project_alias=None), 404

    project_id_check = query_database("SELECT project_id FROM projects WHERE "
                                      " project_alias = %(project_id)s",
                                      {'project_id': project_id})
    if len(project_id_check) == 0:
        error_msg = "Project was not found."
        return render_template('error.html', form=form, error_msg=error_msg, project_alias=project_id), 404
    else:
        project_alias = project_id
        project_id = project_id_check[0]['project_id']
    logging.info("project_id: {}".format(project_id))
    logging.info("project_alias: {}".format(project_alias))
    if current_user.is_authenticated:
        username = current_user.name
        project_admin = query_database("SELECT count(*) as no_results FROM qc_users u, qc_projects p "
                                       " WHERE u.username = %(username)s "
                                       " AND p.project_id = %(project_id)s "
                                       " AND u.user_id = p.user_id",
                         {'username': username, 'project_id': project_id})[0]
        if project_admin['no_results'] > 0:
            project_admin = True
        else:
            project_admin = False
        logging.info("project_admin: {} - {}".format(username, project_admin))
    else:
        project_admin = False
    project_info = query_database("SELECT * FROM projects WHERE project_id = %(project_id)s",
                         {'project_id': project_id})[0]
    try:
        filechecks_list = project_info['project_checks'].split(',')
    except:
        error_msg = "Project is not available."
        return render_template('error.html', form=form, error_msg=error_msg, project_alias=project_alias), 404
    project_total = query_database("SELECT count(*) as no_files "
                                   "    FROM files "
                                   "    WHERE folder_id IN (SELECT folder_id "
                                   "                        FROM folders "
                                   "                        WHERE project_id = %(project_id)s)",
                                   {'project_id': project_id})
    project_stats['total'] = format(int(project_total[0]['no_files']), ',d')
    project_ok = query_database("WITH "
                                "folders_q as (SELECT folder_id from folders WHERE project_id = %(project_id)s), "
                                "files_q as (SELECT file_id FROM files f, folders_q fol WHERE f.folder_id = fol.folder_id), "
                                "data AS (SELECT "
                                "       f.file_id, sum(check_results) as check_results "
                                "       FROM file_checks f, files_q q "
                                "       WHERE f.file_id = q.file_id "
                                "   GROUP BY f.file_id) "
                                " SELECT count(file_id) as no_files "
                                " FROM data WHERE check_results = 0",
                                {'project_id': project_id})
    project_stats['ok'] = format(int(project_ok[0]['no_files']), ',d')
    project_err = query_database("SELECT count(distinct file_id) as no_files FROM file_checks WHERE check_results "
                                 "= 1 AND "
                                 "file_id in (SELECT file_id from files where folder_id IN (SELECT folder_id from folders WHERE project_id = %(project_id)s))",
                                   {'project_id': project_id})
    project_stats['errors'] = format(int(project_err[0]['no_files']), ',d')
    project_running = query_database("SELECT count(distinct file_id) as no_files FROM file_checks WHERE "
                                   "check_results "
                                 "= 9 AND "
                                 "file_id in (" 
                                 "SELECT file_id FROM files WHERE folder_id IN (SELECT folder_id FROM folders "
                                 "WHERE project_id = %(project_id)s))",
                                 {'project_id': project_id})
    project_stats['running'] = format(int(project_running[0]['no_files']), ',d')
    project_public = query_database("SELECT COALESCE(images_public, 0) as no_files FROM projects_stats WHERE "
                                    " project_id = %(project_id)s",
                                    {'project_id': project_id})
    project_stats['public'] = format(int(project_public[0]['no_files']), ',d')
    project_folders = query_database("SELECT f.project_folder, f.folder_id, coalesce(f.no_files, 0) as no_files, "
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
                                     "WHERE f.project_id = %(project_id)s ORDER BY "
                                     "f.date DESC, f.project_folder DESC",
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
    folder_stats = {
        'no_files': 0,
        'no_errors': 0
    }
    post_processing_df = pd.DataFrame()
    if int(project_ok[0]['no_files']) > 0:
        project_stats['ok_percent'] = round((int(project_ok[0]['no_files']) / int(project_total[0]['no_files'])) * 100, 5)
    else:
        project_stats['ok_percent'] = 0
    if int(project_err[0]['no_files']) > 0:
        project_stats['error_percent'] = round((int(project_err[0]['no_files']) / int(project_total[0]['no_files'])) * 100, 5)
    else:
        project_stats['error_percent'] = 0
    if int(project_running[0]['no_files']) > 0:
        project_stats['running_percent'] = round((int(project_running[0]['no_files']) / int(project_total[0]['no_files'])) * 100, 5)
    else:
        project_stats['running_percent'] = 0
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
                       jpg_previews=settings.jpg_previews,
                       folder_stats=folder_stats,
                       post_processing=[post_processing_df.to_html(table_id='post_processing_table',
                                                           index=False,
                                                           border=0,
                                                           escape=False,
                                                           classes=["display", "compact", "table-striped"])],
                       folder_links=folder_links,
                       form=form
                       )


# @cache.memoize(60)
# @app.route('/ajax/foldertable/<int:folder_id>/', methods=['GET', 'POST'], strict_slashes=False)
# def dashboard_ajax(folder_id=None):
#     """Data for DataTables using AJAX"""
#     # Check if folder exists
#     folder_check = query_database("SELECT folder_id FROM folders WHERE folder_id = %(folder_id)s",
#                                       {'folder_id': folder_id})
#     data = {}
#     data['draw'] = 1
#     data['recordsTotal'] = 0
#     data['recordsFiltered'] = 0
#     data['data'] = None
#     try:
#         order_q = request.values.get('order[0][column]')
#     else:
#         order_q = 0
#     if folder_check is None or folder_id is None:
#         response = app.response_class(
#             response=json.dumps(data), status=200, mimetype='application/json'
#         )
#         return response
#
#     draw_q = request.values.get('draw')
#     if draw_q is None:
#         draw_q = 1
#     try:
#         draw_q = int(draw_q)
#     except:
#         logging.error("draw_q: {}".format(draw_q))
#         response = app.response_class(
#             response=json.dumps(data), status=200, mimetype='application/json'
#         )
#         return response
#     logging.info("draw_q: {}".format(draw_q))
#
#     start_q = request.values.get('start')
#     if start_q is None:
#         start_q = 0
#     try:
#         start_q = int(start_q)
#     except:
#         logging.error("start_q: {}".format(start_q))
#         response = app.response_class(
#             response=json.dumps(data), status=200, mimetype='application/json'
#         )
#         return response
#     logging.info("start_q: {}".format(start_q))
#
#     length_q = request.values.get('length')
#     if length_q is None:
#         length_q = 25
#     try:
#         length_q = int(length_q)
#     except:
#         logging.error("length_q: {}".format(length_q))
#         response = app.response_class(
#             response=json.dumps(data), status=200, mimetype='application/json'
#         )
#         return response
#     logging.info("length_q: {}".format(length_q))
#
#     start_q = int(length_q) * int(draw_q)
#     data['draw'] = int(draw_q)
#     order_q = request.values.get('order')
#     if order_q is None:
#         order_q = 0
#     try:
#         order_q = int(order_q)
#     except:
#         logging.error("order_q: {}".format(order_q))
#         response = app.response_class(
#             response=json.dumps(data), status=200, mimetype='application/json'
#         )
#         return response
#     logging.info("order_q: {}".format(order_q))
#     if order_q == 0:
#         order_q = 'file_name'
#
#     project_info = query_database("SELECT p.project_checks, p.project_postprocessing FROM projects p, folders f WHERE p.project_id = f.project_id AND f.folder_id = %(folder_id)s",
#                          {'folder_id': folder_id})[0]
#     try:
#         filechecks_list = project_info['project_checks'].split(',')
#     except:
#         logging.error("filechecks_list: {}".format(project_info['project_checks']))
#         response = app.response_class(
#             response=json.dumps(data), status=200, mimetype='application/json'
#         )
#         return response
#     folder_files_df = pd.DataFrame(query_database("SELECT file_id, file_name FROM files "
#                                                   "     WHERE folder_id = %(folder_id)s "
#                                                   "     ORDER BY %(order)s OFFSET %(offset)s LIMIT %(limit)s",
#                                                   {'folder_id': folder_id, 'offset': start_q, 'limit': length_q, 'order': psycopg2.extensions.AsIs(order_q)}))
#     files_count = query_database("SELECT count(*) as no_files FROM files WHERE folder_id = %(folder_id)s",
#                               {'folder_id': folder_id})[0]
#     data['recordsTotal'] = files_count['no_files']
#     data['recordsFiltered'] = files_count['no_files']
#     logging.info("no_files: {}".format(files_count['no_files']))
#     if files_count['no_files'] == 0:
#         logging.error("no_files: 0")
#         response = app.response_class(
#             response=json.dumps(data), status=200, mimetype='application/json'
#         )
#     else:
#         for fcheck in filechecks_list:
#             logging.info("fcheck: {}".format(fcheck))
#             list_files = pd.DataFrame(query_database("SELECT f.file_id, "
#                                         "   CASE WHEN check_results = 0 THEN 'OK' "
#                                         "       WHEN check_results = 9 THEN 'Pending' "
#                                         "       WHEN check_results = 1 THEN 'Failed' "
#                                         "       ELSE 'Pending' END as {} "
#                                         " FROM files f LEFT JOIN file_checks c ON (f.file_id=c.file_id AND c.file_check = %(file_check)s) "
#                                         "  where  "
#                                         "   f.folder_id = %(folder_id)s"
#                                         "   ORDER BY %(order)s OFFSET %(offset)s LIMIT %(limit)s".format(fcheck),
#                                         {'file_check': fcheck, 'folder_id': folder_id, 'offset': start_q, 'limit': length_q, 'order': psycopg2.extensions.AsIs(order_q)}))
#             logging.info("list_files.size: {}".format(list_files.shape[0]))
#             preview_files = pd.DataFrame(query_database("SELECT f.file_id, "
#                                                      "  COALESCE(f.preview_image, '{}' || f.file_id || '/?') as preview_image "
#                                                      " FROM files f "
#                                                      "  where  "
#                                                      "   f.folder_id = %(folder_id)s"
#                                                      "   ORDER BY %(order)s OFFSET %(offset)s LIMIT %(limit)s".format(settings.jpg_previews),
#                                                      {'folder_id': folder_id, 'offset': start_q, 'limit': length_q, 'order': psycopg2.extensions.AsIs(order_q)}))
#             if list_files.shape[0] > 0:
#                 folder_files_df = folder_files_df.merge(list_files, how='outer', on='file_id')
#         folder_files_df = folder_files_df.sort_values(by=['file_name'])
#         folder_files_df = folder_files_df.sort_values(by=filechecks_list)
#         folder_files_df = folder_files_df.merge(preview_files, how='outer', on='file_id')
#         folder_files_df['file_name'] = '<a href="/file/' \
#                                        + folder_files_df['file_id'].astype(str) + '/" title="File Details">' \
#                                        + folder_files_df['file_name'].astype(str) \
#                                        + '</a> ' \
#                                        + '<button type="button" class="btn btn-light btn-sm" ' \
#                                        + 'data-bs-toggle="modal" data-bs-target="#previewmodal1" ' \
#                                        + 'data-bs-info="' + folder_files_df['preview_image'] \
#                                        + '" data-bs-link = "/file/' + folder_files_df['file_id'].astype(str) \
#                                        + '" data-bs-text = "Details of the file ' + folder_files_df['file_name'].astype(str) \
#                                        + '" title="Image Preview">' \
#                                        + '<i class="fa-regular fa-image"></i></button>'
#         folder_files_df = folder_files_df.drop(['file_id'], axis=1)
#         folder_files_df = folder_files_df.drop(['preview_image'], axis=1)
#         files_data = json.loads(folder_files_df.to_json(orient='table', index=False))['data']
#         ajax_data = []
#         #data['data'] = json.loads(folder_files_df.to_json(orient='table', index=False))['data']
#         for row in files_data:
#             logging.info("ROW: {}".format(row))
#             row_data = []
#             logging.info("ROW_type: {}".format(type(row_data)))
#             for cell in row:
#                 logging.info("CELL: {}".format(row[cell]))
#                 row_data.append(row[cell])
#             ajax_data.append(row_data)
#         data['data'] = ajax_data
#         response = app.response_class(
#             response=json.dumps(data), status=200, mimetype='application/json'
#         )
#     return response


@cache.memoize(60)
@app.route('/dashboard/', methods=['GET'], strict_slashes=False)
def dashboard_empty():
    return redirect(url_for('login'))


@cache.memoize(60)
@app.route('/file/<file_id>/', methods=['GET'], strict_slashes=False)
def file(file_id):
    """File details"""
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Declare the login form
    form = LoginForm(request.form)

    if file_id is None:
        error_msg = "File ID is missing."
        return render_template('error.html', form=form, error_msg=error_msg, project_alias=None), 400
    else:
        try:
            file_id = int(file_id)
        except:
            error_msg = "Invalid File ID."
            return render_template('error.html', form=form, error_msg=error_msg, project_alias=None), 400
    folder_info = query_database("SELECT * FROM folders WHERE folder_id IN (SELECT folder_id FROM files WHERE file_id = %(file_id)s)",
                         {'file_id': file_id})[0]
    project_alias = query_database("SELECT COALESCE(project_alias, project_id::text) as project_id FROM projects "
                                   " WHERE project_id = %(project_id)s",
                   {'project_id': folder_info['project_id']})[0]
    project_alias = project_alias['project_id']
    file_details = query_database("WITH data AS ("
                                  "         SELECT file_id, "
                                  "             COALESCE(preview_image, %(preview)s || file_id) as preview_image, "
                                  "             folder_id, file_name, dams_uan "
                                  "             FROM files "
                              "                 WHERE folder_id = %(folder_id)s AND folder_id IN (SELECT folder_id FROM folders WHERE project_id != ANY('{{100,131}}'))"
                                  " UNION "
                                  "         SELECT file_id, COALESCE(preview_image, %(preview)s || file_id) as preview_image, folder_id, file_name, dams_uan "
                                  "             FROM files "
                              "                 WHERE folder_id = %(folder_id)s AND folder_id NOT IN (SELECT folder_id FROM folders WHERE project_id != ANY('{{100,131}}'))"
                                  "             ORDER BY file_name"
                                  "),"
                              "data2 AS (SELECT file_id, preview_image, folder_id, file_name, dams_uan, "
                              "         lag(file_id,1) over (order by file_name) prev_id,"
                              "         lag(file_id,-1) over (order by file_name) next_id "
                              " FROM data)"
                              " SELECT "
                                  " file_id, "
                                  "     CASE WHEN position('?' in preview_image)>0 THEN preview_image ELSE preview_image || '?' END AS preview_image, "
                                  " folder_id, file_name, dams_uan, prev_id, next_id "
                                  "FROM data2 WHERE file_id = %(file_id)s LIMIT 1",
                              {'folder_id': folder_info['folder_id'], 'file_id': file_id, 'preview': settings.jpg_previews})[0]
    file_checks = query_database("SELECT file_check, check_results, CASE WHEN check_info = '' THEN 'Check passed.' "
                                            " ELSE check_info END AS check_info "
                                            " FROM file_checks WHERE file_id = %(file_id)s",
                         {'file_id': file_id})
    image_url = settings.jpg_previews + str(file_id)
    file_metadata = pd.DataFrame(query_database("SELECT tag, taggroup, tagid, value "
                                            " FROM files_exif WHERE file_id = %(file_id)s AND filetype ilike 'TIF' "
                                            " ORDER BY taggroup, tag ",
                         {'file_id': file_id}))
    file_links = query_database("SELECT link_name, link_url "
                                            " FROM files_links WHERE file_id = %(file_id)s ",
                         {'file_id': file_id})
    if current_user.is_authenticated:
        user_name = current_user.name
        is_admin = user_perms('', user_type='admin')
    else:
        user_name = ""
        is_admin = False
    logging.info("project_alias: {}".format(project_alias))
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
                           form=form
                           )


@app.route('/file/', methods=['GET'], strict_slashes=False)
def file_empty():
    return redirect(url_for('login'))


@cache.memoize(60)
@app.route('/file_json/<file_id>/', methods=['GET'], strict_slashes=False)
def file_json(file_id):
    """File details"""
    # Declare the login form
    form = LoginForm(request.form)
    if file_id is None:
        error_msg = "File ID is missing."
        return render_template('error.html', form=form, error_msg=error_msg, project_alias=None), 400
    else:
        try:
            file_id = int(file_id)
        except:
            error_msg = "Invalid File ID."
            return render_template('error.html', form=form, error_msg=error_msg, project_alias=None), 400
    file_checks = query_database("SELECT file_check, CASE WHEN check_results = 0 THEN '<div style=\"background: "
                                 "#198754; color:white;padding:8px;\">OK</div>' "
                                            "       WHEN check_results = 9 THEN 'Pending' "
                                            "       WHEN check_results = 1 THEN '<div style=\"background: "
                                 "#dc3545; color:white;padding:8px;\">Failed</div>' END as check_result, check_info"
                                            " FROM file_checks WHERE file_id = %(file_id)s",
                         {'file_id': file_id})
    return jsonify({"data": file_checks})


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
    project_info = query_database("SELECT * FROM projects WHERE project_alias = %(project_alias)s",
                                  {'project_alias': project_alias})[0]
    if q is None:
        error_msg = "No search query was submitted."
        return render_template('error.html', form=form, error_msg=error_msg, project_alias=project_alias), 400
    else:
        logging.info("q: {}".format(q))
        logging.info("metadata: {}".format(metadata))
        logging.info("offset: {}".format(offset))
        if metadata is None or metadata == '0':
            results = query_database("SELECT "
                                     "  f.file_id, f.folder_id, f.file_name, COALESCE(f.preview_image, %(jpg_previews)s || file_id) as preview_image, fd.project_folder "
                                     " FROM files f, folders fd, projects p "
                                     " WHERE f.folder_id = fd.folder_id AND "
                                     "  f.file_name ILIKE %(q)s AND "
                                     "  fd.project_id = p.project_id AND "
                                     "  p.project_alias = %(project_alias)s "
                                     " ORDER BY f.file_name"
                                     " LIMIT 50 "
                                     " OFFSET %(offset)s ",
                                {'project_alias': project_alias,
                                    'jpg_previews': settings.jpg_previews,
                                    'q': '%%' + q + '%%',
                                    'offset': psycopg2.extensions.AsIs(offset)})
        else:
            results = query_database("WITH m AS (SELECT file_id, tag, value, tagid, taggroup "
                                     "              FROM files_exif "
                                     "              WHERE value ILIKE %(q)s)"
                                     "SELECT "
                                     "  f.file_id, f.folder_id, f.file_name, COALESCE(f.preview_image, %(jpg_previews)s || file_id) as preview_image, fd.project_folder "
                                     " FROM files f, m, folders fd, projects p "
                                     " WHERE f.folder_id = fd.folder_id AND "
                                     "  f.file_name ILIKE %(q)s AND "
                                     "  f.file_id = m.file_id AND "
                                     "  fd.project_id = p.project_id AND "
                                     "  p.project_alias = %(project_alias)s "
                                     "  GROUP BY f.file_id, f.folder_id, f.file_name, f.preview_image, fd.project_folder "
                                     " ORDER BY f.file_name"
                                     " LIMIT 50 "
                                     " OFFSET %(offset)s ",
                                     {'project_alias': project_alias,
                                       'jpg_previews': settings.jpg_previews,
                                       'q': '%%' + q + '%%',
                                       'offset': psycopg2.extensions.AsIs(offset)})
    return render_template('search_files.html',
                           results=results,
                           project_info=project_info,
                           project_alias=project_alias,
                           q=q,
                           form=form)


@app.route('/dashboard/<project_alias>/search_folders', methods=['GET'], strict_slashes=False)
@cache.memoize()
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

    q = request.values.get('q')
    page = request.values.get('page')
    if page is None:
        page = 0
    offset = page * 50
    project_info = query_database("SELECT * FROM projects WHERE project_alias = %(project_alias)s",
                                  {'project_alias': project_alias})[0]
    if q is None:
        error_msg = "No search query was submitted."
        return render_template('error.html', form=form, error_msg=error_msg, project_alias=project_alias), 400
    else:
        logging.info("q: {}".format(q))
        logging.info("offset: {}".format(offset))
        results = query_database("WITH pfolders AS (SELECT folder_id from folders WHERE project_id in (SELECT project_id FROM projects WHERE project_alias = %(project_alias)s)),"
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
                                        "       LEFT JOIN qc_users u ON "
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
                                        "   AND f.project_folder ILIKE %(q)s "
                                        "  ORDER BY f.project_folder ASC"
                                        "  LIMIT 50 OFFSET %(offset)s",
                                        {'project_alias': project_alias,
                                            'q': '%%' + q + '%%',
                                            'offset': psycopg2.extensions.AsIs(offset)})
    results_df = pd.DataFrame({'folder': [], 'no_files': []})
    for row in results:
        results_df.loc[len(results_df.index)] = ['<a href="/dashboard/' + project_alias \
                                + '/' \
                                + str(row['folder_id']) \
                                + '/" title="Folder Details">' \
                                + row['project_folder'] \
                                + '</a> ', str(row['no_files'])]
    logging.info(results_df)
    return render_template('search_folders.html',
                           tables=[results_df.to_html(table_id='results',
                                                           index=False,
                                                           border=0,
                                                           escape=False,
                                                           classes=["display", "compact", "table-striped"])],
                           project_info=project_info,
                           project_alias=project_alias,
                           q=q,
                           form=form)


@app.route("/logout", methods=['GET'], strict_slashes=False)
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route("/notuser", methods=['GET'], strict_slashes=False)
def not_user():
    # Declare the login form
    form = LoginForm(request.form)

    logout_user()
    return render_template('notuser.html', form=form)


###################################
# Osprey API
###################################
@app.route('/api/', methods=['GET'], strict_slashes=False)
@cache.memoize()
def routes_list():
    """Print available routes in JSON"""
    # Adapted from https://stackoverflow.com/a/17250154
    func_list = {}
    for rule in app.url_map.iter_rules():
        # Skip 'static' routes
        if str(rule).startswith('/api'):
            func_list[rule.rule] = app.view_functions[rule.endpoint].__doc__
        else:
            continue
    return jsonify(func_list)


@app.route('/api/2.0/projects/', methods=['GET'], strict_slashes=False)
@cache.memoize()
def get_projects():
    """Get the list of projects."""
    data = query_database("SELECT "
                          "project_id, "
                          "project_title, "
                          "project_alias, "
                          "project_unit, "
                          "project_checks, "
                          "project_postprocessing, "
                          "project_status, "
                          "project_description, "
                          "project_type, "
                          "project_method, "
                          "project_manager, "
                          "project_url, "
                          "project_area, "
                          "project_start, "
                          "CASE WHEN project_end IS NULL THEN NULL ELSE project_end END as project_end, "
                          "project_datastorage, "
                          "project_notice, "
                          "updated_at::timestamp "
                          "FROM projects")
    return jsonify(data)


@app.route('/api/2.0/projects/<project_alias>', methods=['GET'], strict_slashes=False)
@cache.memoize()
def get_project_details(project_alias=None):
    """Get the details of a project by specifying the project_alias."""
    data = query_database("SELECT "
                              "project_id, "
                              "project_title, "
                              "project_alias, "
                              "project_unit, "
                              "project_checks, "
                              "project_postprocessing, "
                              "project_status, "
                              "project_description, "
                              "project_type, "
                              "project_method, "
                              "project_manager, "
                              "project_url, "
                              "project_area, "
                              "to_char(project_start, 'YYYY-MM-DD') AS project_start, "
                              "CASE WHEN project_end IS NULL THEN NULL ELSE to_char(project_end, 'YYYY-MM-DD') END as project_end, "
                              "project_notice, "
                              "updated_at::timestamp "
                          "FROM projects WHERE project_alias = %(project_alias)s",
                          {'project_alias': project_alias})
    if data is not None:
        folders = query_database("SELECT "
                                     "folder_id, "
                                     "project_id, "
                                     "project_folder as folder, "
                                     "status, "
                                     "notes, "
                                     "error_info, "
                                     "to_char(date, 'YYYY-MM-DD') as date, "
                                     "no_files, "
                                     "file_errors "
                                 "FROM folders WHERE project_id = %(project_id)s",
                              {'project_id': data[0]['project_id']})
        data[0]['folders'] = folders
        project_stats = query_database("SELECT "
                                           "collex_total, "
                                           "collex_to_digitize, "
                                           "collex_ready, "
                                           "objects_digitized, "
                                           "images_taken, "
                                           "images_in_dams, "
                                           "images_in_cis, "
                                           "images_public, "
                                           "no_records_in_cis, "
                                           "no_records_in_collexweb, "
                                           "no_records_in_collectionssiedu, "
                                           "no_records_in_gbif, "
                                           "updated_at::timestamp "
                                     "FROM projects_stats WHERE project_id = %(project_id)s",
                                     {'project_id': data[0]['project_id']})
        data[0]['project_stats'] = project_stats[0]
    return jsonify(data[0])


@app.route('/api/2.0/folders/<folder_id>', methods=['GET'], strict_slashes=False)
@cache.memoize()
def get_folder_details(folder_id=None):
    """Get the details of a folder and the list of files."""
    data = query_database("SELECT "
                             "folder_id, "
                             "project_id, "
                             "project_folder as folder, "
                             "status, "
                             "notes, "
                             "error_info, "
                             "to_char(date, 'YYYY-MM-DD') as date, "
                             "no_files, "
                             "file_errors "
                             "FROM folders WHERE folder_id = %(folder_id)s",
                             {'folder_id': folder_id})
    if data is not None:
        files_data = []
        files = query_database("SELECT "
                                   "file_id, "
                                   "folder_id, "
                                   "file_name, "
                                   "file_timestamp::timestamp, "
                                   "dams_uan, "
                                   "preview_image, "
                                   "updated_at::timestamp, "
                                   "created_at::timestamp "
                                 "FROM files WHERE folder_id = %(folder_id)s",
                              {'folder_id': folder_id})
        for file in files:
            file_checks = query_database("SELECT check_info, check_results, file_check, updated_at::timestamp "
                                   "FROM file_checks WHERE file_id = %(file_id)s",
                                   {'file_id': file['file_id']})
            file_post = query_database("SELECT post_step, post_results, post_info, updated_at::timestamp "
                                       "FROM file_postprocessing WHERE file_id = %(file_id)s",
                                       {'file_id': file['file_id']})
            file_md5 = query_database("SELECT filetype, md5, updated_at::timestamp "
                                      "FROM file_md5 WHERE file_id = %(file_id)s",
                                      {'file_id': file['file_id']})
            file_links = query_database("SELECT link_name, link_url, link_notes, updated_at::timestamp "
                                        "FROM files_links WHERE file_id = %(file_id)s",
                                        {'file_id': file['file_id']})
            files_data.append({
                'file_id': file['file_id'],
                'folder_id': file['folder_id'],
                'file_name': file['file_name'],
                'file_timestamp': file['file_timestamp'],
                'dams_uan': file['dams_uan'],
                'preview_image': file['preview_image'],
                'updated_at': file['updated_at'],
                'created_at': file['created_at'],
                'file_checks': file_checks,
                'file_postprocessing': file_post,
                'md5_hashes': file_md5,
                'links': file_links
            })
        data[0]['files'] = files_data
    return jsonify(data[0])


@app.route('/api/2.0/files/<file_id>', methods=['GET'], strict_slashes=False)
@cache.memoize()
def get_file_details(file_id=None):
    """Get the details of a file."""
    data = query_database("SELECT "
                           "file_id, "
                           "folder_id, "
                           "file_name, "
                           "file_timestamp::timestamp, "
                           "dams_uan, "
                           "preview_image, "
                           "updated_at::timestamp, "
                           "created_at::timestamp "
                           "FROM files WHERE file_id = %(file_id)s",
                           {'file_id': file_id})
    if data is not None:
        file_checks = query_database("SELECT check_info, check_results, file_check, updated_at::timestamp "
                               "FROM file_checks WHERE file_id = %(file_id)s",
                               {'file_id': file_id})
        data[0]['file_checks'] = file_checks
        file_exif = query_database("SELECT tag, value, filetype, tagid, taggroup, updated_at::timestamp "
                                     "FROM files_exif WHERE file_id = %(file_id)s",
                                     {'file_id': file_id})
        data[0]['exif'] = file_exif
        file_md5 = query_database("SELECT filetype, md5, updated_at::timestamp "
                                   "FROM file_md5 WHERE file_id = %(file_id)s",
                                   {'file_id': file_id})
        data[0]['md5_hashes'] = file_md5
        file_links = query_database("SELECT link_name, link_url, link_notes, updated_at::timestamp "
                                  "FROM files_links WHERE file_id = %(file_id)s",
                                  {'file_id': file_id})
        data[0]['links'] = file_links
        file_post = query_database("SELECT post_step, post_results, post_info, updated_at::timestamp "
                                   "FROM file_postprocessing WHERE file_id = %(file_id)s",
                                   {'file_id': file_id})
        data[0]['file_postprocessing'] = file_post
    return jsonify(data[0])


#####################################
if __name__ == '__main__':
    app.run()
