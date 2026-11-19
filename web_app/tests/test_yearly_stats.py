"""Nightly project statistics: projects_stats recalculation and this year's new images and objects."""

from datetime import date
from unittest.mock import patch

from osprey.services import yearly_stats as ys


# ---- recalculation of projects_stats ----------------------------------------

def test_refresh_recalculates_ongoing_projects_and_survives_a_failure():
    projects = [{'project_id': 1, 'transcription': 0}, {'project_id': 2, 'transcription': 1},
                {'project_id': 3, 'transcription': 0}]

    def recalc(project_id, transcription):
        if project_id == 2:
            raise ValueError('Invalid project_object_query')

    with patch.object(ys, 'run_query', return_value=projects) as rq, \
            patch.object(ys.folder_stats, 'recalculate_project_stats', side_effect=recalc) as rp:
        assert ys.refresh_project_stats() == (2, [2])
    query = rq.call_args.args[0]
    assert "project_status = 'Ongoing'" in query and 'skip_project IS NOT True' in query
    assert [c.args for c in rp.call_args_list] == [(1, 0), (2, 1), (3, 0)]


# ---- this year's counts -------------------------------------------------------

def test_count_year_counts_files_created_that_year_with_the_object_expression():
    with patch.object(ys, 'run_query', return_value=[{'images': 40, 'objects': 20}]) as rq:
        assert ys.count_year(7, 0, 'count(distinct f.file_name)', 2026) == (40, 20)
    query, params = rq.call_args.args
    assert 'count(distinct f.file_name) AS objects' in query and 'COUNT(f.file_name) AS images' in query
    assert 'FROM files f, folders fol' in query
    assert 'f.created_at >= %(start)s AND f.created_at < %(end)s' in query
    assert params == {'project_id': 7, 'start': '2026-01-01', 'end': '2027-01-01'}


def test_count_year_uses_transcription_files_for_transcription_projects():
    with patch.object(ys, 'run_query', return_value=[{'images': 1, 'objects': 1}]) as rq:
        ys.count_year(8, 1, 'count(f.file_name)', 2026)
    assert 'FROM transcription_files f, transcription_folders fol' in rq.call_args.args[0]
    with patch.object(ys, 'run_query', return_value=[{'images': 3, 'objects': 0}]) as rq:
        assert ys.count_year(8, 0, None, 2026) == (3, 0)
    assert '0 AS objects' in rq.call_args.args[0]


def test_compute_year_rows_keeps_going_past_bad_projects():
    projects = [
        {'project_id': 1, 'project_title': 'Bees', 'transcription': 0, 'project_object_query': 'count(f.file_name)'},
        {'project_id': 2, 'project_title': 'Bad', 'transcription': 0, 'project_object_query': 'sleep(5)'},
        {'project_id': 3, 'project_title': 'None', 'transcription': 1, 'project_object_query': None},
        {'project_id': 4, 'project_title': 'Broken', 'transcription': 0, 'project_object_query': 'count(f.file_name)'},
    ]
    calls = []

    def count(pid, transcription, expr, year):
        calls.append((pid, transcription, expr, year))
        if pid == 4:
            raise RuntimeError('lost connection')
        return {1: (900, 300), 2: (50, 0), 3: (10, 0)}[pid]

    with patch.object(ys, 'run_query', return_value=projects), patch.object(ys, 'count_year', side_effect=count):
        rows = {r['project_id']: r for r in ys.compute_year_rows(2026)}
    assert (rows[1]['images'], rows[1]['objects'], rows[1]['error']) == (900, 300, '')
    # Bad or missing expression: images still counted, objects not.
    assert rows[2]['images'] == 50 and 'objects not counted' in rows[2]['error']
    assert rows[3]['images'] == 10 and rows[3]['error']
    assert calls[1][2] is None and calls[2][:2] == (3, 1)
    assert rows[4]['failed'] and 'count failed' in rows[4]['error']


def test_write_year_rows_upserts_and_skips_failed_counts():
    rows = [{'project_id': 1, 'objects': 300, 'images': 900, 'error': ''},
            {'project_id': 4, 'objects': 0, 'images': 0, 'error': 'count failed', 'failed': True}]
    with patch.object(ys, 'run_query') as rq:
        assert ys.write_year_rows(rows, 2026) == 1
    query, params = rq.call_args.args
    assert query.startswith('INSERT INTO projects_stats_yearly') and 'ON DUPLICATE KEY UPDATE' in query
    assert params == {'project_id': 1, 'year': 2026, 'objects': 300, 'images': 900}


def test_load_year_totals_filters_like_the_cards():
    with patch.object(ys, 'run_query', return_value=[{'projects': 3, 'objects': 120, 'images': 300}]) as rq:
        assert ys.load_year_totals('MD', 2026) == {'objects': 120, 'images': 300, 'year': 2026}
    query, params = rq.call_args.args
    assert 'skip_project IS NOT True' in query and 'p.project_section = %(section)s' in query
    assert params == {'year': 2026, 'section': 'MD'}
    with patch.object(ys, 'run_query', return_value=[{'projects': 0, 'objects': 0, 'images': 0}]) as rq:
        assert ys.load_year_totals(None, 2026) is None
    assert 'project_section' not in rq.call_args.args[0]


# ---- nightly script -----------------------------------------------------------

def _script():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent / 'scripts' / 'nightly_project_stats.py'
    spec = importlib.util.spec_from_file_location('nightly_project_stats', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_ROWS = [{'project_id': 1, 'project_title': 'Bees', 'images': 900, 'objects': 300, 'error': ''}]


def test_script_recalculates_then_counts_this_year(capsys):
    script = _script()
    order = []
    with patch.object(ys, 'refresh_project_stats', side_effect=lambda: order.append('refresh') or (4, [])), \
            patch.object(ys, 'compute_year_rows', side_effect=lambda y: order.append(('count', y)) or _ROWS), \
            patch.object(ys, 'write_year_rows', return_value=1):
        assert script.main([]) == 0
    assert order == ['refresh', ('count', date.today().year)]
    assert '300 objects and 900 images' in capsys.readouterr().out


def test_script_counts_only_and_another_year():
    script = _script()
    with patch.object(ys, 'refresh_project_stats') as refresh, \
            patch.object(ys, 'compute_year_rows', return_value=_ROWS) as compute, \
            patch.object(ys, 'write_year_rows', return_value=1) as write:
        assert script.main(['--counts-only', '--year', '2025']) == 0
    refresh.assert_not_called()
    compute.assert_called_once_with(2025)
    write.assert_called_once_with(_ROWS, 2025)


def test_script_reports_problems_through_the_exit_code():
    script = _script()
    bad = [dict(_ROWS[0], error='invalid project_object_query (x); objects not counted')]
    with patch.object(ys, 'refresh_project_stats', return_value=(3, [7])), \
            patch.object(ys, 'compute_year_rows', return_value=_ROWS), patch.object(ys, 'write_year_rows', return_value=1):
        assert script.main([]) == 1
    with patch.object(ys, 'refresh_project_stats', return_value=(3, [])), \
            patch.object(ys, 'compute_year_rows', return_value=bad), patch.object(ys, 'write_year_rows', return_value=1):
        assert script.main([]) == 1
    with patch.object(ys, 'refresh_project_stats', return_value=(3, [])), \
            patch.object(ys, 'compute_year_rows', return_value=_ROWS), \
            patch.object(ys, 'write_year_rows', side_effect=RuntimeError("Table doesn't exist")):
        assert script.main([]) == 1
