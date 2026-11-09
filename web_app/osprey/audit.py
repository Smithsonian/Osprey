"""Audit trail of insert/update/delete events on projects, folders and files.

Each event is one ``audit_log`` row (who, when, which project/folder/file,
what happened; see db/audit_log.sql). The request details go to
ospreyaudit.log, on a line carrying the same audit_id and request_id.

Call ``record()`` right after the write it describes. For deletes, call
``lookup_context()`` *before* the DELETE and pass the result as ``context=`` so the
names are captured while the row still exists.

Auditing is best effort: ``record()`` never raises, so a problem with the
audit table cannot break the change being audited. A failed insert is
logged at ERROR with the full event so nothing is lost silently.
"""

import json
import os
import sys
import uuid

from flask import g, has_request_context, request

from logger import audit_logger
from osprey.db import query_database_insert, run_query

ACTIONS = ('insert', 'update', 'delete')
ENTITIES = ('project', 'folder', 'file')

# Form fields never copied into the audit log.
_SECRET_FIELDS = ('api_key', 'csrf_token', 'password')
# Long form values (e.g. a full EXIF dump) are cut to this many characters.
_MAX_DETAIL_VALUE = 2000

_INSERT = (
    "INSERT INTO audit_log "
    " (actor_type, actor, source, action, entity, event, transcription, "
    "  project_id, folder_ref, file_ref, project_alias, folder_name, file_name, note, request_id) "
    "VALUES "
    " (%(actor_type)s, %(actor)s, %(source)s, %(action)s, %(entity)s, %(event)s, %(transcription)s, "
    "  %(project_id)s, %(folder_ref)s, %(file_ref)s, %(project_alias)s, %(folder_name)s, %(file_name)s, "
    "  %(note)s, %(request_id)s)"
)

_CONTEXT_QUERIES = {
    # (entity looked up, transcription) -> query returning the context columns
    ('file', False): (
        "SELECT p.project_id, p.project_alias, fo.folder_id AS folder_ref, "
        "       fo.project_folder AS folder_name, f.file_name "
        "FROM files f "
        "LEFT JOIN folders fo ON fo.folder_id = f.folder_id "
        "LEFT JOIN projects p ON p.project_id = fo.project_id "
        "WHERE f.file_id = %(ref)s"
    ),
    ('file', True): (
        "SELECT p.project_id, p.project_alias, fo.folder_transcription_id AS folder_ref, "
        "       fo.folder AS folder_name, f.file_name "
        "FROM transcription_files f "
        "LEFT JOIN transcription_folders fo ON fo.folder_transcription_id = f.folder_transcription_id "
        "LEFT JOIN projects p ON p.project_id = fo.project_id "
        "WHERE f.file_transcription_id = %(ref)s"
    ),
    ('folder', False): (
        "SELECT p.project_id, p.project_alias, fo.project_folder AS folder_name "
        "FROM folders fo LEFT JOIN projects p ON p.project_id = fo.project_id "
        "WHERE fo.folder_id = %(ref)s"
    ),
    ('folder', True): (
        "SELECT p.project_id, p.project_alias, fo.folder AS folder_name "
        "FROM transcription_folders fo LEFT JOIN projects p ON p.project_id = fo.project_id "
        "WHERE fo.folder_transcription_id = %(ref)s"
    ),
    ('project', False): (
        "SELECT project_id, project_alias FROM projects WHERE project_id = %(ref)s"
    ),
}


def _blank(value):
    return value is None or value == ''


def request_id():
    """The current request's id (created on first use), or None outside a request."""
    if not has_request_context():
        return None
    rid = g.get('request_id')
    if rid is None:
        rid = uuid.uuid4().hex
        g.request_id = rid
    return rid


def _actor():
    """(actor_type, actor, source) for whoever is making the change."""
    if has_request_context():
        api_actor = g.get('api_actor')
        if api_actor:
            return 'api_key', api_actor, 'api'
        try:
            from flask_login import current_user
            if current_user and current_user.is_authenticated:
                return 'user', str(current_user.name), 'web'
        except Exception:  # no login manager on this app/request
            pass
        return 'system', 'anonymous', 'web'
    script = os.path.basename(sys.argv[0]) if sys.argv and sys.argv[0] else ''
    return 'system', script or 'script', 'script'


