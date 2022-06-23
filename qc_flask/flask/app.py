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
from flask import redirect
from flask import url_for
from flask import send_file
from flask_caching import Cache

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

import math

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField
from wtforms.validators import DataRequired

import pandas as pd

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


# Cache config
config = {
    "DEBUG": True,  # some Flask specific configs
    "CACHE_TYPE": "FileSystemCache",  # Flask-Caching related configs
    "CACHE_DIR": "{}/cache".format(os.getcwd()),
    "CACHE_DEFAULT_TIMEOUT": 0
}
app = Flask(__name__)
app.secret_key = b'a40dceb6ed968dc4263a20e9107b4532eeff613875dbb7982d09aeaa37a5e6bb'
# tell Flask to use the above defined config
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


# Database
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


def query_database(query, parameters=""):
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
    return data


def user_perms(project_id, user_type='user'):
    try:
        user_name = current_user.name
    except:
        return False
    if user_type == 'user':
        is_user = query_database("SELECT COUNT(*) as is_user FROM qc_projects p, qc_users u WHERE p.user_id = "
                                 "u.user_id AND "
                                 "p.project_id = %(project_id)s AND u.username = %(user_name)s",
                         {'project_id': project_id, 'user_name': user_name})
        return is_user[0]['is_user'] == 1
    if user_type == 'admin':
        is_admin = query_database("SELECT is_admin FROM qc_users WHERE username = %(user_name)s",
                                 {'user_name': user_name})
        return is_admin[0]['is_admin'] == 1
    else:
        return False


class LoginForm(FlaskForm):
    username = StringField  (u'Username', validators=[DataRequired()])
    password = PasswordField(u'Password', validators=[DataRequired()])


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

    if current_user.is_authenticated:
        return redirect(url_for('home'))

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
            return redirect(url_for('home'))
        else:
            msg = "Error, user not known or password was incorrect"
    projects = query_database("select p.project_title, p.project_id, p.filecheck_link, p.project_alias FROM "
                              " projects p where p.project_alias is not null "
                                " ORDER BY p.projects_order DESC")
    return render_template('login.html', projects=projects, form=form, msg=msg, site_ver=site_ver)


@app.route('/qc', methods=['POST', 'GET'])
@login_required
def qc():
    """Search the whole system"""
    folder_id = request.values.get('folder_id')
    project_id = request.values.get('project_id')
    if project_id is None:
        error_msg = "Project can't be empty."
        return render_template('error.html', error_msg=error_msg), 404
    else:
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
        if folder_id is not None:
            fld = query_database("UPDATE folders SET qc_status = 0, qc_by = %(qc_by)s, qc_date = NOW(), qc_ip = %(qc_ip)s "
                             "WHERE folder_id = %(folder_id)s RETURNING folder_id",
                             {'qc_by': current_user.name, 'qc_ip': request.environ['REMOTE_ADDR'], 'folder_id':
                                 folder_id})
            return redirect(url_for('qc'))
    return render_template('qc.html', project_list=projects, site_ver=site_ver, user_name=current_user.name,
                           is_admin=user_perms('', user_type='admin'))


