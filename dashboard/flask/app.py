#!flask/bin/python
#
# DPO QC System for Digitization Projects
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
# import simplejson as json
import os
import math
import pandas as pd

import psycopg2
import psycopg2.extras
# from psycopg2.extensions import AsIs

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

import settings

site_ver = "2.0.0"

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
    "CACHE_DIR": "/var/www/app/cache",
    "CACHE_DEFAULT_TIMEOUT": 0
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
    return render_template('error.html', error_msg=error_msg), 404


@app.errorhandler(500)
def page_not_found(e):
    logging.error(e)
    error_msg = "There was a system error."
    return render_template('error.html', error_msg=error_msg), 500


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


def query_database(query, parameters=""):
    logging.info("parameters: {}".format(parameters))
    logging.info("query: {}".format(query))
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('SET statement_timeout = 5000')
    # Run query
    try:
        cur.execute(query, parameters)
        logging.info("cur.query: {}".format(cur.query))
    except Exception as error:
        logging.error("Error: {}".format(error))
        logging.error("cur.query: {}".format(cur.query))
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
    # Run query
    try:
        cur.execute(query, parameters)
        logging.info("cur.query: {}".format(cur.query))
    except:
        logging.error("cur.query: {}".format(cur.query))
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
        user = query_database("SELECT user_id, username, user_active, "
                              "full_name "
                              "     FROM qc_users "
                              "     WHERE username = %(username)s AND pass = MD5(%(password)s)",
                              {'username': username, 'password': password})

        if user:
            user_obj = User(user[0]['user_id'], user[0]['username'], user[0][
                'full_name'],
                            user[0]['user_active'])
            login_user(user_obj)
            return redirect(url_for('home'))
        else:
            msg = "Error, user not known or password was incorrect"
    projects = query_database("select project_title, project_id, filecheck_link, project_alias, "
                              "     to_char(project_start, 'Mon-YYYY') as project_start, "
                              "     to_char(project_end, 'Mon-YYYY') as project_end,"
                              "     project_unit "
                              " FROM projects where project_alias is not null "
                              " ORDER BY projects_order DESC")
    return render_template('login.html',
                           projects=projects,
                           form=form,
                           msg=msg,
                           site_ver=site_ver,
                           user_exists=user_exists,
                           username=username)


@app.route('/qc_process/<folder_id>/', methods=['POST', 'GET'])
@login_required
def qc_process(folder_id):
    """Run QC on a folder"""
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
                                   {'project_id': project_id['project_id']})[0]
    folder_qc_check = query_database("SELECT "
                                     "  CASE WHEN q.qc_status = 0 THEN 'QC Passed' "
                                     "          WHEN q.qc_status = 1 THEN 'QC Failed' "
                                     "          WHEN q.qc_status = 9 THEN 'QC Pending' END AS qc_status, "
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
                                    "  ORDER BY RANDOM() LIMIT {})".format(no_files_for_qc),
                               {'folder_id': folder_id})
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
                image_url = settings.jpg_previews + str(file_qc['file_id'])
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
                project_alias = query_database("SELECT project_alias FROM projects WHERE project_id IN "
                                            "   (SELECT project_id "
                                            "       FROM folders "
                                            "       WHERE folder_id = %(folder_id)s)",
                                            {'folder_id': folder_id})[0]
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
                                       msg=msg
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
                                       error_files=error_files)
    else:
        error_msg = "Folder is not available for QC."
        return render_template('error.html', error_msg=error_msg), 400


@app.route('/qc_done/<folder_id>/', methods=['POST', 'GET'])
@login_required
def qc_done(folder_id):
    """Run QC on a folder"""
    #folder_id = request.values.get('folder_id')
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


@app.route('/qc/<project_id>/', methods=['POST', 'GET'])
@login_required
def qc(project_id):
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
    project_settings = query_database("SELECT s.qc_percent FROM qc_settings s, projects p "
                                   " WHERE p.project_alias = %(project_id)s AND"
                                      " s.project_id = p.project_id ",
                                   {'project_id': project_id})[0]
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
                               project=project)


