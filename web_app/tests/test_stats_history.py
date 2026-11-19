"""projects_stats_history: nightly copies and the homepage's yearly change."""

from datetime import date
from unittest.mock import patch

from osprey.services import stats_history as sh


def test_snapshot_copies_projects_stats_for_the_day():
    with patch.object(sh, 'run_query', side_effect=[None, [{'n': 12}]]) as rq:
        assert sh.snapshot(date(2026, 11, 10)) == 12
    insert = rq.call_args_list[0]
    assert 'INSERT INTO projects_stats_history' in insert.args[0]
    assert 'FROM projects_stats' in insert.args[0] and 'ON DUPLICATE KEY UPDATE' in insert.args[0]
    assert insert.args[1] == {'day': '2026-11-10'} and insert.kwargs == {'return_val': False}


def test_baselines_use_the_last_copy_before_the_year():
    row = {'project_id': 1, 'stat_date': date(2026, 12, 31), 'objects_digitized': 5, 'images_taken': 9}
    with patch.object(sh, 'run_query', return_value=[row]) as rq:
        assert sh.load_baselines(2027) == {1: {'objects': 5, 'images': 9, 'stat_date': date(2026, 12, 31)}}
    assert rq.call_count == 1
    assert 'MAX(stat_date)' in rq.call_args.args[0] and rq.call_args.args[1] == {'jan1': '2027-01-01'}


def test_baselines_in_the_first_year_use_the_first_copy():
    row = {'project_id': 1, 'stat_date': date(2026, 11, 10), 'objects_digitized': 5, 'images_taken': 9}
    with patch.object(sh, 'run_query', side_effect=[[], [row]]) as rq:
        assert sh.load_baselines(2026)[1]['stat_date'] == date(2026, 11, 10)
    assert 'MIN(stat_date)' in rq.call_args.args[0]


def test_year_change_sums_differences_and_counts_new_projects_in_full():
    current = [
        {'project_id': 1, 'objects': 150, 'images': 400},
        {'project_id': 2, 'objects': 30, 'images': 60},      # no baseline: new this year
    ]
    baselines = {1: {'objects': 100, 'images': 250, 'stat_date': date(2025, 12, 31)}}
    assert sh.year_change(current, baselines, 2026) == {'objects': 80, 'images': 210, 'year': 2026, 'since': None}


def test_year_change_in_the_first_year_says_since_when():
    current = [{'project_id': 1, 'objects': 150, 'images': 400}, {'project_id': 2, 'objects': 10, 'images': 10}]
    baselines = {
        1: {'objects': 100, 'images': 250, 'stat_date': date(2026, 11, 12)},
        2: {'objects': 10, 'images': 10, 'stat_date': date(2026, 11, 10)},
    }
    change = sh.year_change(current, baselines, 2026)
    assert change['since'] == date(2026, 11, 10) and change['objects'] == 50


def test_year_change_without_history_or_after_a_correction():
    assert sh.year_change([{'project_id': 1, 'objects': 5, 'images': 5}], {}, 2026) is None
    lowered = sh.year_change([{'project_id': 1, 'objects': 90, 'images': 5}],
                             {1: {'objects': 100, 'images': 5, 'stat_date': date(2025, 12, 31)}}, 2026)
    assert lowered['objects'] == 0 and lowered['images'] == 0


# ---- nightly recalculation --------------------------------------------------

def test_refresh_recalculates_ongoing_projects_and_survives_a_failure():
    projects = [{'project_id': 1, 'transcription': 0}, {'project_id': 2, 'transcription': 1},
                {'project_id': 3, 'transcription': 0}]

    def recalc(project_id, transcription):
        if project_id == 2:
            raise ValueError('Invalid project_object_query')

    with patch.object(sh, 'run_query', return_value=projects) as rq, \
            patch.object(sh.folder_stats, 'recalculate_project_stats', side_effect=recalc) as rp:
        assert sh.refresh_project_stats() == (2, [2])
    query = rq.call_args.args[0]
    assert "project_status = 'Ongoing'" in query and 'skip_project IS NOT True' in query
    assert [c.args for c in rp.call_args_list] == [(1, 0), (2, 1), (3, 0)]