@app.route('/home', methods=['POST', 'GET'])
@login_required
def home():
    """Home for user, listing projects and options"""
    user_name = current_user.name
    is_admin = user_perms('', user_type='admin')
    logging.info(is_admin)
    #if is_admin:
    # projects = query_database("select p.project_title, p.project_id, p.filecheck_link, p.project_alias "
    #                           " FROM qc_projects qp, projects p "
    #                           " where qp.project_id = p.project_id ORDER BY p.projects_order DESC")
    #else:
    projects = query_database("select p.project_title, p.project_id, p.filecheck_link, p.project_alias FROM qc_projects qp, "
                                  " qc_users u, projects p where qp.project_id = p.project_id and qp.user_id = u.user_id "
                                  " AND u.username = %(username)s ORDER BY p.projects_order DESC",
                                  {'username': user_name})
    logging.info("projects: {}".format(projects))
    project_list = []
    for project in projects:
        project_total = query_database("SELECT count(*) as no_files from files where folder_id IN (SELECT folder_id "
                                       "from folders "
                                       "WHERE project_id = %(project_id)s)",
                                       {'project_id': project['project_id']})
        project_ok = query_database("WITH data AS (SELECT "
                                    " file_id, sum(check_results) as check_results "
                                    " FROM file_checks "
                                    " WHERE file_id in (SELECT file_id FROM files WHERE folder_id IN "
                                    " (SELECT folder_id from folders WHERE project_id = %(project_id)s)) "
                                    "   GROUP BY file_id) "
                                    " SELECT count(file_id) as no_files "
                                    " FROM data WHERE check_results = 0",
                                    {'project_id': project['project_id']})
        project_err = query_database("SELECT count(distinct file_id) as no_files FROM file_checks WHERE check_results "
                                     "= 1 AND "
                                     "file_id in (SELECT file_id from files where folder_id IN (SELECT folder_id from folders WHERE project_id = %(project_id)s))",
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
                'ok_percent': ok_percent,
                'error_percent': error_percent,
                'running_percent': running_percent,
                'project_alias': project_alias
            })
    return render_template('home.html', project_list=project_list, site_ver=site_ver, user_name=user_name,
                           is_admin=is_admin)