@cache.memoize()
@app.route('/home/', methods=['POST', 'GET'])
@login_required
def home():
    """Home for user, listing projects and options"""
    user_name = current_user.name
    is_admin = user_perms('', user_type='admin')
    logging.info(is_admin)
    ip_addr = request.environ['REMOTE_ADDR']
    projects = query_database("select p.project_title, p.project_id, p.filecheck_link, p.project_alias, "
                              "     to_char(p.project_start, 'Mon-YYYY') as project_start, "
                              "     to_char(p.project_end, 'Mon-YYYY') as project_end,"
                              "     p.qc_status, p.project_unit "
                                "  FROM qc_projects qp, "
                                "       qc_users u, projects p "
                                " WHERE qp.project_id = p.project_id "
                              "     AND qp.user_id = u.user_id "
                              "     AND u.username = %(username)s "
                              "     AND p.project_alias IS NOT NULL "
                              " ORDER BY p.projects_order DESC",
                                  {'username': user_name})
    logging.info("projects: {}".format(projects))
    project_list = []
    for project in projects:
        project_total = query_database("SELECT count(*) as no_files "
                                       "    FROM files "
                                       "    WHERE folder_id IN ("
                                       "            SELECT folder_id "
                                       "              FROM folders "
                                       "              WHERE project_id = %(project_id)s)",
                                       {'project_id': project['project_id']})
        project_ok = query_database("WITH data AS ("
                                    "   SELECT file_id, sum(check_results) as check_results "
                                    "   FROM file_checks "
                                    "   WHERE file_id in (SELECT file_id FROM files WHERE folder_id IN "
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
                'project_alias': project_alias,
                'project_start': project['project_start'],
                'project_end': project['project_end'],
                'qc_status': project['qc_status'],
                'project_unit': project['project_unit']
            })
    return render_template('home.html', project_list=project_list, site_ver=site_ver, username=user_name,
                           is_admin=is_admin, ip_addr=ip_addr)


@app.route('/new_project/', methods=['POST', 'GET'])
@login_required
def new_project():
    """Create a new project"""
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
                               today_date=datetime.today().strftime('%Y-%m-%d'))


@app.route('/create_new_project/', methods=['POST'])
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
    return redirect(url_for('home', _anchor=p_alias))


@app.route('/edit_project/<project_id>/', methods=['GET'])
@login_required
def edit_project(project_id):
    """Edit a project"""
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
                               project=project)


@app.route('/logs/<project_id>/', methods=['GET'])
def logs(project_id):
    """Show logs of a project"""
    project = query_database("SELECT project_id FROM projects "
                             " WHERE project_alias = %(project_alias)s ",
                             {'project_alias': project_id})[0]
    project_id = project['project_id']
    move_log = query_database("INSERT INTO process_logging_5d (file_id, project_id, date_time, log_area, log_text, log_type)"
                          "(SELECT file_id, project_id, date_time, log_area, log_text, log_type FROM process_logging "
                          "     where project_id = %(project_id)s "
                          "     ORDER BY table_id ASC OFFSET 1000) returning table_id",
                          {'project_id': project_id})
    move_log = query_database(
                    "DELETE FROM process_logging where table_id in (select table_id from process_logging "
                    "  WHERE project_id = %(project_id)s "
                    "  ORDER BY table_id ASC OFFSET 1000) returning table_id ",
                    {'project_id': project_id})
    date = request.values.get('date')
    project_info = query_database("SELECT * FROM projects WHERE project_id = %(project_id)s",
                   {'project_id': project_id})[0]
    # logging.info("date: {}".format(date))
    if date is None:
        date = datetime.today().strftime('%Y-%m-%d')
    log_list = pd.DataFrame(query_database("SELECT to_char(date_time, 'YYYY-MM-DD HH:MM:SS') as date_time, "
                               " log_type, file_id::int as file_id, log_area, log_text "
                               " FROM process_logging "
                               " WHERE project_id = %(project_id)s "
                               "ORDER BY date_time DESC LIMIT 500",
                              {'project_id': project_id}))
    return render_template('logs.html',
                               date=date,
                               logs=logs,
                               project_info=project_info,
                               tables=[
                                    log_list.to_html(table_id='log_list',
                                                       index=False,
                                                       border=0,
                                                       escape=False,
                                                       classes=["display",
                                                                "compact",
                                                                "table-striped"])],
                           )


