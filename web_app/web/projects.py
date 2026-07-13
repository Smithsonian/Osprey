"""Web views for creating and editing projects, informatics projects, and project links."""

from datetime import datetime

import pandas as pd
from flask import Blueprint
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for
from flask_login import current_user
from flask_login import login_required

import settings
from logger import logger
from osprey.services import projects as project_service
from osprey.services.permissions import user_perms
from osprey.version import __version__
from web.forms import LoginForm

projects_bp = Blueprint('projects', __name__)


@projects_bp.route('/new_project/', methods=['GET'], provide_automatic_options=False)
@login_required
def new_project(msg=None):
    """Create a new project"""
    site_env = settings.env
    site_net = settings.site_net
    site_ver = __version__

    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api.api_route_list'))

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


@projects_bp.route('/create_new_project/', methods=['POST'], provide_automatic_options=False)
@login_required
def create_new_project():
    """Create a new project"""
    site_net = settings.site_net

    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api.api_route_list'))

    is_admin = user_perms('', user_type='admin')
    if is_admin is False:
        # Not allowed
        return redirect(url_for('home'))
    p_title = request.values.get('p_title')
    p_alias = request.values.get('p_alias')
    p_desc = request.values.get('p_desc')
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

    project_service.create_project(
        p_title, p_unit, p_alias, p_desc, p_coordurl, p_area, p_md, p_method,
        p_manager, p_prod, p_storage, p_start, p_noobjects, current_user.id,
        file_checks={
            'raw_pair': request.values.get('raw_pair'),
            'tif_compression': request.values.get('tif_compression'),
            'magick': request.values.get('magick'),
            'jhove': request.values.get('jhove'),
            'sequence': request.values.get('sequence'),
        })

    return redirect(url_for('home', _anchor=p_alias))


@projects_bp.route('/edit_project/<project_alias>/', methods=['GET'], provide_automatic_options=False)
@login_required
def edit_project(project_alias=None):
    """Edit a project"""
    site_env = settings.env
    site_net = settings.site_net
    site_ver = __version__

    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api.api_route_list'))

    # Declare the login form
    form = LoginForm(request.form)

    username = current_user.name
    is_admin = user_perms('', user_type='admin')
    if is_admin is False:
        # Not allowed
        return redirect(url_for('home'))
    project_admin = project_service.count_project_admin(username, project_alias)
    if project_admin[0]['no_results'] == 0:
        # Not allowed
        return redirect(url_for('home'))
    project = project_service.get_project_for_edit(project_alias)
    return render_template('edit_project.html',
                           username=username,
                           is_admin=is_admin,
                           project=project,
                           form=form,
                           site_env=site_env,
                           site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code)


@projects_bp.route('/infprojects/', methods=['GET'], provide_automatic_options=False)
@login_required
def infprojects():
    """Home for informatics projects"""
    site_env = settings.env
    site_net = settings.site_net
    site_ver = __version__

    # Declare the login form
    form = LoginForm(request.form)

    is_admin = user_perms('', user_type='admin')
    logger.info("is_admin:{}".format(is_admin))
    list_projects_inf = pd.DataFrame(project_service.list_informatics_projects())
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


@projects_bp.route('/infprojects/<proj_id>/', methods=['GET'], provide_automatic_options=False)
@login_required
def infprojects_edit(proj_id=None):
    """Home for informatics projects"""
    site_env = settings.env
    site_net = settings.site_net
    site_ver = __version__

    # Declare the login form
    form = LoginForm(request.form)

    is_admin = user_perms('', user_type='admin')
    logger.info("is_admin:{}".format(is_admin))
    project = project_service.get_informatics_project(proj_id)
    si_units = project_service.list_si_units()

    return render_template('infproject.html',
                           project=project, si_units=si_units, form=form,
                           site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code)


