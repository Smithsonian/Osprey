"""Daily copies of each project's totals (projects_stats_history) and the yearly change built on them.

The nightly job recalculates projects_stats for ongoing projects
(refresh_project_stats), then copies it into projects_stats_history. The
homepage's "+N in <year>" is today's projects_stats total minus each
project's baseline for the year:

- the last copy dated before 1 January of the year, when history reaches
  back that far (the normal case from the second year on);
- otherwise, in the year history started, the project's first copy that
  year, and the highlight is labelled "since <that date>";
- a project with no baseline at all (added after history started) counts in
  full, since all of its work is new.
"""

from __future__ import annotations

from datetime import date

from logger import logger
from osprey.db import run_query
from osprey.services import folder_stats

TABLE = 'projects_stats_history'


def refresh_project_stats():
    """Recalculate projects_stats for every ongoing, listed project before it is copied.

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


def snapshot(day=None):
    """Copy every project's current totals into the history for `day` (default today).

    Re-running on the same day overwrites that day's copy. Returns the number
    of projects copied.
    """
    params = {'day': (day or date.today()).isoformat()}
    run_query(
        'INSERT INTO projects_stats_history (project_id, stat_date, objects_digitized, images_taken) '
        'SELECT project_id, %(day)s, COALESCE(objects_digitized, 0), COALESCE(images_taken, 0) '
        'FROM projects_stats '
        'ON DUPLICATE KEY UPDATE objects_digitized = VALUES(objects_digitized), '
        '  images_taken = VALUES(images_taken)',
        params,
        return_val=False,
    )
    return int(run_query(
        'SELECT COUNT(*) AS n FROM projects_stats_history WHERE stat_date = %(day)s', params)[0]['n'] or 0)


def load_baselines(year):
    """{project_id: {objects, images, stat_date}}: each project's starting totals for `year`."""
    jan1 = date(year, 1, 1).isoformat()
    rows = run_query(
        'SELECT h.project_id, h.stat_date, h.objects_digitized, h.images_taken '
        'FROM projects_stats_history h '
        'JOIN (SELECT project_id, MAX(stat_date) AS stat_date FROM projects_stats_history '
        '      WHERE stat_date < %(jan1)s GROUP BY project_id) b '
        '  ON b.project_id = h.project_id AND b.stat_date = h.stat_date',
        {'jan1': jan1},
    )
    if not rows:
        # Nothing before this year: history started this year, so count from
        # each project's first copy.
        rows = run_query(
            'SELECT h.project_id, h.stat_date, h.objects_digitized, h.images_taken '
            'FROM projects_stats_history h '
            'JOIN (SELECT project_id, MIN(stat_date) AS stat_date FROM projects_stats_history '
            '      WHERE stat_date >= %(jan1)s GROUP BY project_id) b '
            '  ON b.project_id = h.project_id AND b.stat_date = h.stat_date',
            {'jan1': jan1},
        )
    return {
        row['project_id']: {
            'objects': int(row['objects_digitized'] or 0),
            'images': int(row['images_taken'] or 0),
            'stat_date': row['stat_date'],
        }
        for row in rows or []
    }


def year_change(current, baselines, year):
    """This year's change from per-project totals.

    current: [{project_id, objects, images}] from projects_stats for the
    projects on the cards. Returns {'objects', 'images', 'year', 'since'}
    where since is None when every baseline is from before 1 January,
    otherwise the earliest baseline date this year. Returns None when there
    is no history yet. A total that went down (a correction) shows as 0.
    """
    if not baselines:
        return None
    jan1 = date(year, 1, 1)
    objects = images = 0
    since = None
    for row in current:
        base = baselines.get(row['project_id'])
        if base is None:
            objects += row['objects']
            images += row['images']
            continue
        objects += row['objects'] - base['objects']
        images += row['images'] - base['images']
        if base['stat_date'] >= jan1 and (since is None or base['stat_date'] < since):
            since = base['stat_date']
    return {'objects': max(objects, 0), 'images': max(images, 0), 'year': year, 'since': since}


def load_current_totals(section=None):
    """[{project_id, objects, images}] for the projects the homepage cards count."""
    where = 'WHERE p.skip_project IS NOT True'
    params = {}
    if section:
        where += ' AND p.project_section = %(section)s'
        params['section'] = section
    rows = run_query(
        'SELECT p.project_id, COALESCE(ps.objects_digitized, 0) AS objects, '
        '  COALESCE(ps.images_taken, 0) AS images '
        'FROM projects p LEFT JOIN projects_stats ps ON ps.project_id = p.project_id ' + where,
        params,
    )
    return [{'project_id': r['project_id'], 'objects': int(r['objects'] or 0), 'images': int(r['images'] or 0)}
            for r in rows or []]