def _request_details():
    """The request's form fields (secrets removed, long values cut), or None."""
    if not has_request_context():
        return None
    details = {'method': request.method, 'path': request.path}
    for key, value in request.form.items():
        if key in _SECRET_FIELDS:
            continue
        if len(value) > _MAX_DETAIL_VALUE:
            value = value[:_MAX_DETAIL_VALUE] + '...[{} chars]'.format(len(value))
        details[key] = value
    return details


def lookup_context(project_id=None, folder_ref=None, file_ref=None, transcription=False):
    """Look up project/folder/file ids and names for an audit row.

    Uses the most specific ref given (file, then folder, then project). Never
    raises; a failed or empty lookup just returns the ids that were passed in.
    """
    ctx = {
        'project_id': project_id,
        'folder_ref': None if _blank(folder_ref) else str(folder_ref),
        'file_ref': None if _blank(file_ref) else str(file_ref),
        'project_alias': None,
        'folder_name': None,
        'file_name': None,
    }
    if ctx['file_ref'] is not None:
        key, ref = ('file', bool(transcription)), ctx['file_ref']
    elif ctx['folder_ref'] is not None:
        key, ref = ('folder', bool(transcription)), ctx['folder_ref']
    elif not _blank(project_id):
        key, ref = ('project', False), project_id
    else:
        return ctx
    try:
        rows = run_query(_CONTEXT_QUERIES[key], {'ref': ref}, log_vals=False)
    except Exception as err:
        audit_logger.warning("audit context lookup failed ({}): {}={}".format(err, key, ref))
        return ctx
    if rows:
        for column, value in rows[0].items():
            if value is not None and ctx.get(column) is None:
                ctx[column] = str(value) if column == 'folder_ref' else value
    return ctx


def record(action, entity, event, *, project_id=None, folder_ref=None, file_ref=None,
           transcription=False, note=None, details=None, context=None):
    """Write one audit row plus its detail line. Returns the audit_id, or None.

    - ``folder_ref``/``file_ref``: the int id, or the uuid for transcription
      projects. ``entity='file'`` with no ``file_ref`` means a bulk change to
      the folder's files (say how many in ``note``).
    - ``details``: dict for the log line; defaults to the request's form.
    - ``context``: result of ``lookup_context()`` taken before a delete. Explicit
      ids passed here still win over it.
    """
    row = {}
    try:
        if action not in ACTIONS:
            raise ValueError("unknown audit action: {}".format(action))
        if entity not in ENTITIES:
            raise ValueError("unknown audit entity: {}".format(entity))
        ctx = context if context is not None else lookup_context(
            project_id=project_id, folder_ref=folder_ref, file_ref=file_ref,
            transcription=transcription)
        actor_type, actor, source = _actor()
        row = {
            'actor_type': actor_type,
            'actor': actor[:100],
            'source': source,
            'action': action,
            'entity': entity,
            'event': str(event)[:48],
            'transcription': 1 if transcription else 0,
            'project_id': project_id if not _blank(project_id) else ctx.get('project_id'),
            'folder_ref': str(folder_ref) if not _blank(folder_ref) else ctx.get('folder_ref'),
            'file_ref': str(file_ref) if not _blank(file_ref) else ctx.get('file_ref'),
            'project_alias': ctx.get('project_alias'),
            'folder_name': ctx.get('folder_name'),
            'file_name': ctx.get('file_name'),
            'note': None if note is None else str(note)[:255],
            'request_id': request_id(),
        }
        if details is None:
            details = _request_details()
        audit_id = query_database_insert(_INSERT, row, return_res=True)
        audit_logger.info("audit_id={} request_id={} {} {} {} transcription={} by {}:{} project={} folder={} file={} details={}".format(
            audit_id, row['request_id'], row['action'], row['entity'], row['event'],
            row['transcription'], row['actor_type'], row['actor'],
            row['project_id'], row['folder_ref'], row['file_ref'],
            json.dumps(details, default=str)))
        return audit_id
    except Exception as err:
        try:
            audit_logger.error("audit insert failed ({}): row={} details={}".format(
                err, json.dumps(row, default=str), json.dumps(details, default=str)))
        except Exception:
            pass
        return None
