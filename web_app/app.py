#!/usr/bin/env python3
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
from flask import Response
from flask import send_from_directory

from cache import cache
# Logging
from logger import logger

import os
import locale
import math
import pandas as pd
from uuid import UUID
from time import strftime
from time import localtime
import random
from auth_service import AuthBaseUser, get_auth_service

# MySQL — shared connection pool
from osprey.db import init_db, query_database_insert, run_query
from osprey.files import attach_preview_paths, resolve_image_viewer, static_fullsize_path, static_preview_path
from osprey.services import reports as report_service
# Flask Login
from flask_login import LoginManager
from flask_login import login_required
from flask_login import login_user
from flask_login import logout_user
from flask_login import current_user

import settings

from osprey.version import __version__ as site_ver
site_env = settings.env
site_net = settings.site_net

logger.info("site_ver = {}".format(site_ver))
logger.info("site_env = {}".format(site_env))
logger.info("site_net = {}".format(site_net))

# Set locale for number format
locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')

app = Flask(__name__)
app.secret_key = settings.secret_key

if site_env == "prod" and not settings.secret_key:
    raise RuntimeError("SECRET_KEY must be set when env is prod")

app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = (site_env == 'prod')

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

# API Blueprint (Worker + JSON endpoints at /api/*)
from api import api_bp
app.register_blueprint(api_bp, url_prefix='/api')

# CSRF protection for browser forms (API blueprint uses api_key auth)
from flask_wtf.csrf import CSRFProtect, generate_csrf
app.config['WTF_CSRF_ENABLED'] = True
app.config['WTF_CSRF_SECRET_KEY'] = settings.secret_key
# Token validation remains on; skip Referer matching (often missing behind
# proxies, privacy browsers, or when Referrer-Policy strips the header).
app.config['WTF_CSRF_SSL_STRICT'] = False
csrf = CSRFProtect(app)
csrf.exempt(api_bp)

# Ensure templates can always call csrf_token() (Flask-WTF context processor
# is not always available depending on version / init order).
app.jinja_env.globals['csrf_token'] = generate_csrf


@app.context_processor
def inject_csrf_token():
    return {'csrf_token': generate_csrf}

# Web Blueprints
from web.reports import reports_bp
from web.invoices import invoices_bp
from web.files import files_bp
from web.projects import projects_bp
app.register_blueprint(reports_bp)
app.register_blueprint(invoices_bp)
app.register_blueprint(files_bp)
app.register_blueprint(projects_bp)


@app.after_request
def set_security_headers(response):
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response


# Shared database pool
try:
    init_db()
except Exception as err:
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


# Disable strict trailing slashes
app.url_map.strict_slashes = True


# From http://flask.pocoo.org/docs/1.0/patterns/apierrors/
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


FILE_CHECK_LABELS = {
    'file_name': 'File name',
    'tif_compression': 'TIF compression',
    'tifpages': 'TIF pages',
    'magick': 'ImageMagick',
    'jhove': 'JHOVE',
    'unique_file': 'Unique file',
    'raw_pair': 'RAW pair',
    'valid_name': 'Valid name',
    'old_name': 'Old name',
    'derivative': 'Derivative',
    'prefix': 'Prefix',
    'sequence': 'Sequence',
    'tesseract': 'Tesseract',
}

FILES_TABLE_HTML_CLASSES = [
    'display', 'table', 'table-sm', 'table-hover', 'dashboard-files-table', 'w-100'
]

HOMEPAGE_TABLE_CLASSES = [
    'display', 'table', 'table-hover', 'homepage-project-table', 'w-100'
]

HOMEPAGE_FEATURED_PROJECTS = [
    {
        'title': 'Digitization of the JPC Archive is Now in Production',
        'image': 'items/Hank_Aaron.jpg',
        'image_alt': 'Photo of Hank Aaron from the JPC Archive',
        'body': ('After the successful <em>Pilot</em> and <em>Priority One</em> projects, we have started '
                 'the <em>Production 1A</em> project of the digitization of the JPC Archive. This phase will '
                 'digitize more than 328,000 reflective and transmissive photographic items.'),
        'link_type': 'dashboard',
        'project_alias': 'jpc_production',
        'link_label': 'JPCA Production Project Dashboard',
        'link_title': 'Link to the JPC Archive Production Project Dashboard',
    },
    {
        'title': 'Digitizing 200k Pollinators',
        'image': 'items/ento.png',
        'image_alt': 'Image of pollinator specimen',
        'body': ('The Mass Digi team is starting the digitization of the NMNH Entomology collection of '
                 'pollinators, including bees, butterflies, flies, and beetles. This conveyor system will '
                 'digitize thousands of specimens per week and more than 200,000 specimens within a year.'),
        'link_type': 'dashboard',
        'project_alias': 'nmnh_mdpp_ento_pollinators',
        'link_label': 'Ento Pollinators Conveyor Dashboard',
        'link_title': 'Link to the Entomology Pollinator Dashboard',
    },
    {
        'title': 'Digitization of the National Herbarium Continues',
        'image': 'items/botany_accession_sample.jpg',
        'image_alt': 'Digitized mounted specimen from the National Herbarium Collection',
        'body': ('We continue to digitize the Herbarium of the National Museum of Natural History. '
                 'The project digitizes new accessions to the collection.'),
        'link_type': 'dashboard',
        'project_alias': 'botany_accessions',
        'link_label': 'Botany Project Dashboard',
        'link_title': 'Link to the Botany Annual Accessions Project Dashboard',
    },
]


ABOUT_USER_GUIDE_URL = (
    "https://github.com/Smithsonian/Osprey/blob/master/documentation/Osprey_User_Guide/OspreyUserGuide.md"
)

ABOUT_COMPONENT_LINKS = [
    {
        'label': 'Osprey Dashboard',
        'url': 'https://github.com/Smithsonian/Osprey',
        'description': 'This web application (dashboard and API)',
    },
    {
        'label': 'Osprey Worker',
        'url': 'https://github.com/Smithsonian/Osprey_Worker/',
        'description': 'Runs file checks and posts results to the API',
    },
    {
        'label': 'Osprey Misc',
        'url': 'https://github.com/Smithsonian/Osprey_Misc/',
        'description': 'Database schema and supporting scripts',
    },
]


def _about_contact_info():
    """Contact details for the about page (override via settings.py)."""
    return {
        'name': getattr(settings, 'about_contact_name', 'Luis J. Villanueva'),
        'email': getattr(settings, 'about_contact_email', 'villanueval@si.edu'),
        'role': getattr(settings, 'about_contact_role', 'Digitization Program Office'),
    }


def _homepage_stat_value(total):
    return "{:,}".format(total or 0)


def label_file_check_column(name):
    return FILE_CHECK_LABELS.get(name, name.replace('_', ' ').title())


def prepare_files_table_df(df):
    if df is None or df.empty:
        return df
    return df.rename(columns={col: label_file_check_column(col) for col in df.columns})


def files_table_html(df):
    return prepare_files_table_df(df).to_html(
        table_id='files_table',
        index=False,
        border=0,
        escape=False,
        classes=FILES_TABLE_HTML_CLASSES)


from osprey.services.permissions import kiosk_mode, user_perms
from web.forms import LoginForm


login_manager = LoginManager()
login_manager.init_app(app)





