"""Transcription profile: DB side (settings, streaming, storing, reading).

Computed out-of-band by scripts/materialize_reports.py (report id
'transcription_profile'); the web report and the dashboard panel only read
the stored results. Analysis logic is in transcription_profile_analysis.py.
"""

from __future__ import annotations

import json
import time

from logger import logger
from osprey.db import executemany, iter_query, query_database_insert, run_query
from osprey.services.folder_details import parse_folder_id
from osprey.services.transcription_profile_analysis import (
    FieldAccumulator,
    build_field_profile,
    normalize,
    rank_suspicious,
)

REPORT_ID = 'transcription_profile'

# Seed lists, copied into transcription_profile_terms the first time a project
# is profiled. After that, the DB rows are the source of truth.
DEFAULT_NONSTRING_TERMS = [
    'n/a', 'na', 'none', 'null', 'unknown', 'illegible', 'not legible',
    'blank', 'no data', 'not applicable',
]
DEFAULT_BOILERPLATE = [
    'as an ai', 'language model', 'i cannot', "i can't", 'i am unable',
    "i'm unable", 'the image shows', 'the image contains', 'not visible in the image',
    'here is the transcription', 'transcribed text',
]


# ---------------------------------------------------------------- settings

def _seed_project(project_id):
    """Insert default settings and term rows for a project profiled for the first time."""
    query_database_insert(
        'INSERT IGNORE INTO transcription_profile_settings (project_id) VALUES (%(project_id)s)',
        {'project_id': project_id},
    )
    terms = (
        [{'project_id': project_id, 'term_type': 'nonstring', 'term': t} for t in DEFAULT_NONSTRING_TERMS]
        + [{'project_id': project_id, 'term_type': 'boilerplate', 'term': t} for t in DEFAULT_BOILERPLATE]
    )
    executemany(
        'INSERT IGNORE INTO transcription_profile_terms (project_id, term_type, term) '
        'VALUES (%(project_id)s, %(term_type)s, %(term)s)',
        terms,
    )


def load_settings(project_id):
    """Return (settings_row, nonstring_set, boilerplate_list), seeding defaults if missing."""
    query = 'SELECT * FROM transcription_profile_settings WHERE project_id = %(project_id)s'
    rows = run_query(query, {'project_id': project_id})
    if not rows:
        _seed_project(project_id)
        rows = run_query(query, {'project_id': project_id})
    terms = run_query(
        'SELECT term_type, term FROM transcription_profile_terms WHERE project_id = %(project_id)s',
        {'project_id': project_id},
    )
    # Terms are compared to normalized values, so normalize them the same way.
    nonstring_terms = {normalize(r['term']) for r in terms if r['term_type'] == 'nonstring'}
    boilerplate = [normalize(r['term']) for r in terms if r['term_type'] == 'boilerplate']
    nonstring_terms.discard('')
    return rows[0], nonstring_terms, [t for t in boilerplate if t]


# ---------------------------------------------------------------- compute

def list_sources(project_id):
    return run_query(
        'SELECT transcription_source_id AS source_id, transcription_source_name AS source_name '
        'FROM transcription_sources WHERE project_id = %(project_id)s '
        'ORDER BY transcription_source_name',
        {'project_id': project_id},
    )


def _list_fields(source_id):
    return run_query(
        'SELECT field_id, field_name, sort_by FROM transcription_fields '
        'WHERE transcription_source_id = %(source_id)s ORDER BY sort_by, field_name',
        {'source_id': source_id},
    )


def _folder_totals(source_id):
    """Files with any text for this source, per folder (the fill-rate denominator)."""
    rows = run_query(
        'SELECT f.folder_transcription_id AS folder_id, '
        '       COUNT(DISTINCT t.file_transcription_id) AS total_files '
        'FROM transcription_files_text t '
        'JOIN transcription_fields fl ON fl.field_id = t.field_id '
        'JOIN transcription_files f ON f.file_transcription_id = t.file_transcription_id '
        'WHERE fl.transcription_source_id = %(source_id)s '
        'GROUP BY f.folder_transcription_id',
        {'source_id': source_id},
    )
    return {r['folder_id']: int(r['total_files']) for r in rows}


def _accumulate_field(field_id, nonstring_terms):
    """Stream one field's text rows into an accumulator. Returns (acc, rows_read)."""
    acc = FieldAccumulator(nonstring_terms)
    rows_read = 0
    query = (
        'SELECT t.file_transcription_id AS file_id, f.folder_transcription_id AS folder_id, '
        '       t.transcription_text AS text '
        'FROM transcription_files_text t '
        'JOIN transcription_files f ON f.file_transcription_id = t.file_transcription_id '
        'WHERE t.field_id = %(field_id)s'
    )
    for chunk in iter_query(query, {'field_id': field_id}):
        for row in chunk:
            acc.add(row['file_id'], row['folder_id'], row['text'])
        rows_read += len(chunk)
    return acc, rows_read


def _save_fill(project_id, source_id, fields, totals, accs):
    """Replace this source's per-folder fill rows."""
    rows = []
    for folder_id, total in totals.items():
        for field in fields:
            acc = accs[field['field_id']]
            rows.append({
                'project_id': project_id,
                'source_id': source_id,
                'folder_id': folder_id,
                'field_id': field['field_id'],
                'field_name': field['field_name'],
                'sort_by': field['sort_by'],
                'total_files': total,
                'filled': acc.filled_by_folder[folder_id],
                'nonstring': acc.nonstring_by_folder[folder_id],
            })
    run_query(
        'DELETE FROM transcription_profile_fill WHERE transcription_source_id = %(source_id)s',
        {'source_id': source_id},
        return_val=False,
    )
    if rows:
        executemany(
            'INSERT INTO transcription_profile_fill '
            '(project_id, transcription_source_id, folder_transcription_id, field_id, field_name, '
            ' sort_by, total_files, filled, nonstring) VALUES '
            '(%(project_id)s, %(source_id)s, %(folder_id)s, %(field_id)s, %(field_name)s, '
            ' %(sort_by)s, %(total_files)s, %(filled)s, %(nonstring)s)',
            rows,
        )


