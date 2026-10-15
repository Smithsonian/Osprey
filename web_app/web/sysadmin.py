"""System admin pages for users with users.is_admin = 1.

Only served on internal deployments (site_net == "internal"). Anyone else
who reaches these URLs — wrong site, or not an admin — is sent to /home.

Pages are read-only except these POST actions: requeue a pregenerated
report, queue a pregenerated sysadmin report, clear the app cache,
add/remove project custom data values, and deactivate/reactivate a user. All are
CSRF-protected (app-wide CSRFProtect), re-check the gate on every
request, and are logged at WARNING with the username so they appear in
ospreyapp.log in production. Running a live sysadmin report (GET) is logged
the same way, since it executes a stored query.
"""

import functools
import os

from flask import Blueprint
from flask import Response
from flask import abort
from flask import flash
from flask import redirect
from flask import render_template
from flask import request
from flask import send_file
from flask import url_for
from flask_login import current_user
from flask_login import login_required

import settings
from cache import cache
from logger import logger
from osprey.services import project_custom_data as custom_data
from osprey.services import report_materializations as materializations
from osprey.services import reports as report_service
from osprey.services import sysadmin_reports
from osprey.services import sysadmin_data
from osprey.services import sysadmin_qc
from osprey.services import sysadmin_users
from osprey.services import system_status
from osprey.services.permissions import user_perms
from osprey.services.system_status import section

sysadmin_bp = Blueprint('sysadmin', __name__, url_prefix='/sysadmin')

# (endpoint, label, icon) for the tab bar in sysadmin_base.html.
NAV = (
    ('sysadmin.index', 'Status', 'fa-gauge-high'),
    ('sysadmin.schema', 'Schema & tables', 'fa-database'),
    ('sysadmin.users', 'Users', 'fa-users'),
    ('sysadmin.projects', 'Projects', 'fa-folder-tree'),
    ('sysadmin.qc_settings', 'QC Settings', 'fa-list-check'),
    ('sysadmin.folder_errors', 'Folder Errors', 'fa-triangle-exclamation'),
    ('sysadmin.api_keys', 'API keys', 'fa-key'),
    ('sysadmin.kiosks', 'Kiosks', 'fa-desktop'),
    ('sysadmin.reports', 'Reports', 'fa-file-lines'),
    ('sysadmin.generate', 'Generate Reports', 'fa-play'),
    ('sysadmin.data_entry', 'Data Entry', 'fa-pen-to-square'),
)


def sysadmin_allowed():
    """True only for an admin on an internal deployment.

    The site check runs first so external/api sites never query the flag.
    """
    if settings.site_net != 'internal':
        return False
    return user_perms('', user_type='admin')


def sysadmin_required(view):
    """login_required plus the admin/internal gate, checked on every request."""
    @functools.wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not sysadmin_allowed():
            logger.warning("sysadmin page {} denied for {} (site_net={})".format(
                view.__name__, current_user.name, settings.site_net))
            return redirect(url_for('home'))
        logger.info("sysadmin page {} viewed by {}".format(view.__name__, current_user.name))
        return view(*args, **kwargs)
    return wrapped


def _render(template, **context):
    return render_template(template, username=current_user.name, nav=NAV, **context)


@sysadmin_bp.route('/', methods=['GET'], provide_automatic_options=False)
@sysadmin_required
def index():
    return _render('sysadmin.html', status=system_status.collect())


@sysadmin_bp.route('/schema/', methods=['GET'], provide_automatic_options=False)
@sysadmin_required
def schema():
    return _render('sysadmin_schema.html',
                   schema=section('schema', sysadmin_data.schema_status),
                   sizes=section('table sizes', sysadmin_data.table_sizes),
                   stats=section('stats', sysadmin_data.stats))


@sysadmin_bp.route('/users/', methods=['GET'], provide_automatic_options=False)
@sysadmin_required
def users():
    return _render('sysadmin_users.html',
                   users=section('users', sysadmin_data.users),
                   assignments=section('assignments', sysadmin_data.assignments_by_user),
                   current_username=current_user.name)


