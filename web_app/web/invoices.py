"""Web views for invoice reconciliation."""

import io
from datetime import datetime
from time import strftime, localtime

from flask import Blueprint
from flask import Response
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for
from flask_login import current_user
from flask_login import login_required

import settings
from osprey.services import invoices as invoice_service
from osprey.services.permissions import user_perms
from osprey.version import __version__
from web.forms import LoginForm

invoices_bp = Blueprint('invoices', __name__)


@invoices_bp.route('/invoice/', methods=['GET'], provide_automatic_options=False)
@login_required
def invoice(msg=None):
    """Invoice Reconciliation"""
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
        project_list = invoice_service.list_user_projects(username)
        msg = ""
        return render_template('invoice.html',
                               username=username, project_list=project_list,
                               is_admin=is_admin, msg=msg,
                               today_date=datetime.today().strftime('%Y-%m-%d'),
                               form=form, site_env=site_env, site_net=site_net, site_ver=site_ver,
                               analytics_code=settings.analytics_code)


@invoices_bp.route('/invoice_recon/', methods=['POST'], provide_automatic_options=False)
@login_required
def invoice_recon(msg=None):
    """Invoice Reconciliation"""
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
        project_id = request.values.get('project_id')
        f = request.files.get('file')
        result = invoice_service.reconcile_invoice(project_id, f)
        now = datetime.now()
        return render_template('invoice_recon.html',
                               username=username,
                               no_files="{:,}".format(result['no_files']),
                               no_files_osprey="{:,}".format(result['no_files_osprey']),
                               no_files_dams="{:,}".format(result['no_files_dams']),
                               is_admin=is_admin, msg=result['msg'],
                               now=now, randomint=result['randomval'],
                               project_info=result['project_info'],
                               count_msg=result['count_msg'], count_msg_css=result['count_msg_css'],
                               today_date=datetime.today().strftime('%Y-%m-%d'),
                               form=form, site_env=site_env, site_net=site_net, site_ver=site_ver,
                               analytics_code=settings.analytics_code)


@invoices_bp.route('/invoice_recon_dl/', methods=['POST'], provide_automatic_options=False)
@login_required
def invoice_recon_dl(randomint=None):
    """Download Invoice Reconciliation"""
    site_net = settings.site_net

    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api.api_route_list'))

    is_admin = user_perms('', user_type='admin')
    if is_admin is False:
        # Not allowed
        return redirect(url_for('home'))
    else:
        randomint = request.values.get('randomint')
        current_time = strftime("%Y%m%d_%H%M%S", localtime())
        # from https://stackoverflow.com/a/68136716
        buffer = io.BytesIO()
        invoice_service.build_invoice_export(randomint).to_excel(buffer, index=False)
        headers = {
            'Content-Disposition': 'attachment; filename=invoice_reconciliation_{}.xlsx'.format(current_time),
            'Content-type': 'application/vnd.ms-excel'
        }
        return Response(buffer.getvalue(), mimetype='application/vnd.ms-excel', headers=headers)