@cache.memoize()
@app.route('/dashboard/<project_id>/', methods=['POST', 'GET'])
def dashboard(project_id):
    """Dashboard for a project"""
    folder_id = request.values.get('folder_id')
    tab = request.values.get('tab')
    if tab is None:
        tab = 0
    else:
        try:
            tab = int(tab)
        except:
            error_msg = "Invalid tab ID."
            return render_template('error.html', error_msg=error_msg), 400
    page = request.values.get('page')
    if page is None:
        page = 1
    else:
        try:
            page = int(page)
        except:
            error_msg = "Invalid page number."
            return render_template('error.html', error_msg=error_msg), 400
    project_stats = {}
    if project_id is None:
        error_msg = "Project is not available."
        return render_template('error.html', error_msg=error_msg), 404
    else:
        try:
            project_id = int(project_id)
            project_id_check = query_database("SELECT project_alias FROM projects WHERE "
                                              " project_id = %(project_id)s",
                                              {'project_id': project_id})
            if len(project_id_check) == 0:
                error_msg = "Project was not found."
                return render_template('error.html', error_msg=error_msg), 404
            else:
                project_alias = project_id_check[0]['project_alias']
        except:
            #Check if shortname
            project_id_check = query_database("SELECT project_id FROM projects WHERE "
                                           " project_alias = %(project_id)s",
                                           {'project_id': project_id})
            if len(project_id_check) == 0:
                error_msg = "Project was not found."
                return render_template('error.html', error_msg=error_msg), 404
            else:
                project_alias = project_id
                project_id = project_id_check[0]['project_id']
        logging.info("project_id: {}".format(project_id))
        if current_user.is_authenticated:
            username = current_user.name
            project_admin = query_database("SELECT count(*) as no_results FROM qc_users WHERE "
                                           " username = %(username)s "
                                           " AND project_id = %(project_id)s",
                             {'username': username, 'project_id': project_id})[0]
            if project_admin['no_results'] > 0:
                project_admin = True
        else:
            project_admin = False
        project_info = query_database("SELECT * FROM projects WHERE project_id = %(project_id)s",
                             {'project_id': project_id})[0]
        try:
            filechecks_list = project_info['project_checks'].split(',')
        except:
            error_msg = "Project is not available."
            return render_template('error.html', error_msg=error_msg), 404
        project_total = query_database("SELECT count(*) as no_files from files where folder_id IN (SELECT folder_id "
                                       "from folders "
                                       "WHERE project_id = %(project_id)s)",
                                       {'project_id': project_id})
        project_stats['total'] = format(int(project_total[0]['no_files']), ',d')
        project_ok = query_database("WITH data AS (SELECT "
                    " file_id, sum(check_results) as check_results "
                    " FROM file_checks "
                    " WHERE file_id in (SELECT file_id FROM files WHERE folder_id IN "
                                                " (SELECT folder_id from folders WHERE project_id = %(project_id)s)) "
                    "   GROUP BY file_id) "
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
        project_folders = query_database("SELECT f.project_folder, f.folder_id, coalesce(f.no_files, 0) as no_files, "
                                         "f.file_errors, f.status, COALESCE(mt.md5, 9) as md5_tif, COALESCE(mr.md5, 9) as md5_raw, "
                                         "f.delivered_to_dams "
                                         "FROM folders f "
                                         "LEFT JOIN folders_md5 mt ON (f.folder_id = mt.folder_id and mt.md5_type = 'tif') "
                                         "LEFT JOIN folders_md5 mr ON (f.folder_id = mr.folder_id and mr.md5_type = 'raw') "
                                         "WHERE f.project_id = %(project_id)s ORDER BY f.file_errors desc, "
                                         "f.date DESC, f.project_folder DESC",
                                     {'project_id': project_id})
        folder_name = None
        if folder_id is not None:
            folder_name = query_database("SELECT project_folder FROM folders WHERE folder_id = %(folder_id)s and "
                                         "project_id = %(project_id)s",
                                         {'folder_id': folder_id, 'project_id': project_id})
            logging.info("folder_name: {}".format(len(folder_name)))
            if len(folder_name) == 0:
                error_msg = "Folder does not exist in this project."
                return render_template('error.html', error_msg=error_msg), 404
            else:
                folder_name = folder_name[0]
            folder_files_df = pd.DataFrame(query_database("SELECT file_id, file_name FROM files WHERE folder_id = %("
                                                          "folder_id)s",
                                                          {'folder_id': folder_id}))
            no_items = 50
            if page is 1:
                offset = 0
            else:
                offset = (page + 1) * no_items
            files_df = query_database("WITH data AS (SELECT file_id, folder_id, file_name FROM files "
                                      "WHERE folder_id = %(folder_id)s ORDER BY file_name)"
                                      " SELECT file_id, folder_id, file_name,"
                                      "         lag(file_id,1) over (order by file_name) prev_id,"
                                      "         lag(file_id,-1) over (order by file_name) next_id "
                                      " FROM data "
                                      "LIMIT {} OFFSET {}".format(no_items, offset),
                                      {'folder_id': folder_id})
            # for row in files_df:
            #     row['prev'] =
            files_count = query_database("SELECT count(*) as no_files FROM files WHERE folder_id = %(folder_id)s",
                                      {'folder_id': folder_id})[0]
            files_count = files_count['no_files']
            for fcheck in filechecks_list:
                list_files = pd.DataFrame(query_database("SELECT file_id, "
                                            "   CASE WHEN check_results = 0 THEN 'OK' "
                                            "       WHEN check_results = 9 THEN 'Pending' "
                                            "       WHEN check_results = 1 THEN 'Failed' END as {} "
                                            "FROM file_checks where file_check = %(file_check)s AND "
                                            "   file_id IN (SELECT file_id FROM files WHERE  "
                                            "   folder_id = %(folder_id)s)".format(fcheck),
                                            {'file_check': fcheck, 'folder_id': folder_id}))
                folder_files_df = folder_files_df.merge(list_files, how='outer', on='file_id')
            folder_files_df = folder_files_df.sort_values(by=['file_name'])
            folder_files_df = folder_files_df.sort_values(by=filechecks_list)
            folder_files_df['file_name'] = '<a href="/file/' \
                                           + folder_files_df['file_id'].astype(str) + '/">' \
                                           + folder_files_df['file_name'].astype(str) + '</a>'
            folder_files_df = folder_files_df.drop(['file_id'], axis=1)
            # Pagination
            pagination_html = "<nav aria-label=\"pages\"><ul class=\"pagination float-end\">"
            no_pages = math.floor(files_count / no_items)
            if page == 1:
                pagination_html = pagination_html + "<li class=\"page-item disabled\"><a class=\"page-link\" href=\"#\" " \
                                                    "tabindex=\"-1\" aria-disabled=\"true\">Previous</a></li>"
            else:
                pagination_html = pagination_html + "<li class=\"page-item\"><a class=\"page-link\" " \
                                                    "href=\"" + url_for('dashboard', project_id=project_alias) \
                                                    + "?folder_id=" + folder_id + "&tab=1&page={}\">Previous</a></li>".format(page - 1)
            # Ellipsis for first pages
            if page > 5:
                pagination_html = pagination_html + "<li class=\"page-item\"><a class=\"page-link\" " \
                                                    + "href=\"" + url_for('dashboard', project_id=project_alias) \
                                                    + "?folder_id=" + str(folder_id) \
                                                    + "&tab=1&page=1\">1</a></li>"
                pagination_html = pagination_html + "<li class=\"page-item disabled\"><a class=\"page-link\" " \
                                                    "href=\"#\">...</a></li>"
            for i in range(1, no_pages):
                if ((page - i) < 4) and ((i - page) < 4):
                    if i == page:
                        pagination_html = pagination_html + "<li class=\"page-item active\">"
                    else:
                        pagination_html = pagination_html + "<li class=\"page-item\">"
                    pagination_html = pagination_html + "<a class=\"page-link\" " \
                                                        + "href=\"" \
                                                        + url_for('dashboard', project_id=project_alias) \
                                                        + "?folder_id=" + folder_id + "&tab=1&page={}\">{}</a>".format(i, i) \
                                                        + "</li>"
            if (no_pages - page) > 4:
                pagination_html = pagination_html + "<li class=\"page-item disabled\"><a class=\"page-link\" " \
                                                    "href=\"#\">...</a></li>"
                pagination_html = pagination_html + "<li class=\"page-item\"><a class=\"page-link\" " \
                                  + "href=\"" + url_for('dashboard', project_id=project_alias) \
                                  + "?folder_id=" + str(folder_id) \
                                  + "&tab=1&page={last}\">{last}</a></li>".format(last=(no_pages - 1))
            if page == (no_pages - 1):
                pagination_html = pagination_html + "<li class=\"page-item disabled\"><a class=\"page-link\" " \
                                                    "href=\"#\">Next</a></li>"
            else:
                if no_pages == 0:
                    pagination_html = pagination_html + "<li class=\"page-item disabled\"><a class=\"page-link\" " \
                                                        "href=\"#\">Next</a></li>"
                else:
                    pagination_html = pagination_html + "<li class=\"page-item\"><a class=\"page-link\" " \
                                                    + "href=\"" + url_for('dashboard', project_id=project_alias) \
                                                    + "?folder_id=" + folder_id + "&tab=1&page={}\">".format(page + 1) \
                                                    + "Next</a></li>"
            pagination_html = pagination_html + "</ul></nav>"
        else:
            folder_files_df = pd.DataFrame()
            pagination_html = ""
            files_df = ""
            files_count = ""
        #print(folder_files_df)
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
        print(project_stats)
        if current_user.is_authenticated:
            user_name = current_user.name
            is_admin = user_perms('', user_type='admin')
        else:
            user_name = ""
            is_admin = False
        return render_template('dashboard.html',
                           project_id=project_id,
                           project_info=project_info,
                           project_alias=project_alias,
                           project_stats=project_stats,
                           project_folders=project_folders,
                           files_df=files_df,
                           folder_id=folder_id,
                           folder_name=folder_name,
                           tables=[folder_files_df.to_html(table_id='files_table', index=False, border=0,
                                                           escape=False, classes=["display", "compact", "table-striped"])],
                           titles=[''],
                           site_ver=site_ver,
                           user_name=user_name,
                           project_admin=project_admin,
                           is_admin=is_admin,
                           tab=tab,
                           files_count=files_count,
                           pagination_html=pagination_html,
                           pagination_html2=pagination_html)


@cache.memoize()
@app.route('/file/<file_id>/', methods=['POST', 'GET'])
def file(file_id):
    """File details"""
    #file_id = int(request.values.get('file_id'))
    if file_id is None:
        error_msg = "File ID is missing."
        return render_template('error.html', error_msg=error_msg), 400
    else:
        try:
            file_id = int(file_id)
        except:
            error_msg = "Invalid File ID."
            return render_template('error.html', error_msg=error_msg), 400
    folder_info = query_database("SELECT * FROM folders WHERE folder_id IN (SELECT folder_id FROM files WHERE file_id = %(file_id)s)",
                         {'file_id': file_id})[0]
    project_alias = query_database("SELECT COALESCE(project_alias, project_id::text) as project_id FROM projects "
                                   " WHERE project_id = %(project_id)s",
                   {'project_id': folder_info['project_id']})[0]
    project_alias = project_alias['project_id']

    file_details = query_database("WITH data AS (SELECT file_id, folder_id, file_name FROM files "
                              "WHERE folder_id = %(folder_id)s ORDER BY file_name),"
                              "data2 AS (SELECT file_id, folder_id, file_name,"
                              "         lag(file_id,1) over (order by file_name) prev_id,"
                              "         lag(file_id,-1) over (order by file_name) next_id "
                              " FROM data)"
                              " SELECT * FROM data2 WHERE file_id = %(file_id)s LIMIT 1",
                              {'folder_id': folder_info['folder_id'], 'file_id': file_id})[0]
    # file_details = query_database("SELECT * FROM files WHERE file_id = %(file_id)s",
    #                      {'file_id': file_id})[0]
    file_checks = query_database("SELECT file_check, check_results, CASE WHEN check_info = '' THEN 'Check passed.' "
                                            " ELSE check_info END AS check_info "
                                            " FROM file_checks WHERE file_id = %(file_id)s",
                         {'file_id': file_id})
    # file_checks = {"data": json.dumps(file_checks)}
    # folder_files_df = folder_files_df.drop(['file_id'], axis=1)
    # image_url = settings.jpg_previews + str(file_id)
    image_url = url_for('previewimage',
                                         folder_id=str(folder_info['folder_id']),
                                         file_id=str(file_id))
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
                           site_ver=site_ver,
                           user_name=user_name,
                           image_url=image_url,
                           is_admin=is_admin,
                           project_alias=project_alias)


