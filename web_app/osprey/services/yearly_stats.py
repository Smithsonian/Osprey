"""Nightly project statistics: recalculated projects_stats, and each year's new images and objects.

Run by scripts/nightly_project_stats.py:

- refresh_project_stats() recalculates projects_stats for ongoing projects,
  so the homepage card totals are current.
- compute_year_rows() / write_year_rows() count, per project, the files
  registered (created_at) in a calendar year and store them in
  projects_stats_yearly. The homepage's "+N in <year>" adds those up
  (load_year_totals).

Images are the project's files (or transcription_files, by its transcription
flag, as the projects_stats roll-up does); objects are its
projects.project_object_query evaluated over the same files.
"""

from __future__ import annotations

from datetime import date

from logger import logger
from osprey.db import run_query
from osprey.services import folder_stats
from osprey.services.file_checks import assert_safe_sql_expression

TABLE = 'projects_stats_yearly'


def refresh_project_stats():
    """Recalculate projects_stats for every ongoing, listed project.

    Uses the same roll-up the worker runs after each folder
    (folder_stats.recalculate_project_stats): images and objects counted from
    the project's files, and the folder file counts. Projects with no files
    in Osprey are left as they are, since that roll-up only updates projects
    it finds files for. Completed projects are not recalculated: their
    totals no longer change.

    One project failing (e.g. an invalid project_object_query) does not stop
    the others. Returns (projects recalculated, [project_ids that failed]).
    """
    rows = run_query(
        "SELECT project_id, COALESCE(transcription, 0) AS transcription FROM projects "
        "WHERE project_status = 'Ongoing' AND skip_project IS NOT True ORDER BY project_id",
        log_vals=False,
    )
    done, failed = 0, []
    for row in rows or []:
        try:
            folder_stats.recalculate_project_stats(row['project_id'], int(row['transcription']))
        except Exception:  # boundary: one bad project must not stop the nightly refresh
            logger.exception("projects_stats refresh failed for project_id=%s", row['project_id'])
            failed.append(row['project_id'])
        else:
            done += 1
    return done, failed


def _file_scope(transcription):
    """FROM/WHERE for one project's files, as used by recalculate_project_stats."""
    if transcription:
        return ('FROM transcription_files f, transcription_folders fol '
                'WHERE fol.project_id = %(project_id)s '
                '  AND fol.folder_transcription_id = f.folder_transcription_id')
    return ('FROM files f, folders fol '
            'WHERE fol.project_id = %(project_id)s AND fol.folder_id = f.folder_id')


def count_year(project_id, transcription, object_expr, year):
    """(images, objects) for the project's files with created_at in `year`.

    object_expr is the project's project_object_query, already checked with
    assert_safe_sql_expression; None counts images only (objects 0).
    """
    objects_sql = object_expr if object_expr else '0'
    row = run_query(
        f'SELECT COUNT(f.file_name) AS images, {objects_sql} AS objects {_file_scope(transcription)} '
        '  AND f.created_at >= %(start)s AND f.created_at < %(end)s',
        {'project_id': project_id, 'start': date(year, 1, 1).isoformat(), 'end': date(year + 1, 1, 1).isoformat()},
        log_vals=False,
    )[0]
    return int(row['images'] or 0), int(row['objects'] or 0)


def compute_year_rows(year):
    """One row per project: {project_id, project_title, images, objects, error} for `year`.

    A project whose project_object_query is missing or fails validation still
    gets its images counted; its objects are 0 and error says why. Any other
    failure for one project is logged, recorded in error, and the rest go on.
    """
    projects = run_query(
        'SELECT project_id, project_title, COALESCE(transcription, 0) AS transcription, project_object_query '
        'FROM projects ORDER BY project_id',
        log_vals=False,
    )
    out = []
    for project in projects or []:
        row = {'project_id': project['project_id'], 'project_title': project.get('project_title') or '',
               'images': 0, 'objects': 0, 'error': ''}
        try:
            object_expr = assert_safe_sql_expression(project['project_object_query'])
        except (ValueError, TypeError) as err:  # TypeError: no project_object_query set
            object_expr = None
            row['error'] = 'invalid project_object_query ({}); objects not counted'.format(err)
        try:
            row['images'], row['objects'] = count_year(
                project['project_id'], int(project['transcription']), object_expr, year)
        except Exception as err:  # boundary: one bad project must not stop the nightly counts
            logger.exception("yearly counts failed for project_id=%s", project['project_id'])
            row['error'] = 'count failed: {}'.format(err)
            row['failed'] = True
        out.append(row)
    return out


def write_year_rows(rows, year):
    """Store the counts for `year`; a re-run overwrites them. Rows whose count failed are skipped.

    Returns the number of rows written.
    """
    written = 0
    for row in rows:
        if row.get('failed'):
            continue
        run_query(
            'INSERT INTO projects_stats_yearly (project_id, year, objects_digitized, images_taken) '
            'VALUES (%(project_id)s, %(year)s, %(objects)s, %(images)s) '
            'ON DUPLICATE KEY UPDATE objects_digitized = VALUES(objects_digitized), '
            '  images_taken = VALUES(images_taken), computed_at = CURRENT_TIMESTAMP',
            {'project_id': row['project_id'], 'year': year, 'objects': row['objects'], 'images': row['images']},
            return_val=False, log_vals=False,
        )
        written += 1
    return written


def load_year_totals(section, year):
    """{'objects', 'images', 'year'} added up over the projects the homepage cards count.

    Same filter as the cards (listed projects, optionally one section).
    None when nothing has been stored for the year yet.
    """
    where = 'WHERE y.year = %(year)s AND p.skip_project IS NOT True'
    params = {'year': year}
    if section:
        where += ' AND p.project_section = %(section)s'
        params['section'] = section
    row = run_query(
        'SELECT COUNT(*) AS projects, COALESCE(SUM(y.objects_digitized), 0) AS objects, '
        '  COALESCE(SUM(y.images_taken), 0) AS images '
        'FROM projects_stats_yearly y JOIN projects p ON p.project_id = y.project_id ' + where,
        params,
    )[0]
    if not row['projects']:
        return None
    return {'objects': int(row['objects'] or 0), 'images': int(row['images'] or 0), 'year': year}