@projects_bp.route('/infprojects/new/', methods=['GET'], provide_automatic_options=False)
@login_required
def new_infprojects():
    """Home for informatics projects"""
    site_env = settings.env
    site_net = settings.site_net
    site_ver = __version__

    # Declare the login form
    form = LoginForm(request.form)

    is_admin = user_perms('', user_type='admin')
    logger.info("is_admin:{}".format(is_admin))
    si_units = project_service.list_si_units()

    return render_template('newinfproject.html',
                           si_units=si_units, form=form,
                           site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code)


@projects_bp.route('/infprojects/edit/', methods=['POST'], provide_automatic_options=False)
@login_required
def edit_inf_proj():
    """Create or edit an informatics project"""
    site_net = settings.site_net

    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api.api_route_list'))

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
    info_link = request.values.get('info_link')
    project_start = request.values.get('project_start')
    project_end = request.values.get('project_end')

    if proj_edit in ("0", "1"):
        project_service.upsert_informatics_project(
            proj_edit, proj_id, project_title, project_unit, summary, records, pm,
            project_status, github_link, info_link, project_start, project_end)
        return redirect(url_for('projects.infprojects_edit', proj_id=proj_id))


@projects_bp.route('/proj_links/<project_alias>/', methods=['GET'], provide_automatic_options=False)
@login_required
def proj_links(project_alias=None):
    """Add / edit links associated with a project"""
    site_env = settings.env
    site_net = settings.site_net
    site_ver = __version__

    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api.api_route_list'))

    # Declare the login form
    form = LoginForm(request.form)

    username = current_user.name
    is_admin = user_perms('', user_type='admin')
    if is_admin is False:
        # Not allowed
        return redirect(url_for('home'))
    project_admin = project_service.count_project_admin(username, project_alias)
    if project_admin[0]['no_results'] == 0:
        # Not allowed
        return redirect(url_for('home'))
    project = project_service.get_project_for_edit(project_alias)

    projects_links = project_service.get_project_links(project['project_id'])

    return render_template('proj_links.html',
                           username=username, is_admin=is_admin, project=project,
                           form=form, projects_links=projects_links, site_env=site_env,
                           site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code)


@projects_bp.route('/add_links/', methods=['POST'], provide_automatic_options=False)
@login_required
def add_links(project_alias=None):
    """Create a new project"""
    site_net = settings.site_net

    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api.api_route_list'))

    is_admin = user_perms('', user_type='admin')
    if is_admin is False:
        # Not allowed
        return redirect(url_for('home'))
    project_alias = request.values.get('project_alias')

    project_id = project_service.get_project_id_row(project_alias)[0]['project_id']

    link_title = request.values.get('link_title')
    link_type = request.values.get('link_type')
    link_url = request.values.get('link_url')
    project_service.add_project_link(project_id, link_type, link_title, link_url)

    return redirect(url_for('projects.proj_links', project_alias=project_alias))


@projects_bp.route('/project_update/<project_alias>', methods=['POST'], provide_automatic_options=False)
@login_required
def project_update(project_alias):
    """Save edits to a project"""
    site_net = settings.site_net

    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api.api_route_list'))

    username = current_user.name
    is_admin = user_perms('', user_type='admin')
    if is_admin is False:
        # Not allowed
        return redirect(url_for('home'))
    project_id = project_service.get_project_id_row(project_alias)[0]['project_id']
    project_admin = project_service.count_project_admin(username, project_alias)
    if project_admin[0]['no_results'] == 0:
        # Not allowed
        return redirect(url_for('home'))
    p_title = request.values.get('p_title')
    p_desc = request.values.get('p_desc')
    p_status = request.values.get('p_status')
    p_start = request.values.get('p_start')
    p_end = request.values.get('p_end')
    p_noobjects = request.values.get('p_noobjects')

    project_service.update_project(project_alias, project_id, p_title, p_status, p_start, p_desc, p_end, p_noobjects)

    return redirect(url_for('home'))