@login_manager.user_loader
def load_user(username):
    query = ("SELECT username, user_id, user_active, full_name FROM users WHERE username = %(username)s")
    u = run_query(query, {'username': username})
    if len(u) == 1:
        return AuthBaseUser(u[0]['username'], u[0]['user_id'], u[0]['full_name'], u[0]['user_active'])
    return None


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
        return redirect(url_for('api.api_route_list'))
    
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
            'objects_digitized': _homepage_stat_value(run_query(
                "SELECT SUM(objects_digitized) as total "
                "FROM projects_stats WHERE project_id NOT IN "
                "(SELECT project_id FROM projects WHERE skip_project IS True)")[0]['total']),
            'images_captured': _homepage_stat_value(run_query(
                "SELECT SUM(images_taken) as total "
                "FROM projects_stats WHERE project_id NOT IN "
                "(SELECT project_id FROM projects WHERE skip_project IS True)")[0]['total']),
            'digitization_projects': _homepage_stat_value(run_query(
                "SELECT COUNT(*) as total FROM projects WHERE skip_project IS NOT True")[0]['total']),
            'active_projects': _homepage_stat_value(run_query(
                "SELECT COUNT(*) as total FROM projects "
                "WHERE skip_project IS NOT True AND project_status='Ongoing'")[0]['total']),
            'images_public': _homepage_stat_value(run_query(
                "SELECT SUM(images_public) as total FROM projects_stats "
                "WHERE project_id NOT IN "
                "(SELECT project_id FROM projects WHERE skip_project IS True)")[0]['total']),
        }
    elif team == "md":
        team_heading = "Summary of Mass Digitization Team Projects"
        html_title = "Mass Digitization Team Projects, Collections Digitization"

        # MD stats
        summary_stats = {
            'objects_digitized': _homepage_stat_value(run_query(
                "SELECT SUM(objects_digitized) as total FROM projects_stats WHERE project_id IN "
                "(SELECT project_id FROM projects WHERE project_section = 'MD' AND skip_project IS NOT True)"
            )[0]['total']),
            'images_captured': _homepage_stat_value(run_query(
                "SELECT SUM(images_taken) as total FROM projects_stats WHERE project_id IN "
                "(SELECT project_id FROM projects WHERE project_section = 'MD' AND skip_project IS NOT True)"
            )[0]['total']),
            'digitization_projects': _homepage_stat_value(run_query(
                "SELECT COUNT(*) as total FROM projects WHERE project_section = 'MD' AND skip_project IS NOT True"
            )[0]['total']),
            'active_projects': _homepage_stat_value(run_query(
                "SELECT COUNT(*) as total FROM projects WHERE project_section = 'MD' AND "
                "skip_project IS NOT True AND project_status='Ongoing'"
            )[0]['total']),
            'images_public': _homepage_stat_value(run_query(
                "SELECT SUM(images_public) as total FROM projects_stats WHERE project_id IN "
                "(SELECT project_id FROM projects WHERE skip_project IS NOT True AND project_section = 'MD')"
            )[0]['total']),
        }
        no_items = run_query(("SELECT SUM(objects_digitized) as total from projects_stats where project_id IN (SELECT project_id FROM projects WHERE project_section = 'MD' AND skip_project IS NOT True)"))[0]['total']
        mass_digi_total = math.floor((int(no_items)*1.0)/100000)/10

    elif team == "is":
        if subset and subset.lower() == "sawhm":
            team_heading = "Summary of Imaging Services Team Projects (SAWHM)"
        else:
            team_heading = "Summary of Imaging Services Team Projects"
        html_title = "Imaging Services Team Projects, Collections Digitization"
        summary_stats = {
            'objects_digitized': _homepage_stat_value(run_query(
                "SELECT SUM(objects_digitized) as total FROM projects_stats WHERE project_id IN "
                "(SELECT project_id FROM projects WHERE project_section = 'IS' AND skip_project IS NOT True)"
            )[0]['total']),
            'images_captured': _homepage_stat_value(run_query(
                "SELECT SUM(images_taken) as total FROM projects_stats WHERE project_id IN "
                "(SELECT project_id FROM projects WHERE project_section = 'IS' AND skip_project IS NOT True)"
            )[0]['total']),
            'digitization_projects': _homepage_stat_value(run_query(
                "SELECT COUNT(*) as total FROM projects WHERE project_section = 'IS' AND skip_project IS NOT True"
            )[0]['total']),
            'active_projects': _homepage_stat_value(run_query(
                "SELECT COUNT(*) as total FROM projects WHERE project_section = 'IS' AND "
                "skip_project IS NOT True AND project_status='Ongoing'"
            )[0]['total']),
            'images_public': _homepage_stat_value(run_query(
                "SELECT SUM(images_public) as total FROM projects_stats WHERE project_id IN "
                "(SELECT project_id FROM projects WHERE skip_project IS NOT True AND project_section = 'IS')"
            )[0]['total']),
        }

    elif team == "inf":
        team_heading = "Summary of Informatics Team Projects"
        html_title = "Summary of the Informatics Team Projects, Collections Digitization"
        # IS stats
        summary_stats = {
            'digitization_projects': _homepage_stat_value(run_query(
                "SELECT COUNT(*) as total FROM projects_informatics")[0]['total']),
            'active_projects': _homepage_stat_value(run_query(
                "SELECT COUNT(*) as total FROM projects_informatics WHERE project_status='Ongoing'"
            )[0]['total']),
            'records': _homepage_stat_value(run_query(
                "SELECT SUM(records) as total FROM projects_informatics WHERE records_redundant IS False"
            )[0]['total']),
        }

    section_query = ((" SELECT "
                     " p.projects_order, "
                     " CONCAT('<abbr title=\"', u.unit_fullname, '\">', p.project_unit, '</abbr>') as project_unit, "
                     "      CASE WHEN "
                     "             p.project_alias IS NULL "
                     "              THEN p.project_title "
                     "      ELSE "
                     "          (CASE WHEN "
                     "              p.project_status = 'Ongoing' and ps.collex_to_digitize != 0 "
                     "              THEN "
                     "              CONCAT('<a href=\"{app_root}/dashboard/', p.project_alias, '\">', p.project_title, '</a><br>"
                     "                  <small>Estimated Progress: ', ROUND((ps.objects_digitized/ps.collex_to_digitize) * 100), ' % "
                     "                  <div class=\"progress dashboard-progress\"> "
                     "                      <div class=\"progress-bar bg-success\" role=\"progressbar\" style=\"width: ', "
                     "                          ROUND((ps.objects_digitized/ps.collex_to_digitize) * 100), '%\" "
                     "                         aria-valuenow=\"', ROUND((ps.objects_digitized/ps.collex_to_digitize) * 100), '\" aria-valuemin=\"0\" aria-valuemax=\"100\"> "
                     "                      </div> "
                     "                   </div></small>"
                     "              ') "
                     "          ELSE "
                     "              CONCAT('<a href=\"{app_root}/dashboard/', p.project_alias, '\">', p.project_title, '</a>') "
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
        "project_manager": "<abbr title=\"Project Manager\">PM</abbr>",
        "project_dates": "Dates",
        "objects_digitized": "Specimens/Objects Digitized",
        "images_taken": "Images Captured"
    })

    if subset is None:
        subset = ""
    is_section_query = section_query
    if subset.lower() == "sawhm":
        is_section_query = section_query.replace(
            "WHERE p.skip_project = 0 AND p.project_section = %(section)s",
            "WHERE p.skip_project = 0 AND p.project_section = %(section)s AND p.project_unit = 'SAWHM'",
        )
    list_projects_is = pd.DataFrame(run_query(is_section_query, {'section': 'IS'}))
    list_projects_is = list_projects_is.drop("images_public", axis=1)

    list_projects_is = list_projects_is.rename(columns={
        "project_unit": "Unit",
        "project_title": "Title",
        "project_status": "Status",
        "project_manager": "<abbr title=\"Project Manager\">PM</abbr>",
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
    is_table_title = "Imaging Services Projects"
    if subset.lower() == "sawhm":
        is_table_title = "Imaging Services Projects (SAWHM projects only)"

    return render_template('home.html',
                           form=form, msg=msg, user_exists=user_exists,
                           username=username, summary_stats=summary_stats, team=team,
                           tables_md=[list_projects_md.to_html(table_id='list_projects_md', index=False,
                                                               border=0, escape=False,
                                                               classes=HOMEPAGE_TABLE_CLASSES)],
                           tables_is=[list_projects_is.to_html(table_id='list_projects_is', index=False,
                                                               border=0, escape=False,
                                                               classes=HOMEPAGE_TABLE_CLASSES)],
                           tables_inf=[list_projects_inf.to_html(table_id='list_projects_inf', index=False,
                                                               border=0, escape=False,
                                                               classes=HOMEPAGE_TABLE_CLASSES)],
                           tables_software=[list_software.to_html(table_id='list_software', index=False,
                                                               border=0, escape=False,
                                                               classes=HOMEPAGE_TABLE_CLASSES + ['homepage-software-table'])],
                           featured_projects=HOMEPAGE_FEATURED_PROJECTS,
                           is_table_title=is_table_title,
                           asklogin=asklogin, site_env=site_env, site_net=site_net, site_ver=site_ver,
                           last_update=last_update[0]['updated_at'] or 'unknown',
                           mass_digi_total=mass_digi_total,
                           kiosk=kiosk, user_address=user_address, team_heading=team_heading,
                           html_title=html_title, analytics_code=settings.analytics_code,
                           app_root=settings.app_root,
                           subset=subset.upper())


@app.route('/login', methods=['POST'], provide_automatic_options=False)
def login():
    """Login into the system with LDAP (internal deployments only)."""
    if site_net == "api":
        return redirect(url_for('api.api_route_list'))

    if site_net == "external":
        logger.warning("Login attempted on external site")
        return redirect(url_for('homepage'))

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
        logger.info("LDAP (user): {}".format(username))
        query = ("SELECT user_id, username, user_active, full_name FROM users WHERE email = %(email)s")
        user = run_query(query, {'email': username})
        logger.info("Trying to log in: {}".format(username))
        if len(user) == 1:
            if not get_auth_service().authenticate_user(username, password):
                logger.error("Login error - LDAP")
                return redirect(url_for('not_user'))
            username = user[0]['username']
            logger.info(user[0]['user_active'])
            if user[0]['user_active']:
                user_obj = AuthBaseUser(user[0]['username'], user[0]['user_id'],
                                user[0]['full_name'], user[0]['user_active'])
                login_user(user_obj)
                return redirect(url_for('home'))
            else:
                logger.error("Login error - user not active")
                return redirect(url_for('not_user'))
        else:
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
        return redirect(url_for('api.api_route_list'))

    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Declare the login form
    # form = LoginForm(request.form)
    form = None

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
            files_count = run_query("SELECT count(*) as no_files FROM transcription_files WHERE folder_transcription_id = %(folder_id)s",
                                {'folder_id': folder_id})[0]
        else:
            files_count = run_query("SELECT count(*) as no_files FROM files WHERE folder_id = %(folder_id)s",
                                {'folder_id': folder_id})[0]

        files_count = files_count['no_files']
        if tab == "filechecks":
            project_postprocessing = []
            page_no = "File Checks"
            if files_count == 0:
                pagination_html = ""
                files_df = ""
                folder_stats = {'no_files': 0, 'no_errors': 0}
            else:
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
            page_no = "Lightbox"
        elif tab == "postprod":
            page_no = "Post-Processing Steps"
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

    # Reports (per-project data_reports + built-in reports)
    reports = report_service.list_project_reports(project_id)
    proj_reports = len(reports) > 0

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
                           tables=[],
                           file_check_labels=FILE_CHECK_LABELS,
                           app_root=settings.app_root,
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
                           project_disk=project_disk,
                           projects_links=projects_links,
                           project_manager_link=project_manager_link,
                           analytics_code=settings.analytics_code,
                           project_stats_other=project_stats_other,
                           folder_badges=folder_badges,
                           transcription=transcription
                           )


@cache.memoize()
@app.route('/dashboard/<project_alias>/', methods=['GET', 'POST'], provide_automatic_options=False)
def dashboard(project_alias=None, folder_id=None):
    """Dashboard for a project"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api.api_route_list'))
    
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
    # form = LoginForm(request.form)
    form = None

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

    # Reports (per-project data_reports + built-in reports)
    reports = report_service.list_project_reports(project_id)
    proj_reports = len(reports) > 0

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
                           tables=[files_table_html(folder_files_df)],
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
        return redirect(url_for('api.api_route_list'))

    # Declare the login form
    form = LoginForm(request.form)

    from osprey.services import project_statistics as stats_service

    ctx = stats_service.load_statistics_page_context(project_alias)
    if not ctx.get('found'):
        error_msg = "Project was not found."
        return render_template(
            'error.html',
            error_msg=error_msg,
            project_alias=project_alias,
            site_env=site_env,
            site_net=site_net,
            site_ver=site_ver,
            analytics_code=settings.analytics_code,
        ), 404

    return render_template(
        'statistics.html',
        form=form,
        site_env=site_env,
        site_net=site_net,
        site_ver=site_ver,
        analytics_code=settings.analytics_code,
        **{k: v for k, v in ctx.items() if k != 'found'},
    )


@cache.memoize()
@app.route('/dashboard/<project_id>/statistics/<step_id>', methods=['POST', 'GET'], provide_automatic_options=False)
def proj_statistics_dl(project_id=None, step_id=None):
    """Download statistics for a project"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api.api_route_list'))

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
@app.route('/about/', methods=['GET'], provide_automatic_options=False)
def about():
    """About page for the system"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api.api_route_list'))
    
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
    if settings.site_net == "internal":
        asklogin = True
    else:
        asklogin = False
    site_env_label = "Production" if site_env == "prod" else site_env.replace("_", " ").title()
    return render_template(
        'about.html',
        form=form,
        username=username,
        site_net=site_net,
        site_env=site_env,
        site_env_label=site_env_label,
        site_ver=site_ver,
        kiosk=kiosk,
        user_address=user_address,
        analytics_code=settings.analytics_code,
        asklogin=asklogin,
        about_contact=_about_contact_info(),
        about_user_guide_url=ABOUT_USER_GUIDE_URL,
        about_component_links=ABOUT_COMPONENT_LINKS,
    )


@app.route('/qc/<project_alias>/', methods=['POST', 'GET'], provide_automatic_options=False)
@login_required
def qc(project_alias=None):
    """List the folders and QC status"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api.api_route_list'))
    
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
                                   {'username': username, 'project_alias': project_alias})[0]
    if project_admin['no_results'] == 0:
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
                                " SELECT f.folder_transcription_id as folder_id, f.folder, f.preview_type, f.delivered_to_dams, "
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
                                     " qc as (SELECT f.folder_transcription_id as folder_id, f.folder, f.preview_type, f.delivered_to_dams, "
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
                                     "  ORDER BY date ASC, folder ASC"),
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
                                     " qc as (SELECT f.folder_transcription_id as folder_id, f.folder, f.preview_type, f.delivered_to_dams, "
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
                                " SELECT f.folder_id, f.project_folder, f.preview_type, f.delivered_to_dams, "
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
                                     " qc as (SELECT f.folder_id, f.project_folder, f.preview_type, f.delivered_to_dams, "
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
                                     "  ORDER BY date ASC, project_folder ASC"),
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
                                     " qc as (SELECT f.folder_id, f.project_folder, f.preview_type, f.delivered_to_dams, "
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
                                     " SELECT *, DATEDIFF(NOW(), updated_at) as days_since FROM qc WHERE qc_status = 'QC Pending' and qc_by is not null "
                                     "  ORDER BY date ASC, project_folder ASC"),
                                    {'project_id': project_id})

        return render_template('qc.html', username=username,
                            project_settings=project_settings,
                            folder_qc_info=folder_qc_info, folder_qc_pending=folder_qc_pending,
                            folder_qc_done=folder_qc_done[:100], folder_qc_done_len=len(folder_qc_done),
                            project=project, form=form, project_qc_stats=project_qc_stats,
                            site_env=site_env, site_net=site_net, site_ver=site_ver,
                            analytics_code=settings.analytics_code)