@sysadmin_bp.route('/users/<int:user_id>/deactivate', methods=['POST'], provide_automatic_options=False)
@sysadmin_required
def deactivate_user(user_id):
    """Set users.user_active = 0 (confirmed in a modal on the Users page)."""
    try:
        result, username = sysadmin_users.deactivate_user(user_id, current_user.name)
    except Exception:  # boundary: DB write; logged with context
        logger.exception("sysadmin deactivate failed: user_id={}".format(user_id))
        flash("Could not deactivate the user; see ospreyapp.log.", 'danger')
        return redirect(url_for('sysadmin.users'))
    if result == sysadmin_users.OK:
        logger.warning("sysadmin {} deactivated user {} (user_id={})".format(
            current_user.name, username, user_id))
        flash("{} is now inactive and can no longer log in.".format(username), 'success')
    elif result == sysadmin_users.SELF:
        flash("You cannot deactivate your own account.", 'danger')
    elif result == sysadmin_users.ALREADY_INACTIVE:
        flash("{} was already inactive.".format(username), 'warning')
    else:
        flash("User {} not found.".format(user_id), 'danger')
    return redirect(url_for('sysadmin.users'))


@sysadmin_bp.route('/users/<int:user_id>/reactivate', methods=['POST'], provide_automatic_options=False)
@sysadmin_required
def reactivate_user(user_id):
    """Set users.user_active = 1 (confirmed in a modal on the Users page)."""
    try:
        result, username = sysadmin_users.reactivate_user(user_id)
    except Exception:  # boundary: DB write; logged with context
        logger.exception("sysadmin reactivate failed: user_id={}".format(user_id))
        flash("Could not reactivate the user; see ospreyapp.log.", 'danger')
        return redirect(url_for('sysadmin.users'))
    if result == sysadmin_users.OK:
        logger.warning("sysadmin {} reactivated user {} (user_id={})".format(
            current_user.name, username, user_id))
        flash("{} is active again and can log in.".format(username), 'success')
    elif result == sysadmin_users.ALREADY_ACTIVE:
        flash("{} was already active.".format(username), 'warning')
    else:
        flash("User {} not found.".format(user_id), 'danger')
    return redirect(url_for('sysadmin.users'))


@sysadmin_bp.route('/projects/', methods=['GET'], provide_automatic_options=False)
@sysadmin_required
def projects():
    return _render('sysadmin_projects.html',
                   projects=section('projects', sysadmin_data.projects_overview),
                   profile=section('transcription profile', sysadmin_data.transcription_profile_config))


@sysadmin_bp.route('/qc/', methods=['GET'], provide_automatic_options=False)
@sysadmin_required
def qc_settings():
    """Step 1: choose a project (a GET form, so ?project_id= jumps to step 2)."""
    project_id = request.args.get('project_id', type=int)
    if project_id is not None:
        return redirect(url_for('sysadmin.qc_settings_project', project_id=project_id))
    return _render('sysadmin_qc.html', projects=section('qc settings projects', sysadmin_qc.list_projects))


@sysadmin_bp.route('/qc/<int:project_id>/', methods=['GET'], provide_automatic_options=False)
@sysadmin_required
def qc_settings_project(project_id):
    """Step 2: this project's QC settings, plus a client-side pass/fail calculator."""
    project = sysadmin_qc.get_project(project_id)
    if project is None:
        abort(404)
    return _render('sysadmin_qc_project.html', project=project,
                   qc_settings=section('qc settings', lambda: sysadmin_qc.get_settings(project)))


@sysadmin_bp.route('/folder-errors/', methods=['GET'], provide_automatic_options=False)
@sysadmin_required
def folder_errors():
    project_id = request.args.get('project_id', type=int)
    return _render('sysadmin_folder_errors.html',
                   errors=section('folder errors', lambda: sysadmin_data.folder_errors(project_id)),
                   filter_projects=section('folder error projects', sysadmin_data.folder_error_projects),
                   selected_project_id=project_id)


@sysadmin_bp.route('/api-keys/', methods=['GET'], provide_automatic_options=False)
@sysadmin_required
def api_keys():
    return _render('sysadmin_api_keys.html', api=section('api keys', sysadmin_data.api_keys))


