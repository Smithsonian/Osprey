"""Web views for project data reports."""

import csv
from io import StringIO

from flask import Blueprint
from flask import redirect
from flask import jsonify
from flask import render_template
from flask import request
from flask import Response
from flask import url_for
from flask_login import current_user

import settings
from cache import cache
from osprey.services import builtin_reports as builtin_report_service
from osprey.services import reports as report_service
from osprey.version import __version__
from web.forms import LoginForm

reports_bp = Blueprint('reports', __name__)

RENDERING_PENDING = ' '


def _report_data_ready(rendering):
    """True only when the client asked for the materialized report view."""
    return str(rendering or '').strip() == '1'


def _materialization_viewable(status):
    """True when an export artifact is available to show (even if a refresh is queued)."""
    if not status:
        return False
    has_artifact = bool(status.get('artifact_path_csv') or status.get('artifact_path_xlsx'))
    if not has_artifact:
        return False
    if status.get('status') == 'succeeded':
        return True
    # Overnight re-queue sets status back to queued/running while prior artifacts remain.
    return status.get('last_succeeded_at') is not None


@cache.memoize()
@reports_bp.route('/reports/', methods=['GET'], provide_automatic_options=False)
def data_reports_form():
    """Report of a project"""
    site_env = settings.env
    site_net = settings.site_net
    site_ver = __version__

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
    return redirect(url_for('reports.data_reports', project_alias=project_alias, report_id=report_id))


# Register concrete action paths before the <rendering> catch-all so
# /status, /refresh, and /download.csv are never captured as rendering values.
@reports_bp.route(
    '/reports/<project_alias>/<report_id>/download.csv',
    methods=['GET'],
    provide_automatic_options=False,
)
def download_builtin_report_csv(project_alias=None, report_id=None):
    """Download the data behind a built-in chart report."""
    project_id = report_service.get_project_id(project_alias)
    if project_id is None:
        return jsonify({'error': 'Project not found'}), 404

    report = report_service.get_project_report(project_id, report_id)
    if not builtin_report_service.is_builtin_chart_report(report):
        return jsonify({'error': 'Built-in chart report not found'}), 404

    project_info = report_service.get_project(project_id)
    chart = builtin_report_service.load_chart_report(
        project_id,
        report_id,
        project_title=project_info.get('project_title', ''),
    )

    output = StringIO()
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(['Date', 'Images', 'Objects'])
    for row in chart['table_rows']:
        writer.writerow([row['date'], row['images'], row['objects']])

    filename = f'{project_alias}-{report_id}.csv'
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@reports_bp.route('/reports/<project_alias>/<report_id>/status', methods=['GET'], provide_automatic_options=False)
def report_status(project_alias=None, report_id=None):
    """Lightweight JSON status for pregenerated/materialized reports."""
    project_id = report_service.get_project_id(project_alias)
    if project_id is None:
        return jsonify({'error': 'Project not found'}), 404
    project_report = report_service.get_project_report(project_id, report_id)
    if project_report is None:
        return jsonify({'error': 'Report not found'}), 404
    if int(project_report.get('pregenerated') or 0) != 1:
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
        'row_count': status.get('row_count'),
        'viewable': _materialization_viewable(status),
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
    if int(project_report.get('pregenerated') or 0) != 1:
        return jsonify({'error': 'Not a pregenerated report'}), 400

    requested_by = current_user.name if current_user.is_authenticated else None
    ok = report_service.request_pregenerated_refresh(project_report, requested_by=requested_by)
    if not ok:
        return jsonify({'error': 'Failed to queue refresh'}), 500
    return jsonify({'result': True})


@reports_bp.route('/reports/<project_alias>/<report_id>/', methods=['GET'], provide_automatic_options=False)
@reports_bp.route('/reports/<project_alias>/<report_id>/<rendering>', methods=['GET'], provide_automatic_options=False)
def data_reports(project_alias=None, report_id=None, rendering=RENDERING_PENDING):
    """Report of a project"""
    site_env = settings.env
    site_net = settings.site_net
    site_ver = __version__

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

    project_info = report_service.get_project(project_id)

    if builtin_report_service.is_builtin_chart_report(project_report):
        chart = builtin_report_service.load_chart_report(
            project_id,
            report_id,
            project_title=project_info.get('project_title', ''),
        )
        return render_template(
            'reports_chart.html',
            project_alias=project_alias,
            project_info=project_info,
            report=project_report,
            chart=chart,
            site_env=site_env,
            site_net=site_net,
            site_ver=site_ver,
            analytics_code=settings.analytics_code,
            username=username,
            asklogin=asklogin,
            form=form,
        )

    report_data_updated = report_service.get_report_last_updated(project_report)

    preview_tables = []
    preview_limit = 20
    preview_row_count = None

    if int(project_report.get('pregenerated') or 0) == 1:
        # Pregenerated exports are materialized out-of-band.
        # If an artifact already exists, skip the loading spinner.
        if not _report_data_ready(rendering):
            status = report_service.get_pregenerated_status(project_report)
            if _materialization_viewable(status):
                return redirect(
                    url_for(
                        'reports.data_reports',
                        project_alias=project_alias,
                        report_id=report_id,
                        rendering='1',
                    )
                )
            # Best-effort: queue a refresh if we have no successful artifact yet.
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
        tables = []
        preview = report_service.get_pregenerated_preview(project_report, limit=preview_limit)
        if preview is not None:
            preview_tables = [
                preview.to_html(
                    table_id='report_preview',
                    index=False,
                    border=0,
                    escape=False,
                    classes=["display", "compact", "table-striped"],
                )
            ]
            if status:
                preview_row_count = status.get('row_count')
    else:
        report_data = report_service.get_report_data(project_report)
        data_file = ""
        data_file_e = ""
        current_datetime_formatted = ""
        status = None
        pregenerated = 0
        tables = [
            report_data.to_html(
                table_id='report_data',
                index=False,
                border=0,
                escape=False,
                classes=["display", "compact", "table-striped"],
            )
        ]

    return render_template('reports.html',
                           project_id=project_id, project_alias=project_alias, project_info=project_info,
                           report=project_report,
                           tables=tables,
                           preview_tables=preview_tables,
                           preview_limit=preview_limit,
                           preview_row_count=preview_row_count,
                           data_file_e=data_file_e, report_data_updated=report_data_updated, form=form,
                           data_file=data_file, pregenerated=pregenerated, report_date=current_datetime_formatted,
                           site_env=site_env, site_net=site_net, site_ver=site_ver,
                           analytics_code=settings.analytics_code,
                           username=username, asklogin=asklogin,
                           materialization=status)