@app.route('/project_update/<project_alias>', methods=['POST'])
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


@app.route('/dashboard/<project_id>/', methods=['POST', 'GET'])
def dashboard(project_id):
    """Dashboard for a project"""
    folder_id = request.values.get('folder_id')
    tab = request.values.get('tab')
    if tab is None or tab == '':
        tab = 0
    else:
        try:
            tab = int(tab)
        except:
            error_msg = "Invalid tab ID."
            return render_template('error.html', error_msg=error_msg), 400
    page = request.values.get('page')
    if page is None or page == '':
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
            return render_template('error.html', error_msg=error_msg), 404
        project_total = query_database("SELECT count(*) as no_files "
                                       "    FROM files "
                                       "    WHERE folder_id IN (SELECT folder_id "
                                       "                        FROM folders "
                                       "                        WHERE project_id = %(project_id)s)",
                                       {'project_id': project_id})
        project_stats['total'] = format(int(project_total[0]['no_files']), ',d')
        project_ok = query_database("WITH data AS (SELECT "
                    "       file_id, sum(check_results) as check_results "
                    "       FROM file_checks "
                    "       WHERE file_id in (SELECT file_id FROM files WHERE folder_id IN "
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
            if folder_name is None:
                error_msg = "Folder does not exist in this project."
                return render_template('error.html', error_msg=error_msg), 404
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
                                               + folder_files_df['file_id'].astype(str) + '/" title="File Details">' \
                                               + folder_files_df['file_name'].astype(str) \
                                               + '</a> ' \
                                               + '<button type="button" class="btn btn-light btn-sm" ' \
                                                 'data-bs-toggle="modal" data-bs-target="#previewmodal1" ' \
                                                 'data-bs-info="' + settings.jpg_previews + folder_files_df['file_id'].astype(str) \
                                               + '" title="Image Preview">' \
                                                    '<i class="fa-regular fa-image"></i></button>'
                folder_files_df = folder_files_df.drop(['file_id'], axis=1)
                # Pagination
                pagination_html = "<nav aria-label=\"pages\"><ul class=\"pagination float-end\">"
                no_pages = math.ceil(files_count / no_items)
                logging.info("no_pages: {}".format(no_pages))
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
                for i in range(1, no_pages + 1):
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
                if page == no_pages:
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
                if project_info['project_postprocessing'] is not None:
                    project_postprocessing = project_info['project_postprocessing'].split(',')
                    for fcheck in project_postprocessing:
                        post_processing_vals = pd.DataFrame(query_database("SELECT f.file_id, "
                                                                           "  CASE WHEN fp.post_results = 0 THEN 'Completed' "
                                                                           "      WHEN fp.post_results = 9 THEN 'Pending' "
                                                                           "      WHEN fp.post_results = 1 THEN 'Failed' "
                                                                           "        ELSE 'Pending' END as {} "
                                                                           " FROM files f LEFT JOIN file_postprocessing fp "
                                                                           "        ON (f.file_id = fp.file_id "
                                                                           "            AND fp.post_step = %(fcheck)s) "
                                                                           " WHERE f.folder_id = %(folder_id)s".format(fcheck),
                                                                           {'folder_id': folder_id,
                                                                                'fcheck': fcheck}))
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
                           folder_qc=folder_qc,
                           tables=[folder_files_df.to_html(table_id='files_table',
                                                           index=False,
                                                           border=0,
                                                           escape=False,
                                                           classes=["display", "compact", "table-striped"])],
                           titles=[''],
                           site_ver=site_ver,
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
                                                               classes=["display", "compact", "table-striped"])]
                               )


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
    image_url = settings.jpg_previews + str(file_id)
    file_metadata = pd.DataFrame(query_database("SELECT tag, taggroup, tagid, value "
                                            " FROM files_exif WHERE file_id = %(file_id)s AND filetype ilike 'TIF' "
                                            " ORDER BY taggroup, tag ",
                         {'file_id': file_id}))
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
                           username=user_name,
                           image_url=image_url,
                           is_admin=is_admin,
                           project_alias=project_alias,
                           tables=[file_metadata.to_html(table_id='file_metadata', index=False, border=0,
                                                           escape=False,
                                                           classes=["display", "compact", "table-striped"])]
                           )


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
    app.run()