@sysadmin_bp.route('/kiosks/', methods=['GET'], provide_automatic_options=False)
@sysadmin_required
def kiosks():
    return _render('sysadmin_kiosks.html', kiosks=section('kiosks', sysadmin_data.kiosks))


@sysadmin_bp.route('/reports/', methods=['GET'], provide_automatic_options=False)
@sysadmin_required
def reports():
    return _render('sysadmin_reports.html', reports=section('reports', sysadmin_data.reports))


# ---- Actions (POST only) ------------------------------------------------
# Post/redirect/get: each action flashes its outcome and redirects back, so
# a browser refresh never repeats it.

@sysadmin_bp.route('/reports/<int:project_id>/<report_id>/requeue', methods=['POST'],
                   provide_automatic_options=False)
@sysadmin_required
def requeue_report(project_id, report_id):
    """Queue a pregenerated report for the next materialize_reports.py pass
    (same path as the report page's Recompute button: ensure_row +
    request_refresh)."""
    report = report_service.get_project_report(project_id, report_id)
    if report is None:
        flash("Report {} / {} not found.".format(project_id, report_id), 'danger')
    elif int(report.get('pregenerated') or 0) != 1:
        # Live reports have no materialization to queue.
        flash("{} is a live report; nothing to queue.".format(report_id), 'warning')
    else:
        try:
            ok = report_service.request_pregenerated_refresh(report, requested_by=current_user.name)
        except Exception:  # boundary: DB write; logged with context, shown to the user
            logger.exception("sysadmin requeue failed: project_id={} report_id={}".format(project_id, report_id))
            ok = False
        if ok:
            logger.warning("sysadmin {} requeued report project_id={} report_id={}".format(
                current_user.name, project_id, report_id))
            flash("Queued {}; it runs on the next materialize_reports.py pass "
                  "(a job already running is left as is).".format(report_id), 'success')
        else:
            flash("Could not queue {}; see ospreyapp.log.".format(report_id), 'danger')
    return redirect(url_for('sysadmin.reports'))


@sysadmin_bp.route('/cache/clear', methods=['POST'], provide_automatic_options=False)
@sysadmin_required
def clear_cache():
    """Empty the shared FileSystemCache (all processes use the same directory)."""
    try:
        ok = cache.clear()
    except OSError:  # boundary: file I/O; cachelib logs most errors itself and returns False
        logger.exception("sysadmin cache clear failed")
        ok = False
    if ok:
        logger.warning("sysadmin {} cleared the cache".format(current_user.name))
        flash("Cache cleared.", 'success')
    else:
        flash("Cache clear stopped partway; see ospreyapp.log.", 'danger')
    return redirect(url_for('sysadmin.index'))


# ---- Generate Reports (sysadmin_reports table) ---------------------------

def _generate_groups():
    if not sysadmin_reports.table_exists():
        return None
    return sysadmin_reports.list_reports()


@sysadmin_bp.route('/generate/', methods=['GET'], provide_automatic_options=False)
@sysadmin_required
def generate():
    return _render('sysadmin_generate.html', groups=section('generate reports', _generate_groups),
                   preview_rows=sysadmin_reports.PREVIEW_ROWS)


def _load_report_or_404(report_id):
    # 404 rather than a MySQL error when db/sysadmin_reports.sql isn't applied yet.
    if not sysadmin_reports.table_exists():
        abort(404)
    report = sysadmin_reports.get_report(report_id)
    if report is None:
        abort(404)
    return report


@sysadmin_bp.route('/generate/<report_id>/', methods=['GET'], provide_automatic_options=False)
@sysadmin_required
def generate_run(report_id):
    """Run a live sysadmin report and show the first rows."""
    report = _load_report_or_404(report_id)
    if report['pregenerated']:
        flash("{} is pregenerated: queue it, then download its files here.".format(report_id), 'warning')
        return redirect(url_for('sysadmin.generate'))
    logger.warning("sysadmin {} requested live run of report {}".format(current_user.name, report_id))
    try:
        result = sysadmin_reports.run_live(report)
    except sysadmin_reports.ReportError as err:
        flash("{} was not run: {}.".format(report_id, err), 'danger')
        return redirect(url_for('sysadmin.generate'))
    except Exception as err:  # boundary: stored SQL run against the DB; logged, shown to the sysadmin
        logger.exception("sysadmin report {} failed".format(report_id))
        flash("{} failed: {}: {}".format(report_id, type(err).__name__, err), 'danger')
        return redirect(url_for('sysadmin.generate'))
    return _render('sysadmin_generate_run.html', report=report, result=result,
                   preview_rows=sysadmin_reports.PREVIEW_ROWS)


