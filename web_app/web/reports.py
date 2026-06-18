"""Web views for project data reports."""

from flask import Blueprint
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for
from flask_login import current_user

import settings
from api.config import config
from cache import cache
from osprey.services import reports as report_service
from web.forms import LoginForm

reports_bp = Blueprint('reports', __name__)


@cache.memoize()
@reports_bp.route('/reports/', methods=['GET'], provide_automatic_options=False)
def data_reports_form():
    """Report of a project"""
    site_env = settings.env
    site_net = settings.site_net
    site_ver = config.SITE_VER

    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api.api_route_list'))

    # Declare the login form
    form = LoginForm(request.form)

    project_alias = request.values.get("project_alias")
    report_id = request.values.get("report_id")
    if project_alias is None or report_id is None:
        error_msg = "Report is not available."
        return render_template('error.html', error_msg=error_msg, project_alias=None,
                               site_env=site_env, site_net=site_net, site_ver=site_ver), 404
    return redirect(url_for('reports.data_reports', project_alias=project_alias, report_id=report_id, rendering=False))


@reports_bp.route('/reports/<project_alias>/<report_id>/<rendering>', methods=['GET'], provide_automatic_options=False)
def data_reports(project_alias=None, report_id=None, rendering=None):
    """Report of a project"""
    site_env = settings.env
    site_net = settings.site_net
    site_ver = config.SITE_VER

    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api.api_route_list'))

    if current_user.is_authenticated:
        username = current_user.name
    else:
        username = None

    # Declare the login form
    form = LoginForm(request.form)
    if settings.site_net == "internal":
        asklogin = True
    else:
        asklogin = False

    if project_alias is None:
        error_msg = "Project is not available."
        return render_template('error.html', error_msg=error_msg, project_alias=None, site_env=site_env, site_net=site_net), 404

    project_id = report_service.get_project_id(project_alias)

    if project_id is None:
        error_msg = "Project was not found."
        return render_template('error.html', error_msg=error_msg, project_alias=project_id,
                               site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404

    project_report = report_service.get_project_report(project_id, report_id)
    if project_report is None:
        error_msg = "Report was not found."
        return render_template('error.html', error_msg=error_msg, project_alias=project_alias,
                               site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code), 404

    report_data_updated = report_service.get_report_last_updated(project_report)
    project_info = report_service.get_project(project_id)

    if project_report['pregenerated'] == 1:
        if rendering != "1":
            return render_template('reports_loading.html',
                           project_alias=project_alias, project_info=project_info,
                           report=project_report,
                           site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code)
        else:
            report_data, data_file, data_file_e, current_datetime_formatted = report_service.generate_pregenerated_report(project_report)
            pregenerated = 1
    else:
        report_data = report_service.get_report_data(project_report)
        data_file = ""
        data_file_e = ""
        current_datetime_formatted = ""
        pregenerated = 0

    return render_template('reports.html',
                           project_id=project_id, project_alias=project_alias, project_info=project_info,
                           report=project_report,
                           tables=[report_data.to_html(table_id='report_data',
                                                       index=False,
                                                       border=0,
                                                       escape=False,
                                                       classes=["display", "compact", "table-striped"])],
                           data_file_e=data_file_e, report_data_updated=report_data_updated, form=form,
                           data_file=data_file, pregenerated=pregenerated, report_date=current_datetime_formatted,
                           site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code,
                           username=username, asklogin=asklogin)