@cache.memoize()
@app.route('/previewimage/<folder_id>/<file_id>/', methods=['GET'])
def previewimage(folder_id, file_id):
    """Return image previews from Mass Digi Projects."""
    #file_id = request.args.get('file_id')
    #folder_id = request.args.get('folder_id')
    if file_id is None:
        error_msg = "File ID is missing."
        return render_template('error.html', error_msg=error_msg), 400
    else:
        try:
            file_id = int(file_id)
        except:
            error_msg = "Invalid File ID."
            return render_template('error.html', error_msg=error_msg), 400
    if folder_id is None:
        error_msg = "Folder ID is missing."
        return render_template('error.html', error_msg=error_msg), 400
    else:
        try:
            folder_id = int(folder_id)
        except:
            error_msg = "Invalid Folder ID."
            return render_template('error.html', error_msg=error_msg), 400
    filename = "static/mdpp/folder{}/{}.jpg".format(folder_id, file_id)
    logging.info(filename)
    if not os.path.isfile(filename):
        filename = "static/na.jpg"
    logging.info(filename)
    return send_file(filename, mimetype='image/jpeg')


@cache.memoize()
@app.route('/file_json/<file_id>/', methods=['POST', 'GET'])
def file_json(file_id):
    """File details"""
    #file_id = int(request.values.get('file_id'))
    if file_id is None:
        error_msg = "File ID is missing."
        return render_template('error.html', error_msg=error_msg), 400
    else:
        try:
            file_id = int(file_id)
        except:
            error_msg = "Invalid File ID."
            return render_template('error.html', error_msg=error_msg), 400
    file_checks = query_database("SELECT file_check, CASE WHEN check_results = 0 THEN '<div style=\"background: "
                                 "#198754; color:white;padding:8px;\">OK</div>' "
                                            "       WHEN check_results = 9 THEN 'Pending' "
                                            "       WHEN check_results = 1 THEN '<div style=\"background: "
                                 "#dc3545; color:white;padding:8px;\">Failed</div>' END as check_result, check_info"
                                            " FROM file_checks WHERE file_id = %(file_id)s",
                         {'file_id': file_id})
    return jsonify({"data": file_checks})


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('login'))


#####################################
if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