@sysadmin_bp.route('/generate/<report_id>/download.csv', methods=['GET'], provide_automatic_options=False)
@sysadmin_required
def generate_download(report_id):
    """Full result of a live sysadmin report as CSV."""
    report = _load_report_or_404(report_id)
    if report['pregenerated']:
        abort(404)
    logger.warning("sysadmin {} downloaded report {}".format(current_user.name, report_id))
    try:
        body = sysadmin_reports.live_csv(report)
    except sysadmin_reports.ReportError as err:
        flash("{} was not run: {}.".format(report_id, err), 'danger')
        return redirect(url_for('sysadmin.generate'))
    except Exception as err:  # boundary: stored SQL run against the DB
        logger.exception("sysadmin report {} download failed".format(report_id))
        flash("{} failed: {}: {}".format(report_id, type(err).__name__, err), 'danger')
        return redirect(url_for('sysadmin.generate'))
    return Response(body, mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename="{}.csv"'.format(report_id)})


@sysadmin_bp.route('/generate/<report_id>/queue', methods=['POST'], provide_automatic_options=False)
@sysadmin_required
def generate_queue(report_id):
    """Queue a pregenerated sysadmin report for the next materialize_reports.py pass."""
    report = _load_report_or_404(report_id)
    if not report['pregenerated']:
        flash("{} is a live report; use Run instead.".format(report_id), 'warning')
        return redirect(url_for('sysadmin.generate'))
    try:
        sysadmin_reports.check_query(report['query'])
        ok = sysadmin_reports.queue(report, requested_by=current_user.name)
    except sysadmin_reports.ReportError as err:
        flash("{} was not queued: {}.".format(report_id, err), 'danger')
        return redirect(url_for('sysadmin.generate'))
    except Exception:  # boundary: DB write; logged with context
        logger.exception("sysadmin queue of report {} failed".format(report_id))
        ok = False
    if ok:
        logger.warning("sysadmin {} queued report {}".format(current_user.name, report_id))
        flash("Queued {}; it runs on the next materialize_reports.py pass "
              "(a job already running is left as is).".format(report_id), 'success')
    else:
        flash("Could not queue {}; see ospreyapp.log.".format(report_id), 'danger')
    return redirect(url_for('sysadmin.generate'))


@sysadmin_bp.route('/generate/<report_id>/file/<fmt>', methods=['GET'], provide_automatic_options=False)
@sysadmin_required
def generate_file(report_id, fmt):
    """Latest CSV/XLSX of a pregenerated sysadmin report (served from outside static/)."""
    if fmt not in ('csv', 'xlsx'):
        abort(404)
    _load_report_or_404(report_id)  # 404 for unknown ids, even if old files exist
    status = materializations.get_materialization(
        sysadmin_reports.MATERIALIZATION_PROJECT_ID, sysadmin_reports.materialization_id(report_id))
    name = status and status.get('artifact_path_' + fmt)
    path = sysadmin_reports.artifact_path(name)
    if path is None:
        flash("No {} file for {} yet.".format(fmt.upper(), report_id), 'warning')
        return redirect(url_for('sysadmin.generate'))
    try:
        response = send_file(path, as_attachment=True, download_name=os.path.basename(path))
    except OSError:  # boundary: file I/O; usually group permissions or the SELinux label (README)
        logger.exception("sysadmin report file {} not readable".format(path))
        flash("Could not read the {} file for {}; see ospreyapp.log.".format(fmt.upper(), report_id), 'danger')
        return redirect(url_for('sysadmin.generate'))
    logger.warning("sysadmin {} downloaded {} of report {}".format(current_user.name, name, report_id))
    return response


# ---- Data Entry (project custom data) ------------------------------------
# Flow: pick a project -> pick a data type -> list/add/remove its values.

def _project_or_404(project_id):
    if not custom_data.tables_exist():
        abort(404)
    project = custom_data.get_project(project_id)
    if project is None:
        abort(404)
    return project


def _type_or_404(project_id, type_id):
    dtype = custom_data.get_type(project_id, type_id)
    if dtype is None:
        abort(404)
    return dtype


@sysadmin_bp.route('/data/', methods=['GET'], provide_automatic_options=False)
@sysadmin_required
def data_entry():
    """Step 1: choose a project (a GET form, so ?project_id= jumps to step 2)."""
    project_id = request.args.get('project_id', type=int)
    if project_id is not None:
        return redirect(url_for('sysadmin.data_project', project_id=project_id))

    def load():
        if not custom_data.tables_exist():
            return None
        return custom_data.list_projects()
    return _render('sysadmin_data.html', projects=section('data entry', load))


@sysadmin_bp.route('/data/<int:project_id>/', methods=['GET'], provide_automatic_options=False)
@sysadmin_required
def data_project(project_id):
    """Step 2: choose the data type for this project."""
    project = _project_or_404(project_id)
    return _render('sysadmin_data_project.html', project=project,
                   types=section('data types', lambda: custom_data.list_types(project_id)))


@sysadmin_bp.route('/data/<int:project_id>/<type_id>/', methods=['GET'], provide_automatic_options=False)
@sysadmin_required
def data_values(project_id, type_id):
    """Step 3: current values, add form, and removed-value history."""
    project = _project_or_404(project_id)
    dtype = _type_or_404(project_id, type_id)
    return _render('sysadmin_data_values.html', project=project, dtype=dtype,
                   values=section('values', lambda: custom_data.list_values(project_id, type_id)),
                   max_per_submit=custom_data.MAX_VALUES_PER_SUBMIT)


@sysadmin_bp.route('/data/<int:project_id>/<type_id>/add', methods=['POST'], provide_automatic_options=False)
@sysadmin_required
def data_add(project_id, type_id):
    _project_or_404(project_id)
    dtype = _type_or_404(project_id, type_id)
    back = redirect(url_for('sysadmin.data_values', project_id=project_id, type_id=type_id))
    try:
        values = custom_data.parse_values(request.form.get('values', ''), dtype['value_type'])
    except custom_data.DataEntryError as err:
        flash("Nothing saved: {}.".format(err), 'danger')
        return back
    note = (request.form.get('note') or '').strip()[:255]
    try:
        n = custom_data.add_values(project_id, type_id, values, note, current_user.name)
    except Exception:  # boundary: DB write; logged with context
        logger.exception("sysadmin data add failed: project_id={} type_id={}".format(project_id, type_id))
        flash("Could not save the values; see ospreyapp.log.", 'danger')
        return back
    logger.warning("sysadmin {} added {} value(s) to project_id={} type_id={}: {}".format(
        current_user.name, n, project_id, type_id, values))
    flash("Saved {} value{}.".format(n, '' if n == 1 else 's'), 'success')
    return back


@sysadmin_bp.route('/data/<int:project_id>/<type_id>/<int:value_id>/remove', methods=['POST'],
                   provide_automatic_options=False)
@sysadmin_required
def data_remove(project_id, type_id, value_id):
    _project_or_404(project_id)
    _type_or_404(project_id, type_id)
    back = redirect(url_for('sysadmin.data_values', project_id=project_id, type_id=type_id))
    try:
        ok = custom_data.remove_value(project_id, type_id, value_id, current_user.name)
    except Exception:  # boundary: DB write; logged with context
        logger.exception("sysadmin data remove failed: value_id={}".format(value_id))
        flash("Could not remove the value; see ospreyapp.log.", 'danger')
        return back
    if ok:
        logger.warning("sysadmin {} removed value_id={} from project_id={} type_id={}".format(
            current_user.name, value_id, project_id, type_id))
        flash("Value removed (kept in history; add it again to restore it).", 'success')
    else:
        flash("That value was already removed.", 'warning')
    return back