@app.route('/qc_transcription/<project_alias>/', methods=['POST', 'GET'], provide_automatic_options=False)
@login_required
def qc_transcription(project_alias=None):
    """List the folders and QC status"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api.api_route_list'))
    
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
                                   {'username': username, 'project_alias': project_alias})[0]
    if project_admin['no_results'] == 0:
        # Not allowed
        return redirect(url_for('home'))

    project_settings = run_query(("SELECT * FROM transcription_qc_settings "
                                 " WHERE project_id = %(project_id)s"),
                                {'project_id': project_id})

    if len(project_settings) == 0:
        query = ("INSERT INTO transcription_qc_settings (project_id, qc_level, qc_percent, "
                 " qc_threshold_critical, qc_threshold_major, qc_threshold_minor, "
                 " qc_normal_percent, qc_reduced_percent, qc_tightened_percent, updated_at) "
                 "  VALUES ("
                 "  %(project_id)s, 'Tightened', 40, 0, 1.5, 4, 10, 5, 40, "
                 "  CURRENT_TIME)")
        q = query_database_insert(query, {'project_id': project_id})
        project_settings = run_query(("SELECT * FROM transcription_qc_settings "
                                      " WHERE project_id = %(project_id)s"),
                                     {'project_id': project_id})

    project_settings = project_settings[0]

    project_qc_stats = {}
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
    
    project_qc_stats['total'] = project_qc_count['no_folders']
    project_qc_stats['ok'] = project_qc_ok['no_folders']
    project_qc_stats['failed'] = project_qc_failed['no_folders']

    project_qc_stats['pending'] = project_qc_stats['total'] - (project_qc_stats['ok'] + project_qc_stats['failed'])

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
                            " SELECT f.folder_transcription_id as folder_id, f.folder, f.preview_type, f.delivered_to_dams, "
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
                                    " qc as (SELECT f.folder_transcription_id as folder_id, f.folder, f.preview_type, f.delivered_to_dams, "
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
                                     " qc as (SELECT f.folder_transcription_id as folder_id, f.folder, f.preview_type, f.delivered_to_dams, "
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
    

    t_sources = run_query("SELECT transcription_source_id, transcription_source_name, CONCAT(transcription_source_notes, ' ', transcription_source_date) as source_notes FROM transcription_sources WHERE project_id = %(project_id)s", {'project_id': project_id})

    return render_template('qc_file_transcription_text_prep.html', username=username,
                            project_settings=project_settings,
                            t_sources=t_sources,
                            folder_qc_info=folder_qc_info, folder_qc_pending=folder_qc_pending,
                            folder_qc_done=folder_qc_done[:100], folder_qc_done_len=len(folder_qc_done),
                            project=project, form=form, project_qc_stats=project_qc_stats,
                            site_env=site_env, site_net=site_net, site_ver=site_ver,
                            analytics_code=settings.analytics_code)


@app.route('/qc_transcription_list/<source_id>/', methods=['POST', 'GET'], provide_automatic_options=False)
@login_required
def qct_loading2(source_id):
    """Prepare QC for a folder"""
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api.api_route_list'))
    username = current_user.name

    # Declare the login form
    form = LoginForm(request.form)

    try:
        # Allow for UUIDs
        source_id = UUID(source_id)
    except:
        raise InvalidUsage('invalid source_id value', status_code=400)
    source_id = str(source_id)

    project_admin = run_query(("SELECT p.project_id "
                                    "    FROM users u, transcription_sources ts, projects p, qc_projects qcp "
                                    "    WHERE u.username = %(username)s "
                                    "        AND ts.transcription_source_id = %(source_id)s "
                                    "        AND ts.project_id = p.project_id "
                                    "        AND ts.project_id = qcp.project_id "
                                    "        AND u.user_id = qcp.user_id"),
                                   {'username': username, 'source_id': source_id})
    if len(project_admin) == 0:
        # Not allowed
        return redirect(url_for('home'))
    else:
        project_id = project_admin[0]['project_id']

    project = run_query("SELECT * FROM projects WHERE project_id = %(project_id)s", {'project_id': project_id})[0]

    source_info = run_query("SELECT * FROM transcription_sources WHERE transcription_source_id = %(source_id)s", {'source_id': source_id})[0]

    project_settings = run_query(("SELECT * FROM transcription_qc_settings "
                                 " WHERE project_id = %(project_id)s"),
                                {'project_id': project_id})

    if len(project_settings) == 0:
        query = ("INSERT INTO transcription_qc_settings (project_id, qc_level, qc_percent, "
                 " qc_threshold_critical, qc_threshold_major, qc_threshold_minor, "
                 " qc_normal_percent, qc_reduced_percent, qc_tightened_percent, updated_at) "
                 "  VALUES ("
                 "  %(project_id)s, 'Tightened', 40, 0, 1.5, 4, 10, 5, 40, "
                 "  CURRENT_TIME)")
        q = query_database_insert(query, {'project_id': project_id})
        project_settings = run_query(("SELECT * FROM transcription_qc_settings "
                                      " WHERE project_id = %(project_id)s"),
                                     {'project_id': project_id})

    project_settings = project_settings[0]

    project_qc_stats = {}
    project_qc_ok = run_query(("SELECT count(f.folder_transcription_id) as no_folders FROM transcription_folders f "
                            " JOIN transcription_qc_folders q on (f.folder_transcription_id = q.folder_transcription_id ) "
                            " JOIN transcription_sources ts on (f.project_id = ts.project_id ) "
                            " WHERE f.project_id = %(project_id)s and ts.transcription_source_id = %(transcription_source_id)s "
                            " and f.status = 0 and f.previews = 0 and f.file_errors = 0 and q.qc_status = 0"),
                            {'project_id': project_id, 'transcription_source_id': source_id})[0]
    project_qc_failed = run_query(("SELECT count(f.folder_transcription_id) as no_folders FROM transcription_folders f "
                            " JOIN transcription_qc_folders q on (f.folder_transcription_id = q.folder_transcription_id ) "
                            " JOIN transcription_sources ts on (f.project_id = ts.project_id ) "
                            " WHERE f.project_id = %(project_id)s and ts.transcription_source_id = %(transcription_source_id)s "
                            " and f.status = 0 and f.previews = 0 and f.file_errors = 0 and q.qc_status = 1"),
                            {'project_id': project_id, 'transcription_source_id': source_id})[0]
    project_qc_count = run_query((
        "SELECT count(distinct f.folder_transcription_id) as no_folders "
        " FROM transcription_folders f, transcription_qc_folders qcf, transcription_sources ts "
        " WHERE f.project_id = ts.project_id AND f.project_id = %(project_id)s AND "
        "        f.folder_transcription_id = qcf.folder_transcription_id and f.status = 0 AND "
        "        f.file_errors = 0 and f.previews = 0 AND qcf.transcription_source_id = %(transcription_source_id)s"),
        {'project_id': project_id, 'transcription_source_id': source_id})[0]

    project_qc_stats['total'] = project_qc_count['no_folders']
    project_qc_stats['ok'] = project_qc_ok['no_folders']
    project_qc_stats['failed'] = project_qc_failed['no_folders']

    project_qc_stats['pending'] = project_qc_stats['total'] - (project_qc_stats['ok'] + project_qc_stats['failed'])
    
    folder_qc_done = run_query(("WITH pfolders AS (SELECT f.folder_transcription_id from transcription_folders f, transcription_qc_folders qcf WHERE f.project_id = %(project_id)s" 
                                    "  AND f.folder_transcription_id = qcf.folder_transcription_id AND qcf.transcription_source_id = %(transcription_source_id)s ),"
                                " errors AS "
                                    "         (SELECT f.folder_transcription_id, count(qc.file_transcription_id) as no_files "
                                    "             FROM transcription_files f, transcription_qc qc "
                                    "             WHERE f.folder_transcription_id IN (SELECT folder_transcription_id from pfolders) "
                                    "                 AND qc_results > 0 AND qc_results != 9 " 
                                    "                  AND f.file_transcription_id = qc.file_transcription_id "
                                    "               GROUP BY folder_transcription_id),"
                                    "passed AS "
                                    "         (SELECT f.folder_transcription_id, count(f.file_transcription_id) as no_files "
                                    "             FROM transcription_files f, transcription_qc qc "
                                    "             WHERE f.folder_transcription_id IN (SELECT folder_transcription_id from pfolders) "
                                    "                 AND qc_results = 0 "
                                    "                  AND f.file_transcription_id = qc.file_transcription_id"
                                    "               GROUP BY folder_transcription_id),"
                                    "total AS (SELECT folder_transcription_id, count(file_transcription_id) as no_files FROM transcription_files "
                                    "             WHERE folder_transcription_id IN (SELECT folder_transcription_id from pfolders)"
                                    "                GROUP BY folder_transcription_id), "
                                    " files_total AS (SELECT folder_transcription_id, count(file_transcription_id) as no_files FROM transcription_files "
                                    "             WHERE folder_transcription_id IN (SELECT folder_transcription_id from pfolders)"
                                    "                GROUP BY folder_transcription_id) "
                                " SELECT f.folder_transcription_id as folder_id, f.folder, f.preview_type, f.delivered_to_dams, "
                                "       ft.no_files, f.file_errors, f.status, f.error_info, q.qc_level, "
                                "   CASE WHEN q.qc_status = 0 THEN 'QC Passed' "
                                "      WHEN q.qc_status = 1 THEN 'QC Failed' "
                                "      ELSE 'QC Pending' END AS qc_status, "
                                "      q.qc_ip, u.username AS qc_by, "
                                "      date_format(q.updated_at, '%Y-%m-%d') AS updated_at, "
                                "       COALESCE(errors.no_files, 0) as qc_stats_no_errors, "
                                "       COALESCE(passed.no_files, 0) as qc_stats_no_passed,"
                                "       COALESCE(total.no_files, 0) as qc_stats_no_files "
                                " FROM transcription_folders f LEFT JOIN transcription_qc_folders q ON "
                                "       (f.folder_transcription_id = q.folder_transcription_id)"
                                "       LEFT JOIN users u ON "
                                "           (q.qc_by = u.user_id)"
                                "       LEFT JOIN errors ON "
                                "           (f.folder_transcription_id = errors.folder_transcription_id)"
                                "       LEFT JOIN passed ON "
                                "           (f.folder_transcription_id = passed.folder_transcription_id)"
                                "       LEFT JOIN total ON "
                                "           (f.folder_transcription_id = total.folder_transcription_id)"
                                "       LEFT JOIN files_total ft ON "
                                "           (f.folder_transcription_id = ft.folder_transcription_id), "
                                "   projects p "
                                " WHERE f.project_id = p.project_id "
                                "   AND p.project_id = %(project_id)s "
                                "   AND q.qc_status != 9 "
                                "  ORDER BY f.date DESC, f.folder DESC"),
                               {'project_id': project_id, 'transcription_source_id': source_id})
    folder_qc_info = run_query(("WITH pfolders AS (SELECT f.folder_transcription_id from transcription_folders f, transcription_qc_folders qcf WHERE f.project_id = %(project_id)s" 
                                    "  AND f.folder_transcription_id = qcf.folder_transcription_id AND qcf.transcription_source_id = %(transcription_source_id)s ),"
                                    " errors AS "
                                    "         (SELECT f.folder_transcription_id, count(qc.file_transcription_id) as no_files "
                                    "             FROM transcription_files f, transcription_qc qc "
                                    "             WHERE f.folder_transcription_id IN (SELECT folder_transcription_id from pfolders) "
                                    "                 AND qc_results > 0 AND qc_results != 9 " 
                                    "                  AND f.file_transcription_id = qc.file_transcription_id "
                                    "               GROUP BY folder_transcription_id),"
                                    " passed AS "
                                    "         (SELECT f.folder_transcription_id, count(f.file_transcription_id) as no_files "
                                    "             FROM transcription_files f, transcription_qc qc "
                                    "             WHERE f.folder_transcription_id IN (SELECT folder_transcription_id from pfolders) "
                                    "                 AND qc_results = 0 "
                                    "                  AND f.file_transcription_id = qc.file_transcription_id"
                                    "               GROUP BY folder_transcription_id),"
                                    "total AS (SELECT folder_transcription_id, count(file_transcription_id) as no_files FROM transcription_files "
                                    "             WHERE folder_transcription_id IN (SELECT folder_transcription_id from pfolders)"
                                    "                GROUP BY folder_transcription_id), "
                                    " files_total AS (SELECT folder_transcription_id, count(file_transcription_id) as no_files FROM transcription_files "
                                    "             WHERE folder_transcription_id IN (SELECT folder_transcription_id from pfolders)"
                                    "                GROUP BY folder_transcription_id), "
                                    " qc as (SELECT f.folder_transcription_id, f.folder, f.preview_type, f.delivered_to_dams, "
                                    "       ft.no_files, f.file_errors, f.status, f.date, f.error_info, "
                                    "   CASE WHEN q.qc_status = 0 THEN 'QC Passed' "
                                    "      WHEN q.qc_status = 1 THEN 'QC Failed' "
                                    "      ELSE 'QC Pending' END AS qc_status, "
                                    "      q.qc_ip, u.username AS qc_by, "
                                    "      date_format(q.updated_at, '%Y-%m-%d') AS updated_at, "
                                    "       COALESCE(errors.no_files, 0) as qc_stats_no_errors, "
                                    "       COALESCE(passed.no_files, 0) as qc_stats_no_passed,"
                                    "       COALESCE(total.no_files, 0) as qc_stats_no_files "
                                    " FROM transcription_folders f LEFT JOIN transcription_qc_folders q ON "
                                    "       (f.folder_transcription_id = q.folder_transcription_id)"
                                    "       LEFT JOIN users u ON "
                                    "           (q.qc_by = u.user_id)"
                                    "       LEFT JOIN errors ON "
                                    "           (f.folder_transcription_id = errors.folder_transcription_id)"
                                    "       LEFT JOIN passed ON "
                                    "           (f.folder_transcription_id = passed.folder_transcription_id)"
                                    "       LEFT JOIN total ON "
                                    "           (f.folder_transcription_id = total.folder_transcription_id)"
                                    "       LEFT JOIN files_total ft ON "
                                    "           (f.folder_transcription_id = ft.folder_transcription_id), "
                                    "   projects p "
                                    " WHERE f.project_id = p.project_id AND f.file_errors = 0 AND f.status = 0 AND f.previews = 0 "
                                    "   AND p.project_id = %(project_id)s) "
                                    " SELECT *, folder as project_folder FROM qc WHERE qc_status = 'QC Pending' and qc_by is null "
                                    "  and no_files > 0 "
                                    "  and folder_transcription_id not in (SELECT folder_uid from folders_badges where badge_type = 'folder_error' AND folder_uid IS NOT NULL) "
                                    "  and folder_transcription_id not in (SELECT folder_uid from folders_badges where badge_type = 'verification' AND folder_uid IS NOT NULL) "
                                    "  ORDER BY date ASC, folder ASC LIMIT 10"),
                                {'project_id': project_id, 'transcription_source_id': source_id})
    folder_qc_pending = run_query(("select tqf.*, u.username, tf.folder from transcription_folders tf, transcription_qc_folders tqf, users u "
                                       " where tqf.qc_by is not null and tqf.folder_transcription_id = tf.folder_transcription_id and "
                                       " tqf.qc_by = u.user_id AND tqf.qc_status = 9 " 
                                       " and tf.project_id = %(project_id)s and tqf.transcription_source_id = %(transcription_source_id)s"),
                                    {'project_id': project_id, 'transcription_source_id': source_id})
    
    return render_template('qc_file_transcription_text_select.html', username=username,
                    project_settings=project_settings, source_info=source_info,
                    folder_qc_info=folder_qc_info, folder_qc_pending=folder_qc_pending,
                    folder_qc_done=folder_qc_done[:100], folder_qc_done_len=len(folder_qc_done),
                    project=project, form=form, project_qc_stats=project_qc_stats, source_id=source_id, 
                    site_env=site_env, site_net=site_net, site_ver=site_ver,
                    analytics_code=settings.analytics_code)


@app.route('/qc_process/<folder_id>/', methods=['GET', 'POST'], provide_automatic_options=False)
@login_required
def qc_process(folder_id):
    """Run QC on a folder"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api.api_route_list'))
    
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
        if transcription == 1:
            q = query_database_insert(("UPDATE qc_folders SET qc_by = %(qc_by)s "
                                " WHERE folder_uid = %(folder_id)s"),
                            {'folder_id': folder_id,
                                'qc_by': current_user.id
                                })
        else:
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
            # return redirect(url_for('qc_loading1', folder_id=folder_id))
            return redirect(url_for('qc_loading2', folder_id=folder_id))
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
                                            "     AND f.folder_transcription_id = %(folder_id)s AND q.file_qc = 9 order by f.file_transcription_id "
                                            "  LIMIT 1 "),
                                            {'folder_id': folder_id})[0]
                    file_details = run_query(("SELECT f.file_transcription_id as file_id, f.folder_transcription_id as folder_id, f.file_name, NULL as sensitive_contents, "
                                                "       NULL as preview_image_ext, DATEDIFF(NOW(), f.created_at) as datediff "
                                                " FROM transcription_files f WHERE f.file_transcription_id = %(file_id)s"),
                                                {'file_id': file_qc['file_id']})[0]
                    file_checks = run_query(("SELECT file_check, check_results, "
                                                "       CASE WHEN check_info = '' THEN 'Check passed.' "
                                                "           ELSE check_info END AS check_info "
                                                "   FROM transcription_files_checks WHERE file_transcription_id = %(file_id)s"),
                                                {'file_id': file_qc['file_id']})
                    file_metadata = pd.DataFrame(run_query(("SELECT tag, taggroup, tagid, value "
                                                                "   FROM files_exif "
                                                                "   WHERE file_uid = %(file_id)s "
                                                                "       AND lower(filetype) = 'tif' "
                                                                "   ORDER BY taggroup, tag "),
                                                            {'file_id': file_qc['file_id']}))
                    folder = run_query(
                        ("SELECT folder_transcription_id as folder_id, folder as project_folder, delivered_to_dams FROM transcription_folders "
                        "  WHERE folder_transcription_id IN (SELECT folder_transcription_id FROM transcription_files WHERE file_transcription_id = %(file_id)s)"),
                        {'file_id': file_qc['file_id']})[0]

                    viewer = resolve_image_viewer(
                        file_details['folder_id'],
                        file_qc['file_id'],
                        file_details['file_name'],
                        transcription=True,
                    )
                    zoom_exists = viewer['zoom_exists']
                    zoom_filename = viewer['zoom_filename']
                    iiif_image = viewer['iiif_image']
                else:
                    file_qc = run_query(("SELECT f.file_id FROM qc_files q, files f "
                                            "  WHERE q.file_id = f.file_id "
                                            "     AND f.folder_id = %(folder_id)s AND q.file_qc = 9 order by file_id "
                                            "  LIMIT 1 "),
                                            {'folder_id': folder_id})[0]
                    file_details = run_query(("SELECT f.file_id, f.folder_id, f.file_name, f.preview_image as preview_image_ext, "
                                                "       DATEDIFF(NOW(), f.created_at) as datediff, COALESCE(s.sensitive_contents, 0) as sensitive_contents "
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

                    viewer = resolve_image_viewer(
                        file_details['folder_id'],
                        file_qc['file_id'],
                        file_details['file_name'],
                        transcription=False,
                    )
                    zoom_exists = viewer['zoom_exists']
                    zoom_filename = viewer['zoom_filename']
                    iiif_image = viewer['iiif_image']

                file_details['preview_img_path'] = static_preview_path(file_details['folder_id'], file_qc['file_id'], size="160", transcription=(transcription == 1))
                file_details['preview_img_path_600'] = static_preview_path(file_details['folder_id'], file_qc['file_id'], size="600", transcription=(transcription == 1))
                file_details['fullsize_img_path'] = static_fullsize_path(file_details['folder_id'], file_qc['file_id'], transcription=(transcription == 1))

                return render_template("qc_file.html",
                                        zoom_exists=zoom_exists, zoom_filename=zoom_filename,
                                        iiif_image=iiif_image,
                                        folder=folder, qc_stats=qc_stats,
                                        folder_id=folder_id, file_qc=file_qc, project_settings=project_settings,
                                        file_details=file_details, file_checks=file_checks, username=username,
                                        project_alias=project_alias['project_alias'],
                                        tables=[file_metadata.to_html(table_id='file_metadata', index=False, border=0,
                                                                        escape=False,
                                                                        classes=["display", "compact", "table-striped"])],
                                        file_metadata_rows=file_metadata.shape[0],
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
                    folder = run_query("SELECT *, folder_transcription_id as folder_id FROM transcription_folders WHERE folder_transcription_id = %(folder_id)s",
                                    {'folder_id': folder_id})[0]
                else:
                    error_files = run_query(("SELECT f.file_name, "
                                         " CASE WHEN q.file_qc = 1 THEN 'Critical Issue' "
                                         " WHEN q.file_qc = 2 THEN 'Major Issue' "
                                         " WHEN q.file_qc = 3 THEN 'Minor Issue' END as file_qc, "
                                         " q.qc_info FROM qc_files q, files f "
                                              "  WHERE q.folder_id = %(folder_id)s "
                                              "  AND q.file_qc > 0 AND q.file_id = f.file_id"),
                                             {'folder_id': folder_id})
                    folder = run_query("SELECT * FROM folders WHERE folder_id = %(folder_id)s",
                                    {'folder_id': folder_id})[0]
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
                qc_threshold_critical_comparison = math.floor(qc_stats['no_files'] * (float(project_settings['qc_threshold_critical']) / 100))
                qc_threshold_major_comparison = math.floor(qc_stats['no_files'] * (float(project_settings['qc_threshold_major']) / 100))
                qc_threshold_minor_comparison = math.floor(qc_stats['no_files'] * (float(project_settings['qc_threshold_minor']) / 100))
                if crit_files > 0:
                    if qc_threshold_critical_comparison <= crit_files:
                        qc_folder_result = False
                if major_files > 0:
                    if qc_threshold_major_comparison <= major_files:
                        qc_folder_result = False
                if minor_files > 0:
                    if qc_threshold_minor_comparison <= minor_files:
                        qc_folder_result = False
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



@app.route('/qc_process_transcription/<source_id>/<folder_id>', methods=['GET', 'POST'], provide_automatic_options=False)
@login_required
def qc_process_transcript(source_id, folder_id):
    """Run QC on a transcription folder"""
    
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api.api_route_list'))
    
    if current_user.is_authenticated:
        user_exists = True
        username = current_user.name
    else:
        user_exists = False
        username = None

    # Declare the login form
    form = LoginForm(request.form)

    try:
        # Allow for UUIDs
        folder_id = UUID(folder_id)
        folder_id = str(folder_id)
        source_id = UUID(source_id)
        source_id = str(source_id)
    except:
        raise InvalidUsage('invalid source_id or folder_id value', status_code=400)
    
    username = current_user.name
    
    project_admin = run_query(("SELECT count(*) as no_results FROM users u, qc_projects p, transcription_folders f "
                                "    WHERE u.username = %(username)s "
                                "        AND p.project_id = f.project_id "
                                "        AND f.folder_transcription_id = %(folder_id)s "
                                "        AND u.user_id = p.user_id"),
                                {'username': username, 'folder_id': folder_id})[0]

    if project_admin['no_results'] == 0:
        # Not allowed
        return redirect(url_for('home'))
    file_id_q = request.values.get('file_id')
    msg = ""
    # check if folder is owned, assigned otherwise
    folder_owner = run_query(("SELECT f.*, u.username from transcription_qc_folders f, users u "
                                    "    WHERE u.user_id = f.qc_by "
                                    "        AND f.folder_transcription_id = %(folder_id)s "
                                    "        AND f.transcription_source_id = %(source_id)s"),
                                {'folder_id': folder_id, 'source_id': source_id})
    
    if len(folder_owner) == 1:
        if folder_owner[0]['username'] != username:
            # Not allowed
            return redirect(url_for('qct_loading2', source_id = source_id))
    else:
        # Assign user
        q = query_database_insert(("UPDATE transcription_qc_folders SET qc_by = %(qc_by)s "
                                " WHERE folder_transcription_id = %(folder_id)s "
                                "   AND transcription_source_id = %(source_id)s"),
                            {'folder_id': folder_id,
                                'source_id': source_id,
                                'qc_by': current_user.id
                                })
    
    
    project_id = run_query("SELECT project_id from transcription_folders WHERE folder_transcription_id = %(folder_id)s",
                                {'folder_id': folder_id})[0]
    
    # File submitted
    if file_id_q is not None:

        qc_info = request.values.get('qc_info')
        qc_val = request.values.get('qc_val')
        if str(project_id['project_id']) == "250":
            alembo_cat = request.values.get('alembo_cat')
            alembo_cat_t = (alembo_cat is None)
            logger.info(f"{alembo_cat},{alembo_cat_t},{qc_info},{file_id_q}")
            if qc_info != "" and alembo_cat == "NA":
                msg = "Error: The field Issue or Comment Category can not be empty if QC Details is filled.<br>Please try again."
            else:
                user_id = run_query("SELECT user_id FROM users WHERE username = %(username)s",
                                        {'username': username})[0]
                if qc_val != "0" and qc_info == "":
                    msg = "Error: The field QC Details can not be empty if the file has an issue.<br>Please try again."
                else:
                    q = query_database_insert(("UPDATE transcription_qc SET "
                                    "      qc_results = %(qc_val)s, "
                                    "      qc_notes = %(qc_info)s "
                                    " WHERE file_transcription_id = %(file_id)s and transcription_source_id = %(source_id)s"),
                                    {'file_id': file_id_q,
                                    'qc_info': f"{alembo_cat}|{qc_info}",
                                    'qc_val': qc_val,
                                    'source_id': source_id
                                    })
                
                    logger.info(f"file_id: {file_id_q}|source_id: {source_id}|folder_id: {folder_id}")
                    return redirect(url_for('qc_process_transcript', source_id=source_id, folder_id=folder_id))
        else:
            user_id = run_query("SELECT user_id FROM users WHERE username = %(username)s",
                                    {'username': username})[0]
            if qc_val != "0" and qc_info == "":
                msg = "Error: The field QC Details can not be empty if the file has an issue.<br>Please try again."
            else:
                q = query_database_insert(("UPDATE transcription_qc SET "
                                "      qc_results = %(qc_val)s, "
                                "      qc_notes = %(qc_info)s "
                                " WHERE file_transcription_id = %(file_id)s and transcription_source_id = %(source_id)s"),
                                {'file_id': file_id_q,
                                'qc_info': qc_info,
                                'qc_val': qc_val,
                                'source_id': source_id
                                })
            
                logger.info(f"file_id: {file_id_q}|source_id: {source_id}|folder_id: {folder_id}")
                return redirect(url_for('qc_process_transcript', source_id=source_id, folder_id=folder_id))
    
    project_settings = run_query("SELECT * FROM transcription_qc_settings WHERE project_id = %(project_id)s",
                                      {'project_id': project_id['project_id']})[0]

    folder_qc_check = run_query(("SELECT "
                                      "  CASE WHEN q.qc_status = 0 THEN 'QC Passed' "
                                      "          WHEN q.qc_status = 1 THEN 'QC Failed' "
                                      "          ELSE 'QC Pending' END AS qc_status, "
                                      "      qc_ip, u.username AS qc_by, "
                                      "      date_format(q.updated_at, '%Y-%m-%d') AS updated_at"
                                      " FROM transcription_qc_folders q, "
                                      "      users u WHERE q.qc_by=u.user_id "
                                      "      AND q.folder_transcription_id = %(folder_id)s "
                                      "      AND q.transcription_source_id = %(source_id)s"),
                                     {'folder_id': folder_id, 'source_id': source_id})
    
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

    folder_stats = {
        'no_files': folder_stats1[0]['no_files'],
        'no_errors': folder_stats2[0]['no_errors']
    }
    logger.info("qc_status: {} | no_files: {}".format(folder_qc['qc_status'], folder_stats['no_files']))
    
    project_qc_settings = run_query(("SELECT * FROM transcription_qc_settings WHERE project_id = %(project_id)s"),
                                    {'project_id': project_id['project_id']})[0]
    
    if folder_qc['qc_status'] == "QC Pending" and folder_stats['no_files'] > 0:
        # Setup the files for QC
        in_qc = run_query(
            "SELECT count(*) as no_files FROM transcription_qc "
            " WHERE folder_transcription_id = %(folder_id)s "
            "   AND transcription_source_id = %(source_id)s",
            {'folder_id': folder_id, 'source_id': source_id})
    
        if in_qc[0]['no_files'] == 0:
            q = query_database_insert("DELETE FROM transcription_qc_folders WHERE folder_transcription_id = %(folder_id)s and transcription_source_id = %(source_id)s",
                                {'folder_id': folder_id, 'source_id': source_id})
            q = query_database_insert("INSERT INTO transcription_qc_folders (folder_transcription_id, transcription_source_id, qc_status, qc_level) VALUES (%(folder_id)s, %(source_id)s, 9, %(qc_level)s)",
                                {'folder_id': folder_id, 'source_id': source_id, 'qc_level': project_qc_settings['qc_level']})
            
            no_files_for_qc = math.ceil(folder_stats['no_files'] * (float(project_settings['qc_percent']) / 100))
            if no_files_for_qc < 10:
                if folder_stats['no_files'] > 10:
                    no_files_for_qc = 10
                else:
                    no_files_for_qc = folder_stats['no_files']
            if project_settings['qc_filenames'] != None:
                q = query_database_insert(("INSERT INTO transcription_qc (file_transcription_id, folder_transcription_id, transcription_source_id) ("
                                  " SELECT file_transcription_id, '{}' as folder_transcription_id, '{}' as transcription_source_id"
                                  "  FROM transcription_files WHERE folder_transcription_id = %(folder_id)s "
                                  "    AND {} "
                                  "  ORDER BY RAND() LIMIT {})").format(folder_id, source_id, project_settings['qc_filenames'], no_files_for_qc),
                                 {'folder_id': folder_id})
            else:
                q = query_database_insert(("INSERT INTO transcription_qc (file_transcription_id, folder_transcription_id, transcription_source_id) ("
                                  " SELECT file_transcription_id, '{}' as folder_transcription_id, '{}' as transcription_source_id"
                                  "  FROM transcription_files WHERE folder_transcription_id = %(folder_id)s "
                                  "  ORDER BY RAND() LIMIT {})").format(folder_id, source_id, no_files_for_qc),
                                 {'folder_id': folder_id})
            logger.info("no_files_for_qc: {}".format(no_files_for_qc))
            return redirect(url_for('qc_transcription_loading1', folder_id=folder_id, source_id=source_id))
        else:
            qc_stats_q = run_query(("WITH errors AS "
                                         "         (SELECT count(file_transcription_id) as no_files "
                                         "             FROM transcription_qc "
                                         "             WHERE file_transcription_id in (select file_transcription_id from transcription_files where folder_transcription_id = %(folder_id)s) "
                                         "                 AND transcription_source_id = %(source_id)s "
                                         "                 AND qc_results > 0 AND qc_results != 9),"
                                         "passed AS "
                                         "         (SELECT count(file_transcription_id) as no_files "
                                         "             FROM transcription_qc "
                                         "             WHERE file_transcription_id in (select file_transcription_id from transcription_files where folder_transcription_id = %(folder_id)s) "
                                         "                 AND transcription_source_id = %(source_id)s "
                                         "                 AND qc_results = 0),"
                                         "total AS (SELECT count(file_transcription_id) as no_files FROM transcription_qc "
                                         "            WHERE file_transcription_id in (select file_transcription_id from transcription_files where folder_transcription_id = %(folder_id)s) "
                                         "              AND transcription_source_id = %(source_id)s)"
                                         " SELECT t.no_files, e.no_files as no_errors,"
                                         "         p.no_files as no_passed "
                                         " FROM errors e, total t, passed p "),
                                        {'folder_id': folder_id, 'source_id': source_id})[0]
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
            folder = run_query(
                "SELECT q.*, f.folder as project_folder "
                " FROM transcription_qc_folders q, transcription_folders f "
                " WHERE q.folder_transcription_id = f.folder_transcription_id "
                "   AND q.folder_transcription_id = %(folder_id)s "
                "   AND q.transcription_source_id = %(source_id)s",
                {'folder_id': folder_id, 'source_id': source_id})[0]
            if qc_stats['no_files'] != int(qc_stats['no_errors']) + int(qc_stats['passed']):
                file_qc = run_query(("SELECT f.file_transcription_id FROM transcription_qc q, transcription_files f "
                                        "  WHERE q.file_transcription_id = f.file_transcription_id "
                                        "     AND f.folder_transcription_id = %(folder_id)s "
                                        "     AND q.transcription_source_id = %(source_id)s "
                                        "     AND q.qc_results = 9 order by file_transcription_id "
                                        "  LIMIT 1 "),
                                        {'folder_id': folder_id, 'source_id': source_id})[0]
                file_details = run_query(("SELECT f.file_transcription_id, f.folder_transcription_id, f.file_name, "
                                            "       NULL as preview_image_ext, DATEDIFF(NOW(), f.created_at) as datediff "
                                            " FROM transcription_files f WHERE f.file_transcription_id = %(file_id)s"),
                                            {'file_id': file_qc['file_transcription_id']})[0]
                file_checks = run_query(("SELECT file_check, check_results, "
                                            "       CASE WHEN check_info = '' THEN 'Check passed.' "
                                            "           ELSE check_info END AS check_info "
                                            "   FROM transcription_files_checks WHERE file_transcription_id = %(file_id)s"),
                                            {'file_id': file_qc['file_transcription_id']})
                file_metadata = pd.DataFrame()
                folder = run_query(
                    ("SELECT fol.* FROM transcription_folders fol, transcription_files f where f.folder_transcription_id = fol.folder_transcription_id and f.file_transcription_id = %(file_id)s"),
                        {'file_id': file_qc['file_transcription_id']})[0]

                viewer = resolve_image_viewer(
                    file_details['folder_transcription_id'],
                    file_qc['file_transcription_id'],
                    file_details['file_name'],
                    transcription=True,
                )
                zoom_exists = viewer['zoom_exists']
                zoom_filename = viewer['zoom_filename']
                iiif_image = viewer['iiif_image']

                attach_preview_paths(file_details, file_qc['file_transcription_id'], transcription=True)

                # Transcriptions
                tables = {}
                t_source = run_query("SELECT transcription_source_id, transcription_source_name, CONCAT(transcription_source_notes, ' ', transcription_source_date) as source_notes FROM transcription_sources WHERE project_id = %(project_id)s AND transcription_source_id = %(source_id)s", {'project_id': project_id['project_id'], 'source_id': source_id})[0]
                transcription_text = pd.DataFrame(run_query(("""
                                            SELECT fields.field_name as field, COALESCE(t.transcription_text, '') as value 
                                                FROM transcription_fields fields LEFT JOIN transcription_files_text t ON (fields.field_id = t.field_id and t.file_transcription_id = %(file_id)s) 
                                                WHERE fields.transcription_source_id = %(source_id)s 
                                                ORDER BY fields.sort_by
                                                """), {'source_id': t_source['transcription_source_id'], 'file_id': file_qc['file_transcription_id']}))
                tables = {'name': t_source['transcription_source_name'],
                                'table': transcription_text.to_html(table_id='transcription_text', index=False, border=0,
                                                                    escape=True,
                                                                    classes=["display", "compact", "table-striped"]),
                                'source_info': t_source['source_notes']}
                
                return render_template("qc_file_transcription.html",
                                    transcription=transcription_text,
                                    zoom_exists=zoom_exists, zoom_filename=zoom_filename,
                                    iiif_image=iiif_image,
                                    folder=folder, qc_stats=qc_stats,
                                    folder_id=folder_id, file_qc=file_qc, project_settings=project_settings,
                                    file_details=file_details, file_checks=file_checks, username=username,
                                    project_alias=project_alias['project_alias'],
                                    msg=msg, form=form, source_id=source_id, tables=tables,
                                    site_env=site_env, site_net=site_net, site_ver=site_ver,
                                    analytics_code=settings.analytics_code)
            else:
                error_files = run_query(("SELECT f.file_name, "
                                         " CASE WHEN q.qc_results = 1 THEN 'Critical Issue' "
                                         " WHEN q.qc_results = 2 THEN 'Major Issue' "
                                         " WHEN q.qc_results = 3 THEN 'Minor Issue' END as qc_results, "
                                         " q.qc_notes FROM transcription_qc q, transcription_files f "
                                              "  WHERE q.file_transcription_id in (select file_transcription_id from transcription_files where folder_transcription_id = %(folder_id)s) "
                                             "  AND q.transcription_source_id = %(source_id)s "
                                              "  AND q.qc_results > 0 AND q.file_transcription_id = f.file_transcription_id"),
                                            {'folder_id': folder_id, 'source_id': source_id})
                qc_folder_result = True
                crit_files = 0
                major_files = 0
                minor_files = 0
                for file in error_files:
                    if file['qc_results'] == 'Critical Issue':
                        crit_files += 1
                    elif file['qc_results'] == 'Major Issue':
                        major_files += 1
                    elif file['qc_results'] == 'Minor Issue':
                        minor_files += 1
                qc_threshold_critical_comparison = math.floor(qc_stats['no_files'] * (float(project_settings['qc_threshold_critical']) / 100))
                qc_threshold_major_comparison = math.floor(qc_stats['no_files'] * (float(project_settings['qc_threshold_major']) / 100))
                qc_threshold_minor_comparison = math.floor(qc_stats['no_files'] * (float(project_settings['qc_threshold_minor']) / 100))
                if crit_files > 0:
                    if qc_threshold_critical_comparison <= crit_files:
                        qc_folder_result = False
                if major_files > 0:
                    if qc_threshold_major_comparison <= major_files:
                        qc_folder_result = False
                if minor_files > 0:
                    if qc_threshold_minor_comparison <= minor_files:
                        qc_folder_result = False
                return render_template('qc_transcription_done.html',
                                        folder_id=folder_id, folder=folder, qc_stats=qc_stats,
                                        project_settings=project_settings, username=username,
                                        project_alias=project_alias['project_alias'],
                                        source_id=source_id,
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



@app.route('/qc_transcription_prep/<source_id>/<folder_id>/', methods=['POST', 'GET'], provide_automatic_options=False)
@login_required
def qc_transcription_loading1(source_id, folder_id):
    """Prepare QC for a folder"""
    return render_template('qc_transcription_prep.html', folder_id=folder_id, source_id=source_id,
                               project_alias="", site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code)


@app.route('/qc_loading/<folder_id>/', methods=['POST', 'GET'], provide_automatic_options=False)
@login_required
def qc_loading2(folder_id):
    """Prepare QC for a folder"""
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api.api_route_list'))

    try:
        folder_id = int(folder_id)
    except ValueError:
        try:
            folder_id = UUID(folder_id)
        except ValueError:
            raise InvalidUsage('invalid folder_id value', status_code=400)
    return redirect(url_for('qc_process', folder_id=str(folder_id)))


@app.route('/qc_transcription_done/<source_id>/<folder_id>/', methods=['POST', 'GET'], provide_automatic_options=False)
@login_required
def qc_transcription_done(source_id, folder_id):
    """Finalize transcription QC for a source/folder pair."""
    if site_net == "api":
        return redirect(url_for('api.api_route_list'))

    username = current_user.name
    try:
        folder_id = str(UUID(folder_id))
        source_id = str(UUID(source_id))
    except:
        raise InvalidUsage('invalid source_id or folder_id value', status_code=400)

    project_admin = run_query(
        ("SELECT count(*) as no_results "
         " FROM users u, qc_projects p, transcription_folders f "
         " WHERE u.username = %(username)s "
         "   AND p.project_id = f.project_id "
         "   AND f.folder_transcription_id = %(folder_id)s "
         "   AND u.user_id = p.user_id"),
        {'username': username, 'folder_id': folder_id})[0]
    if project_admin['no_results'] == 0:
        return redirect(url_for('home'))

    project_info = run_query(
        ("SELECT p.project_id, p.project_alias "
         " FROM projects p, transcription_folders f "
         " WHERE f.folder_transcription_id = %(folder_id)s "
         "   AND f.project_id = p.project_id"),
        {'folder_id': folder_id})[0]
    project_id = project_info['project_id']
    project_alias = project_info['project_alias']

    source = run_query(
        ("SELECT transcription_source_name "
         " FROM transcription_sources "
         " WHERE transcription_source_id = %(source_id)s "
         "   AND project_id = %(project_id)s"),
        {'source_id': source_id, 'project_id': project_id})
    if not source:
        raise InvalidUsage('invalid source_id value', status_code=400)

    qc_info = request.values.get('qc_info')
    qc_status = request.values.get('qc_status')
    if qc_status not in ("0", "1"):
        raise InvalidUsage('invalid qc_status value', status_code=400)

    user_id = run_query("SELECT user_id FROM users WHERE username = %(username)s",
                        {'username': username})[0]
    project_qc_settings = run_query(
        "SELECT * FROM transcription_qc_settings WHERE project_id = %(project_id)s",
        {'project_id': project_id})[0]

    q = query_database_insert(
        ("UPDATE transcription_qc_folders SET "
         "   qc_status = %(qc_status)s, "
         "   qc_by = %(qc_by)s, "
         "   qc_info = %(qc_info)s, "
         "   qc_ip = %(qc_ip)s, "
         "   qc_level = %(qc_level)s "
         " WHERE folder_transcription_id = %(folder_id)s "
         "   AND transcription_source_id = %(source_id)s"),
        {'folder_id': folder_id,
         'source_id': source_id,
         'qc_status': qc_status,
         'qc_info': qc_info,
         'qc_ip': request.environ.get('REMOTE_ADDR'),
         'qc_by': user_id['user_id'],
         'qc_level': project_qc_settings['qc_level']})

    badgecss = "bg-success" if qc_status == "0" else "bg-danger"
    badge_status = "Passed" if qc_status == "0" else "Failed"
    badge_text = "Transcription QC {} - {}".format(
        badge_status, source[0]['transcription_source_name'])
    if len(badge_text) > 64:
        badge_text = "{}...".format(badge_text[:61])

    clear_badges = run_query(
        ("DELETE FROM folders_badges "
         " WHERE folder_uid = %(folder_id)s "
         "   AND badge_type = 'transcription_qc_status' "
         "   AND folder_transcription_id = %(source_id)s"),
        {'folder_id': folder_id, 'source_id': source_id})
    query = (
        "INSERT INTO folders_badges "
        " (folder_uid, folder_transcription_id, badge_type, badge_css, badge_text, updated_at) "
        " VALUES (%(folder_id)s, %(source_id)s, 'transcription_qc_status', %(badgecss)s, %(msg)s, CURRENT_TIMESTAMP)")
    res = query_database_insert(query, {
        'folder_id': folder_id,
        'source_id': source_id,
        'badgecss': badgecss,
        'msg': badge_text,
    })

    return redirect(url_for('qc_transcription', project_alias=project_alias))



@app.route('/qc_transcription_loading/<source_id>/<folder_id>/', methods=['POST', 'GET'], provide_automatic_options=False)
@login_required
def qc_transcription_loading2(source_id, folder_id):
    """Prepare QC for a folder"""
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api.api_route_list'))

    try:
        folder_id = str(UUID(folder_id))
        source_id = str(UUID(source_id))
    except ValueError:
        raise InvalidUsage('invalid source_id or folder_id value', status_code=400)

    return redirect(url_for('qc_process_transcript', source_id=source_id, folder_id=folder_id))


@app.route('/qc_done/<folder_id>/', methods=['POST', 'GET'], provide_automatic_options=False)
@login_required
def qc_done(folder_id):
    """Run QC on a folder"""
    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api.api_route_list'))
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
        # q = query_database_insert(("UPDATE transcription_qc_folders SET qc_status = %(qc_status)s, qc_by = %(qc_by)s, qc_info = %(qc_info)s, qc_level = %(qc_level)s WHERE folder_transcription_id = %(folder_id)s"),
        #                  {'folder_id': folder_id,
        #                   'qc_status': qc_status,
        #                   'qc_info': qc_info,
        #                   'qc_by': user_id['user_id'],
        #                   'qc_level': project_qc_settings['qc_level']
        #                   })
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
    # if transcription == 1:
    #     return redirect(url_for('qc_transcription', project_alias=project_alias))
    # else:
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
    projects = run_query(
        "select p.project_title, p.project_id, p.project_alias, "
        "date_format(p.project_start, '%b-%Y') as project_start, "
        "date_format(p.project_end, '%b-%Y') as project_end, "
        "p.qc_status, p.project_unit, p.transcription "
        " FROM qc_projects qp, users u, projects p "
        " WHERE qp.project_id = p.project_id AND qp.user_id = u.user_id "
        "     AND u.username = %(username)s "
        "     AND p.project_alias IS NOT NULL AND p.project_status != 'Completed' "
        " GROUP BY p.project_title, p.project_id, p.project_alias, "
        "     p.project_start, p.project_end, p.qc_status, p.project_unit, p.transcription "
        " ORDER BY p.projects_order DESC",
        {'username': user_name},
    )
    if not projects or projects is False:
        projects = []
    project_list = []
    for project in projects:
        logger.info("project: {}".format(project).encode("utf-8"))
        logger.info("project_alias: {}".format(project['project_alias']))
        project_list.append({
            'project_title': project['project_title'],
            'project_id': project['project_id'],
            'filecheck_link': None,
            'project_alias': project['project_alias'],
            'project_start': project['project_start'],
            'project_end': project['project_end'],
            'qc_status': project['qc_status'],
            'project_unit': project['project_unit'],
            'transcription': project['transcription']
        })
    return render_template('userhome.html', project_list=project_list, username=user_name,
                           is_admin=is_admin, ip_addr=ip_addr, form=form,
                           site_env=site_env, site_net=site_net, site_ver=site_ver,
                           about_user_guide_url=ABOUT_USER_GUIDE_URL,
                           analytics_code=settings.analytics_code)


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



#####################################
if __name__ == '__main__':
    if site_env == "dev":
        app.run(threaded=False, debug=True)
    else:
        app.run(threaded=False, debug=False)