# ---- one-off backfill of a year's starting point -----------------------------
#
# History only exists from the first nightly copy, so the year it starts has
# no copy from before 1 January. backfill_rows() rebuilds one: each project's
# current projects_stats totals minus the work its files show since
# 1 January. Subtracting (rather than counting the files from before 1 January)
# keeps hand-entered or estimated totals out of the year's change: only work
# that Osprey has files for is counted as this year's.

def _file_scope(transcription):
    """(FROM/WHERE for one project's files, date column) as used by recalculate_project_stats."""
    if transcription:
        # transcription_files has no capture date: use when the worker registered the file.
        return ('FROM transcription_files f, transcription_folders fol '
                'WHERE fol.project_id = %(project_id)s '
                '  AND fol.folder_transcription_id = f.folder_transcription_id', 'f.created_at')
    # Capture date, or when the file was registered when the capture date is unknown.
    return ('FROM files f, folders fol '
            'WHERE fol.project_id = %(project_id)s AND fol.folder_id = f.folder_id',
            'COALESCE(f.datetime_created, f.created_at)')


def work_since(project_id, transcription, object_expr, start):
    """(images, objects) the project's files show from `start` (a date) on.

    object_expr is the project's project_object_query (already checked with
    assert_safe_sql_expression), the same expression the roll-up uses.
    """
    scope, date_col = _file_scope(transcription)
    row = run_query(
        f'SELECT COUNT(f.file_name) AS images, {object_expr} AS objects {scope} AND {date_col} >= %(start)s',
        {'project_id': project_id, 'start': start.isoformat()},
        log_vals=False,
    )[0]
    return int(row['images'] or 0), int(row['objects'] or 0)


def backfill_rows(year):
    """Starting totals for `year`, one per project in projects_stats, dated 31 December of the year before.

    Each row: project_id, project_title, objects/images (the starting totals),
    objects_since/images_since (this year's work from files), and error
    (set when the project's object expression is invalid; its starting
    totals are then its current ones, so it adds nothing to the year).
    """
    from osprey.services.file_checks import assert_safe_sql_expression

    start = date(year, 1, 1)
    projects = run_query(
        'SELECT ps.project_id, p.project_title, COALESCE(p.transcription, 0) AS transcription, '
        '  p.project_object_query, COALESCE(ps.objects_digitized, 0) AS objects, '
        '  COALESCE(ps.images_taken, 0) AS images '
        'FROM projects_stats ps JOIN projects p ON p.project_id = ps.project_id '
        'ORDER BY ps.project_id',
        log_vals=False,
    )
    out = []
    for project in projects or []:
        row = {
            'project_id': project['project_id'],
            'project_title': project.get('project_title') or '',
            'objects_since': 0,
            'images_since': 0,
            'error': '',
        }
        try:
            object_expr = assert_safe_sql_expression(project['project_object_query'])
            row['images_since'], row['objects_since'] = work_since(
                project['project_id'], int(project['transcription']), object_expr, start)
        except (ValueError, TypeError) as err:  # TypeError: no project_object_query set
            row['error'] = 'invalid project_object_query: {}'.format(err)
        # A total lower than its files show (stale or hand-entered) would go
        # negative: start from 0 then, so the year counts what the files show.
        row['objects'] = max(int(project['objects']) - row['objects_since'], 0)
        row['images'] = max(int(project['images']) - row['images_since'], 0)
        out.append(row)
    return out


def write_backfill(rows, year, replace=False):
    """Store backfill_rows() as the copies dated 31 December of the year before.

    Existing copies for that date are kept unless replace is True. Returns
    the number of rows written.
    """
    day = date(year - 1, 12, 31).isoformat()
    verb = 'INSERT' if replace else 'INSERT IGNORE'
    tail = (' ON DUPLICATE KEY UPDATE objects_digitized = VALUES(objects_digitized), '
            'images_taken = VALUES(images_taken)') if replace else ''
    written = 0
    for row in rows:
        run_query(
            f'{verb} INTO projects_stats_history (project_id, stat_date, objects_digitized, images_taken) '
            'VALUES (%(project_id)s, %(day)s, %(objects)s, %(images)s)' + tail,
            {'project_id': row['project_id'], 'day': day, 'objects': row['objects'], 'images': row['images']},
            return_val=False, log_vals=False,
        )
        written += 1
    return written
