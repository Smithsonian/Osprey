"""Web views for project data reports."""

from flask import Blueprint
from flask import redirect
from flask import jsonify
from flask import render_template
from flask import request
from flask import url_for
from flask_login import current_user

import settings
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
    site_ver = getattr(settings, 'site_ver', '2.11.1')

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
    site_ver = getattr(settings, 'site_ver', '2.11.1')

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
        # Pregenerated exports are materialized out-of-band.
        # The loading view now polls status and redirects back here when ready.
        if rendering != "1":
            # Best-effort: queue a refresh if we have no successful artifact yet.
            status = report_service.get_pregenerated_status(project_report)
            if not status or status.get("last_succeeded_at") is None:
                report_service.request_pregenerated_refresh(
                    project_report, requested_by=username
                )
            return render_template(
                'reports_loading.html',
                project_alias=project_alias,
                project_info=project_info,
                report=project_report,
                site_env=site_env,
                site_net=site_net,
                site_ver=site_ver,
                analytics_code=settings.analytics_code,
            )

        data_file, data_file_e, current_datetime_formatted, status = report_service.generate_pregenerated_report(project_report)
        pregenerated = 1
    else:
        report_data = report_service.get_report_data(project_report)
        data_file = ""
        data_file_e = ""
        current_datetime_formatted = ""
        status = None
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
                           username=username, asklogin=asklogin,
                           materialization=status)


@reports_bp.route('/reports/<project_alias>/<report_id>/status', methods=['GET'], provide_automatic_options=False)
def report_status(project_alias=None, report_id=None):
    """Lightweight JSON status for pregenerated/materialized reports."""
    project_id = report_service.get_project_id(project_alias)
    if project_id is None:
        return jsonify({'error': 'Project not found'}), 404
    project_report = report_service.get_project_report(project_id, report_id)
    if project_report is None:
        return jsonify({'error': 'Report not found'}), 404
    if project_report.get('pregenerated') != 1:
        return jsonify({'error': 'Not a pregenerated report'}), 400
    status = report_service.get_pregenerated_status(project_report) or {}
    # Only return fields the template JS needs.
    return jsonify({
        'status': status.get('status'),
        'last_succeeded_at': str(status.get('last_succeeded_at')) if status.get('last_succeeded_at') else None,
        'last_started_at': str(status.get('last_started_at')) if status.get('last_started_at') else None,
        'last_failed_at': str(status.get('last_failed_at')) if status.get('last_failed_at') else None,
        'error_message': status.get('error_message'),
        'artifact_path_csv': status.get('artifact_path_csv'),
        'artifact_path_xlsx': status.get('artifact_path_xlsx'),
        'materialized_table_name': status.get('materialized_table_name'),
        'freshness_sla_seconds': status.get('freshness_sla_seconds'),
        'source_updated_at': str(status.get('source_updated_at')) if status.get('source_updated_at') else None,
    })


@reports_bp.route('/reports/<project_alias>/<report_id>/refresh', methods=['POST'], provide_automatic_options=False)
def report_refresh(project_alias=None, report_id=None):
    """Queue a refresh for a pregenerated/materialized report."""
    project_id = report_service.get_project_id(project_alias)
    if project_id is None:
        return jsonify({'error': 'Project not found'}), 404
    project_report = report_service.get_project_report(project_id, report_id)
    if project_report is None:
        return jsonify({'error': 'Report not found'}), 404
    if project_report.get('pregenerated') != 1:
        return jsonify({'error': 'Not a pregenerated report'}), 400

    requested_by = current_user.name if current_user.is_authenticated else None
    ok = report_service.request_pregenerated_refresh(project_report, requested_by=requested_by)
    if not ok:
        return jsonify({'error': 'Failed to queue refresh'}), 500
    return jsonify({'result': True})