def _script():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent / 'scripts' / 'snapshot_project_stats.py'
    spec = importlib.util.spec_from_file_location('snapshot_project_stats', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_recalculates_then_copies():
    script = _script()
    order = []
    with patch.object(sh, 'refresh_project_stats', side_effect=lambda: order.append('refresh') or (4, [])), \
            patch.object(sh, 'snapshot', side_effect=lambda: order.append('copy') or 9):
        assert script.main([]) == 0
    assert order == ['refresh', 'copy']


def test_script_still_copies_when_a_project_fails_but_reports_it():
    script = _script()
    with patch.object(sh, 'refresh_project_stats', return_value=(3, [7])), \
            patch.object(sh, 'snapshot', return_value=9) as snap:
        assert script.main([]) == 1
    snap.assert_called_once()


def test_script_copy_only_skips_the_recalculation():
    script = _script()
    with patch.object(sh, 'refresh_project_stats') as refresh, patch.object(sh, 'snapshot', return_value=9):
        assert script.main(['--copy-only']) == 0
    refresh.assert_not_called()


def test_script_fails_when_the_copy_fails():
    script = _script()
    with patch.object(sh, 'refresh_project_stats', return_value=(1, [])), \
            patch.object(sh, 'snapshot', side_effect=RuntimeError('no table')):
        assert script.main([]) == 1


# ---- backfill of the year's starting point ----------------------------------

def test_work_since_uses_the_project_object_expression_and_capture_date():
    with patch.object(sh, 'run_query', return_value=[{'images': 40, 'objects': 20}]) as rq:
        assert sh.work_since(7, 0, 'count(distinct f.file_name)', date(2026, 1, 1)) == (40, 20)
    query, params = rq.call_args.args
    assert 'count(distinct f.file_name) AS objects' in query
    assert 'FROM files f, folders fol' in query
    assert 'COALESCE(f.datetime_created, f.created_at) >= %(start)s' in query
    assert params == {'project_id': 7, 'start': '2026-01-01'}
    with patch.object(sh, 'run_query', return_value=[{'images': 1, 'objects': 1}]) as rq:
        sh.work_since(8, 1, 'count(f.file_name)', date(2026, 1, 1))
    assert 'transcription_files f' in rq.call_args.args[0] and 'f.created_at >= %(start)s' in rq.call_args.args[0]


def test_backfill_rows_subtract_this_years_files_from_current_totals():
    projects = [
        {'project_id': 1, 'project_title': 'Bees', 'transcription': 0, 'project_object_query': 'count(f.file_name)',
         'objects': 1000, 'images': 3000},
        {'project_id': 2, 'project_title': 'Paper only', 'transcription': 0,
         'project_object_query': 'count(f.file_name)', 'objects': 500, 'images': 500},
        {'project_id': 3, 'project_title': 'Bad', 'transcription': 0, 'project_object_query': 'sleep(5)',
         'objects': 50, 'images': 60},
        {'project_id': 4, 'project_title': 'Stale', 'transcription': 0, 'project_object_query': 'count(f.file_name)',
         'objects': 10, 'images': 10},
    ]
    since = {1: (900, 300), 2: (0, 0), 4: (25, 25)}
    with patch.object(sh, 'run_query', return_value=projects), \
            patch.object(sh, 'work_since', side_effect=lambda pid, t, e, s: since[pid]):
        rows = {r['project_id']: r for r in sh.backfill_rows(2026)}
    assert (rows[1]['objects'], rows[1]['images']) == (700, 2100)
    assert (rows[1]['objects_since'], rows[1]['images_since']) == (300, 900)
    assert (rows[2]['objects'], rows[2]['images']) == (500, 500)      # no files: adds nothing
    assert rows[3]['error'] and (rows[3]['objects'], rows[3]['images']) == (50, 60)
    assert (rows[4]['objects'], rows[4]['images']) == (0, 0)          # never negative


def test_write_backfill_dates_rows_31_december_and_keeps_existing_by_default():
    rows = [{'project_id': 1, 'objects': 700, 'images': 2100}]
    with patch.object(sh, 'run_query') as rq:
        assert sh.write_backfill(rows, 2026) == 1
    query, params = rq.call_args.args
    assert query.startswith('INSERT IGNORE INTO projects_stats_history')
    assert params == {'project_id': 1, 'day': '2025-12-31', 'objects': 700, 'images': 2100}
    with patch.object(sh, 'run_query') as rq:
        sh.write_backfill(rows, 2026, replace=True)
    assert 'ON DUPLICATE KEY UPDATE' in rq.call_args.args[0]


def test_backfilled_rows_turn_the_highlight_into_a_whole_year():
    # With a 2025-12-31 copy, baselines come from before 1 January: "in 2026", not "since".
    current = [{'project_id': 1, 'objects': 1000, 'images': 3000}]
    baselines = {1: {'objects': 700, 'images': 2100, 'stat_date': date(2025, 12, 31)}}
    assert sh.year_change(current, baselines, 2026) == {'objects': 300, 'images': 900, 'year': 2026, 'since': None}


def _backfill_script():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent / 'scripts' / 'backfill_stats_history.py'
    spec = importlib.util.spec_from_file_location('backfill_stats_history', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_backfill_script_is_a_dry_run_unless_asked_to_write(capsys):
    script = _backfill_script()
    rows = [{'project_id': 1, 'project_title': 'Bees', 'objects': 700, 'images': 2100,
             'objects_since': 300, 'images_since': 900, 'error': ''}]
    with patch.object(sh, 'backfill_rows', return_value=rows), patch.object(sh, 'write_backfill') as write:
        assert script.main(['--year', '2026']) == 0
        write.assert_not_called()
        assert script.main(['--year', '2026', '--write']) == 0
        write.assert_called_once_with(rows, 2026, replace=False)
    out = capsys.readouterr().out
    assert 'dry run: nothing written' in out and '300 objects, 900 images' in out
