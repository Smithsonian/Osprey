"""Web views for file details, search, and DAMS folder updates."""

from flask import Blueprint
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for
from flask_login import current_user
from flask_login import login_required

import settings
from cache import cache
from logger import logger
from osprey.files import attach_preview_paths, check_file_id, resolve_image_viewer, static_preview_path
from osprey.services import file_search as file_search_service
from osprey.services import files as files_service
from osprey.services.permissions import kiosk_mode, user_perms
from web.forms import LoginForm

files_bp = Blueprint('files', __name__)


@files_bp.route('/file/<file_id>/', methods=['GET'], provide_automatic_options=False)
def file(file_id=None):
    """File details"""
    site_env = settings.env
    site_net = settings.site_net
    site_ver = getattr(settings, 'site_ver', '2.11.1')

    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api.api_route_list'))

    if file_id is None:
        error_msg = "File ID is missing."
        return render_template('error.html', error_msg=error_msg, project_alias=None, site_env=site_env, site_net=site_net, site_ver=site_ver), 400
    try:
        file_id = int(file_id)
    except:
        error_msg = "File ID is not valid."
        return render_template('error.html', error_msg=error_msg, project_alias=None, site_env=site_env, site_net=site_net, site_ver=site_ver), 400

    # Declare the login form
    form = LoginForm(request.form)

    file_id_check = check_file_id(file_id)

    if file_id_check is False:
        error_msg = "File ID not found."
        return render_template('error.html', error_msg=error_msg, project_alias=None, site_env=site_env, site_net=site_net, site_ver=site_ver), 400

    # Folder info
    folder_info = files_service.get_folder_info(file_id)
    if folder_info is None:
        error_msg = "Invalid File ID."
        return render_template('error.html', error_msg=error_msg, project_alias=None, site_env=site_env, site_net=site_net, site_ver=site_ver), 400

    file_details = files_service.get_file_details(folder_info['folder_id'], file_id)
    project_alias = files_service.get_project_alias(folder_info['project_id'])

    file_checks = files_service.get_file_checks(file_id)
    file_postprocessing = files_service.get_file_postprocessing(file_id)

    attach_preview_paths(file_details, file_id)
    image_url = url_for('static', filename=file_details['fullsize_img_path'])
    file_metadata = files_service.get_file_metadata(file_id, file_details['file_ext'])

    file_links = files_service.get_file_links(file_id)

    file_sensitive = []
    if len(file_sensitive) == 0:
        file_sensitive = 0
        sensitive_info = ""
    else:
        file_data = file_sensitive[0]
        file_sensitive = file_data['sensitive_contents']
        sensitive_info = file_data['sensitive_info']

    if current_user.is_authenticated:
        user_name = current_user.name
        is_admin = user_perms('', user_type='admin')
    else:
        user_name = ""
        is_admin = False
    logger.info("project_alias: {}".format(project_alias))

    # kiosk mode
    kiosk, user_address = kiosk_mode(request, settings.kiosks)

    viewer = resolve_image_viewer(
        file_details['folder_id'],
        file_id,
        file_details['file_name'],
        transcription=False,
    )
    zoom_exists = viewer['zoom_exists']
    zoom_filename = viewer['zoom_filename']
    iiif_image = viewer['iiif_image']
    transcription_text = ""

    return render_template('file.html',
                           zoom_exists=zoom_exists, iiif_image=iiif_image, zoom_filename=zoom_filename, folder_info=folder_info,
                           file_details=file_details, file_checks=file_checks,
                           file_postprocessing=file_postprocessing, username=user_name, image_url=image_url,
                           is_admin=is_admin, project_alias=project_alias,
                           tables=[file_metadata.to_html(table_id='file_metadata', index=False, border=0,
                                                         escape=False,
                                                         classes=["display", "compact", "table-striped"])],
                           file_metadata_rows=file_metadata.shape[0],
                           file_links=file_links, file_sensitive=str(file_sensitive),

                           sensitive_info=sensitive_info, form=form, site_env=site_env,
                           site_net=site_net, site_ver=site_ver, kiosk=kiosk, user_address=user_address,
                           analytics_code=settings.analytics_code)


