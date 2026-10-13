"""scripts/count_exif.py: merges unlinked rows into project 0 and prunes stale rows."""

import datetime
import importlib.util
from pathlib import Path
from unittest.mock import patch

_spec = importlib.util.spec_from_file_location(
    'count_exif', Path(__file__).resolve().parent.parent / 'scripts' / 'count_exif.py')
count_exif = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(count_exif)

RUN_AT = datetime.datetime(2026, 10, 13, 2, 30)


def _run(by_project, unlinked):
    calls = []

    def rq(query, params=None, return_val=True, log_vals=True):
        calls.append((query, params))
        if 'NOW()' in query and 'SELECT' in query and 'exif_counts' not in query:
            return [{'now': RUN_AT}]
        if query == count_exif.COUNT_BY_PROJECT:
            return by_project
        if query == count_exif.COUNT_UNLINKED:
            return [{'n': unlinked}]
        return True

    with patch.object(count_exif, 'run_query', side_effect=rq), \
            patch.object(count_exif, 'executemany') as em:
        n = count_exif.count_exif()
    return n, calls, em


def test_unlinked_rows_added_to_project_zero():
    n, calls, em = _run([{'project_id': 10, 'exif_rows': 100, 'files_with_exif': 4},
                         {'project_id': 0, 'exif_rows': 3, 'files_with_exif': 1}], unlinked=7)
    rows = {r[0]: r[1:3] for r in em.call_args[0][1]}
    assert rows == {10: (100, 4), 0: (10, 1)}
    assert n == 2
    assert all(r[3] == RUN_AT for r in em.call_args[0][1])


def test_unlinked_only_creates_project_zero_row():
    _, _, em = _run([], unlinked=5)
    assert [r[:3] for r in em.call_args[0][1]] == [(0, 5, 0)]


def test_stale_rows_deleted_with_run_timestamp():
    _, calls, _ = _run([{'project_id': 10, 'exif_rows': 1, 'files_with_exif': 1}], unlinked=0)
    delete = [c for c in calls if c[0].startswith('DELETE FROM exif_counts')]
    assert delete == [('DELETE FROM exif_counts WHERE computed_at < %(run_at)s', {'run_at': RUN_AT})]


def test_empty_files_exif_writes_nothing_but_prunes():
    _, calls, em = _run([], unlinked=0)
    em.assert_not_called()
    assert any(c[0].startswith('DELETE FROM exif_counts') for c in calls)


def test_main_returns_1_on_failure():
    with patch.object(count_exif, 'count_exif', side_effect=RuntimeError('db down')):
        assert count_exif.main() == 1
