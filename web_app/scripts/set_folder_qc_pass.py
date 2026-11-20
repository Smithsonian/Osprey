#!/usr/bin/env python3
"""Mark a folder's QC result as passed, with a custom message.

Writes what the web QC flow (app.py qc_done) saves for a pass, without
computing it from the sampled files:

  - qc_folders: qc_status = 0, <message> appended to qc_info as
    "<old comment> | <message>" (just <message> when it was empty), qc_level / qc_method
    from the project's qc_settings, and qc_by when --user is given
    (a qc_folders row is created if the folder never entered QC)
  - folders_badges: the 'qc_status' badge set to "QC Passed"
  - audit_log: a 'qc_decision' event noting the override and message

qc_files ratings and the project's inspection level are left alone.

    set_folder_qc_pass.py 1234 "Passed after manual review"
    set_folder_qc_pass.py 1234 "Re-scanned by vendor" --user jdoe
    set_folder_qc_pass.py 6f1c...-uuid "Approved" --dry-run    (transcription folder)

Run from the web_app root with PYTHONPATH=. (needs settings.py).
Exit code 1 when the folder or user is not found or the combined comment is too long.
"""

from __future__ import annotations

import argparse
import sys
from uuid import UUID

import settings  # noqa: F401  (database settings for osprey.db)
from osprey import audit
from osprey.db import query_database_insert, run_query
from osprey.services import qc as qc_service

QC_INFO_MAX = 254  # qc_folders.qc_info is varchar(254)
QC_INFO_SEPARATOR = ' | '


def combined_info(old, message):
    """The new qc_info: the old comment, a pipe, then the message (just the message if there was none)."""
    old = (old or '').strip()
    return f"{old}{QC_INFO_SEPARATOR}{message}" if old else message


def parse_folder_id(value):
    """(folder_id, transcription): an int for regular folders, a UUID string for transcription folders."""
    try:
        return int(value), False
    except ValueError:
        pass
    try:
        return str(UUID(value)), True
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a folder id or UUID: {value!r}")


def load_folder(folder_id, transcription):
    if transcription:
        rows = run_query(
            "SELECT f.folder_transcription_id AS folder_id, f.project_id, f.folder AS folder_name "
            "  FROM transcription_folders f WHERE f.folder_transcription_id = %(folder_id)s",
            {'folder_id': folder_id})
    else:
        rows = run_query(
            "SELECT f.folder_id, f.project_id, f.project_folder AS folder_name "
            "  FROM folders f WHERE f.folder_id = %(folder_id)s",
            {'folder_id': folder_id})
    return rows[0] if rows else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('folder_id', type=parse_folder_id,
                        help='folder_id, or the folder UUID for transcription projects')
    parser.add_argument('message', help='custom QC message appended to qc_info as "<old> | <message>" '
                                        f'(the result must fit in {QC_INFO_MAX} chars)')
    parser.add_argument('--user', help='username to record as the QC reviewer (qc_by); default keeps the current one')
    parser.add_argument('--dry-run', action='store_true', help='show what would change without writing')
    args = parser.parse_args(argv)

    folder_id, transcription = args.folder_id
    message = args.message.strip()
    if not message:
        print("message is empty", file=sys.stderr)
        return 1
    if len(message) > QC_INFO_MAX:
        print(f"message is {len(message)} characters; qc_info holds {QC_INFO_MAX}", file=sys.stderr)
        return 1

    folder = load_folder(folder_id, transcription)
    if folder is None:
        print(f"folder {folder_id} not found", file=sys.stderr)
        return 1
    project_id = folder['project_id']

    settings_rows = run_query("SELECT * FROM qc_settings WHERE project_id = %(project_id)s",
                              {'project_id': project_id})
    if not settings_rows:
        print(f"project {project_id} has no qc_settings row", file=sys.stderr)
        return 1
    qc_settings = settings_rows[0]

    qc_by = None
    if args.user:
        users = run_query("SELECT user_id FROM users WHERE username = %(username)s", {'username': args.user})
        if not users:
            print(f"user {args.user!r} not found", file=sys.stderr)
            return 1
        qc_by = users[0]['user_id']

    fold_col = "folder_uid" if transcription else "folder_id"
    params = {'folder_id': folder_id}
    current = run_query(f"SELECT qc_status, qc_by, qc_info FROM qc_folders WHERE {fold_col} = %(folder_id)s", params)

    print(f"folder {folder_id} ({folder['folder_name']}), project {project_id}")
    new_by = qc_by if qc_by is not None else '(unchanged)'
    too_long = False
    if current:
        for row in current:
            new_info = combined_info(row['qc_info'], message)
            print(f"  current: qc_status={row['qc_status']} qc_by={row['qc_by']} qc_info={row['qc_info']!r}")
            print(f"  new:     qc_status=0 qc_by={new_by} qc_info={new_info!r}")
            too_long = too_long or len(new_info) > QC_INFO_MAX
    else:
        print("  current: no qc_folders row (one will be created)")
        print(f"  new:     qc_status=0 qc_by={new_by} qc_info={message!r}")
    if too_long:
        print(f"the combined comment would exceed the {QC_INFO_MAX} characters qc_info holds; "
              "use a shorter message", file=sys.stderr)
        return 1
    if args.dry_run:
        print("dry run: nothing written")
        return 0

    values = {
        'folder_id': folder_id,
        'qc_info': message,
        'qc_level': qc_settings['qc_level'],
        'qc_method': qc_service.qc_method(qc_settings),
        'qc_by': qc_by,
        'separator': QC_INFO_SEPARATOR,
    }
    if current:
        # Append in SQL so each row keeps its own old comment (mirrors combined_info)
        set_by = ", qc_by = %(qc_by)s" if qc_by is not None else ""
        query_database_insert(
            "UPDATE qc_folders SET qc_status = 0, "
            " qc_info = CASE WHEN TRIM(COALESCE(qc_info, '')) = '' THEN %(qc_info)s "
            "           ELSE CONCAT(TRIM(qc_info), %(separator)s, %(qc_info)s) END, "
            f" qc_level = %(qc_level)s, qc_method = %(qc_method)s{set_by} WHERE {fold_col} = %(folder_id)s",
            values)
    else:
        query_database_insert(
            f"INSERT INTO qc_folders ({fold_col}, qc_status, qc_by, qc_info, qc_level, qc_method) "
            " VALUES (%(folder_id)s, 0, %(qc_by)s, %(qc_info)s, %(qc_level)s, %(qc_method)s)",
            values)

    query_database_insert(
        f"DELETE FROM folders_badges WHERE {fold_col} = %(folder_id)s AND badge_type = 'qc_status'", params)
    query_database_insert(
        f"INSERT INTO folders_badges ({fold_col}, badge_type, badge_css, badge_text, updated_at) "
        " VALUES (%(folder_id)s, 'qc_status', 'bg-success', 'QC Passed', CURRENT_TIMESTAMP)",
        params)

    audit.record('update', 'folder', 'qc_decision', project_id=project_id,
                 folder_ref=folder_id, transcription=transcription,
                 note=f"QC Passed (manual override): {message}"[:255],
                 details={'qc_info': message, 'qc_by': qc_by})

    print("QC set to passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