@files_bp.route('/file_transcription/<file_id>/', methods=['GET'], provide_automatic_options=False)
def file_transcription(file_id=None):
    """File details from a transcription project"""
    site_env = settings.env
    site_net = settings.site_net
    site_ver = getattr(settings, 'site_ver', '2.11.1')

    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api.api_route_list'))

    # Declare the login form
    form = LoginForm(request.form)

    file_id_check = files_service.check_file_id_transcription(file_id)
    if file_id_check is None:
        error_msg = "File ID is missing."
        return render_template('error.html', error_msg=error_msg, project_alias=None, site_env=site_env, site_net=site_net, site_ver=site_ver), 400

    folder_info = files_service.get_folder_info_transcription(file_id)
    if folder_info is None:
        error_msg = "Invalid File ID."
        return render_template('error.html', error_msg=error_msg, project_alias=None, site_env=site_env, site_net=site_net, site_ver=site_ver), 400

    # Transcription project?
    transcription = files_service.get_project_transcription_flag(folder_info['project_id'])

    if transcription != 1:
        error_msg = "File ID error."
        return render_template('error.html', error_msg=error_msg, project_alias=None, site_env=site_env, site_net=site_net, site_ver=site_ver), 400

    tables = {}
    i = 0
    t_sources = files_service.get_transcription_sources(folder_info['project_id'])
    for t_source in t_sources:
        transcription_text = files_service.get_transcription_text_table(t_source['transcription_source_id'], file_id)
        tables[i] = {'name': t_source['transcription_source_name'],
                        'table': transcription_text.to_html(table_id='transcription_text', index=False, border=0,
                                                            escape=True,
                                                            classes=["display", "compact", "table-striped"]),
                        'source_info': t_source['source_notes']}
        i += 1

    file_details = files_service.get_file_details_transcription(folder_info['folder_transcription_id'], file_id)

    project_alias = files_service.get_project_alias(folder_info['project_id'])

    file_checks = files_service.get_file_checks_transcription(file_id)
    attach_preview_paths(file_details, file_id, transcription=True)
    image_url = url_for('static', filename=file_details['fullsize_img_path'])

    file_links = files_service.get_file_links(file_id)

    if current_user.is_authenticated:
        user_name = current_user.name
        is_admin = user_perms('', user_type='admin')
    else:
        user_name = ""
        is_admin = False
    logger.info("project_alias: {}".format(project_alias))

    # kiosk mode
    kiosk, user_address = kiosk_mode(request, settings.kiosks)

    viewer = resolve_image_viewer(
        file_details['folder_transcription_id'],
        file_id,
        file_details['file_name'],
        transcription=True,
    )
    zoom_exists = viewer['zoom_exists']
    zoom_filename = viewer['zoom_filename']
    iiif_image = viewer['iiif_image']

    return render_template('file_transcription.html',
                           folder_info=folder_info, zoom_exists=zoom_exists, zoom_filename=zoom_filename,
                           iiif_image=iiif_image,
                           file_details=file_details, file_checks=file_checks, username=user_name, image_url=image_url,
                           is_admin=is_admin, project_alias=project_alias, file_links=file_links,
                           transcription=transcription, tables=tables,
                           form=form, site_env=site_env,
                           site_net=site_net, site_ver=site_ver, kiosk=kiosk, analytics_code=settings.analytics_code)


@files_bp.route('/file/', methods=['GET'], provide_automatic_options=False)
def file_empty():
    return redirect(url_for('homepage'))


@files_bp.route('/file_transcription/', methods=['GET'], provide_automatic_options=False)
def file_t_empty():
    return redirect(url_for('homepage'))


@files_bp.route('/preview/<folder_id>/<file_id>/', methods=['GET'], provide_automatic_options=False)
def preview_image(folder_id=None, file_id=None):
    """Redirect to the 160px preview thumbnail, or the missing-image SVG placeholder if it doesn't exist on disk."""
    transcription = request.args.get('transcription') == '1'
    path = static_preview_path(folder_id, file_id, size="160", transcription=transcription)
    if path == "na_160.png":
        return redirect(url_for('static', filename='missing_image.svg'))
    return redirect(url_for('static', filename=path))


@cache.memoize()
@files_bp.route('/dashboard/<project_alias>/search_files', methods=['GET'], provide_automatic_options=False)
def search_files(project_alias):
    """Search files by filename."""
    site_env = settings.env
    site_net = settings.site_net
    site_ver = getattr(settings, 'site_ver', '2.11.1')

    if site_net == "api":
        return redirect(url_for('api.api_route_list'))

    form = LoginForm(request.form)
    q = (request.values.get('q') or '').strip()
    page = request.values.get('page')
    try:
        page = max(0, int(page or 0))
    except (TypeError, ValueError):
        page = 0

    if not q:
        kiosk, user_address = kiosk_mode(request, settings.kiosks)
        return render_template(
            'search_files.html',
            results=[],
            project_info=None,
            project_alias=project_alias,
            q='',
            total=0,
            page=0,
            page_size=file_search_service.PAGE_SIZE,
            has_prev=False,
            has_next=False,
            form=form,
            site_env=site_env,
            site_net=site_net,
            site_ver=site_ver,
            kiosk=kiosk,
            user_address=user_address,
            analytics_code=settings.analytics_code,
        )

    project_info, results, total, page, page_size = file_search_service.search_files(
        project_alias, q, page=page,
    )
    if project_info is None:
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

    logger.info("search_files q=%r page=%s total=%s", q, page, total)
    kiosk, user_address = kiosk_mode(request, settings.kiosks)
    offset = page * page_size

    return render_template(
        'search_files.html',
        results=results,
        project_info=project_info,
        project_alias=project_alias,
        q=q,
        total=total,
        page=page,
        page_size=page_size,
        has_prev=page > 0,
        has_next=(offset + len(results)) < total,
        form=form,
        site_env=site_env,
        site_net=site_net,
        site_ver=site_ver,
        kiosk=kiosk,
        user_address=user_address,
        analytics_code=settings.analytics_code,
    )


@files_bp.route('/folder_update/<project_alias>/<folder_id>', methods=['GET'], provide_automatic_options=False)
@login_required
def update_folder_dams(project_alias=None, folder_id=None):
    """Update folder when sending to DAMS"""
    site_net = settings.site_net

    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api.api_route_list'))

    if folder_id is None or project_alias is None:
        return redirect(url_for('home'))

    files_service.send_folder_to_dams(folder_id)

    return redirect(url_for('dashboard_f', project_alias=project_alias, folder_id=folder_id))


@files_bp.route('/update_image/', methods=['POST'], provide_automatic_options=False)
@login_required
def update_image():
    """Update image as having sensitive contents"""
    site_net = settings.site_net

    # If API, not allowed - to improve
    if site_net == "api":
        return redirect(url_for('api.api_route_list'))

    if not current_user.is_authenticated:
        return redirect(url_for('homepage'))

    file_id = int(request.form['file_id'])
    sensitive_info = request.form['sensitive_info']

    files_service.mark_file_sensitive(file_id, sensitive_info, current_user.id)

    return redirect(url_for('files.file', file_id=file_id))