def _save_results(project_id, source_id, payload):
    query_database_insert(
        'INSERT INTO transcription_profile_results (transcription_source_id, project_id, computed_at, payload) '
        'VALUES (%(source_id)s, %(project_id)s, CURRENT_TIMESTAMP, %(payload)s) '
        'ON DUPLICATE KEY UPDATE project_id = VALUES(project_id), '
        '  computed_at = CURRENT_TIMESTAMP, payload = VALUES(payload)',
        {'source_id': source_id, 'project_id': project_id, 'payload': json.dumps(payload)},
    )


def materialize_project(project_id):
    """Profile every transcription source of a project. Returns text rows read."""
    settings, nonstring_terms, boilerplate = load_settings(project_id)
    total_rows = 0
    for source in list_sources(project_id):
        source_id = source['source_id']
        start = time.time()
        fields = _list_fields(source_id)
        totals = _folder_totals(source_id)
        accs = {}
        profiles = []
        for field in fields:
            # One field at a time keeps peak memory to a single field's values.
            acc, rows_read = _accumulate_field(field['field_id'], nonstring_terms)
            total_rows += rows_read
            accs[field['field_id']] = acc
            profiles.append(build_field_profile(acc, settings, boilerplate, field['field_name']))
        _save_fill(project_id, source_id, fields, totals, accs)
        _save_results(project_id, source_id, {
            'fields': [{k: v for k, v in p.items() if k != 'suspicious'} for p in profiles],
            'suspicious': rank_suspicious(profiles, int(settings['max_suspicious'])),
        })
        logger.info(f"transcription_profile: source {source_id} done in {time.time() - start:.1f}s")
    return total_rows


# ---------------------------------------------------------------- read (web)

def fill_percentages(total, filled, nonstring):
    """Return counts and percentages (filled / nonstring / empty) for one field."""
    total, filled, nonstring = int(total or 0), int(filled or 0), int(nonstring or 0)
    empty = max(total - filled - nonstring, 0)

    def pct(n):
        return round(100.0 * n / total, 1) if total else 0.0

    return {
        'total_files': total, 'filled': filled, 'nonstring': nonstring, 'empty': empty,
        'filled_pct': pct(filled), 'nonstring_pct': pct(nonstring), 'empty_pct': pct(empty),
    }


def get_report_view(project_id, source_id=None):
    """Data for the report page: sources, selected source, fill rows, stored payload."""
    sources = list_sources(project_id)
    view = {'sources': sources, 'source': None, 'fill': [], 'total_files': 0,
            'payload': None, 'computed_at': None}
    if not sources:
        return view
    view['source'] = next((s for s in sources if str(s['source_id']) == str(source_id)), sources[0])
    sid = view['source']['source_id']

    rows = run_query(
        'SELECT field_name, MIN(sort_by) AS sort_by, SUM(total_files) AS total_files, '
        '       SUM(filled) AS filled, SUM(nonstring) AS nonstring '
        'FROM transcription_profile_fill WHERE transcription_source_id = %(source_id)s '
        'GROUP BY field_id, field_name ORDER BY sort_by, field_name',
        {'source_id': sid},
    )
    view['fill'] = [
        dict(field_name=r['field_name'], **fill_percentages(r['total_files'], r['filled'], r['nonstring']))
        for r in rows
    ]
    # Same denominator for every field of a source, so it is shown once, not per row.
    view['total_files'] = view['fill'][0]['total_files'] if view['fill'] else 0

    results = run_query(
        "SELECT DATE_FORMAT(computed_at, '%Y-%m-%d %H:%i') AS computed_at, payload "
        'FROM transcription_profile_results WHERE transcription_source_id = %(source_id)s',
        {'source_id': sid},
    )
    if results:
        view['computed_at'] = results[0]['computed_at']
        view['payload'] = json.loads(results[0]['payload'])
    return view


def get_folder_fill_payload(folder_id_raw):
    """Per-source fill rates for one folder (dashboard panel). Returns (payload, status, message)."""
    try:
        folder_id, transcription = parse_folder_id(folder_id_raw)
    except ValueError as err:
        return None, 400, str(err)
    payload = {'folder_id': folder_id, 'sources': []}
    if transcription != 1:
        return payload, 200, None

    rows = run_query(
        'SELECT p.transcription_source_id AS source_id, s.transcription_source_name AS source_name, '
        '       p.field_name, p.total_files, p.filled, p.nonstring, '
        "       DATE_FORMAT(p.computed_at, '%Y-%m-%d %H:%i') AS computed_at "
        'FROM transcription_profile_fill p '
        'JOIN transcription_sources s ON s.transcription_source_id = p.transcription_source_id '
        'WHERE p.folder_transcription_id = %(folder_id)s '
        'ORDER BY s.transcription_source_name, p.sort_by, p.field_name',
        {'folder_id': folder_id},
    )
    by_source = {}
    for r in rows:
        source = by_source.setdefault(r['source_id'], {
            'source_id': r['source_id'], 'source_name': r['source_name'],
            'computed_at': r['computed_at'], 'fields': [],
            # Same for every field of the source; shown once in the panel header.
            'total_files': int(r['total_files'] or 0),
        })
        source['fields'].append(
            dict(field_name=r['field_name'], **fill_percentages(r['total_files'], r['filled'], r['nonstring']))
        )
    payload['sources'] = list(by_source.values())
    return payload, 200, None
