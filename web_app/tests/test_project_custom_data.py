"""project_custom_data: value parsing, add/restore and scoped removal."""

from unittest.mock import patch

import pytest

from osprey.services import project_custom_data as cd


def test_parse_text_splits_trims_dedupes():
    assert cd.parse_values(" f001 \n\nf002\nf001\r\nf003 ", 'text') == ['f001', 'f002', 'f003']


def test_parse_numbers_canonical():
    assert cd.parse_values("1,200\n3.50\n1200", 'number') == ['1200', '3.5']


@pytest.mark.parametrize('raw', ['abc', 'NaN', 'Infinity'])
def test_parse_rejects_bad_numbers(raw):
    with pytest.raises(cd.DataEntryError):
        cd.parse_values(raw, 'number')


def test_parse_dates():
    assert cd.parse_values("2026-10-13", 'date') == ['2026-10-13']
    with pytest.raises(cd.DataEntryError):
        cd.parse_values("10/13/2026", 'date')


def test_parse_limits():
    with pytest.raises(cd.DataEntryError):
        cd.parse_values("   \n  ", 'text')
    with pytest.raises(cd.DataEntryError):
        cd.parse_values('x' * 256, 'text')
    with pytest.raises(cd.DataEntryError):
        cd.parse_values('\n'.join(str(i) for i in range(cd.MAX_VALUES_PER_SUBMIT + 1)), 'text')


def test_get_type_rejects_bad_ids_without_query():
    with patch.object(cd, 'run_query') as rq:
        assert cd.get_type(12, "x' OR 1=1") is None
    rq.assert_not_called()


def test_get_type_is_scoped_to_project():
    with patch.object(cd, 'run_query', return_value=[]) as rq:
        assert cd.get_type(12, 'special_folders') is None
    sql, params = rq.call_args[0]
    assert 'project_id = %(pid)s AND type_id = %(tid)s' in sql
    assert params == {'pid': 12, 'tid': 'special_folders'}


def test_list_types_only_this_project():
    with patch.object(cd, 'run_query', return_value=[]) as rq:
        cd.list_types(12)
    sql, params = rq.call_args[0]
    assert 'WHERE t.project_id = %(pid)s' in sql and params == {'pid': 12}
    # values join on both keys, so a same-named type in another project never counts
    assert 'v.project_id = t.project_id AND v.type_id = t.type_id' in sql


def test_list_projects_only_with_types():
    with patch.object(cd, 'run_query', return_value=[]) as rq:
        cd.list_projects()
    assert 'JOIN project_custom_types t ON t.project_id = p.project_id' in rq.call_args[0][0]


def test_add_values_restores_removed_and_keeps_current():
    with patch.object(cd, 'query_database_insert') as ins:
        assert cd.add_values(12, 'special_folders', ['a', 'b'], '', 'alice') == 2
    sql, params = ins.call_args[0]
    assert 'ON DUPLICATE KEY UPDATE' in sql and 'removed_at = NULL' in sql
    assert 'IF(removed_at IS NULL, added_by' in sql  # a current value keeps its original author
    assert params == {'pid': 12, 'tid': 'special_folders', 'v': 'b', 'note': None, 'user': 'alice'}


def test_remove_is_scoped_to_project_and_type():
    calls = []

    def rq(query, params=None, return_val=True):
        calls.append((query, params))
        return [{'value': 'a'}] if query.startswith('SELECT') else True

    with patch.object(cd, 'run_query', side_effect=rq):
        assert cd.remove_value(12, 'special_folders', 5, 'alice') is True
    select, update = calls
    for _, params in calls:
        assert params['pid'] == 12 and params['tid'] == 'special_folders' and params['vid'] == 5
    assert 'project_id = %(pid)s AND type_id = %(tid)s' in update[0]


def test_remove_missing_value_does_nothing():
    with patch.object(cd, 'run_query', return_value=[]) as rq:
        assert cd.remove_value(12, 'special_folders', 5, 'alice') is False
    assert rq.call_count == 1  # no UPDATE


def test_list_values_splits_current_and_removed():
    import datetime
    t1, t2 = datetime.datetime(2026, 1, 1), datetime.datetime(2026, 2, 1)
    rows = [{'value': 'a', 'removed_at': None}, {'value': 'b', 'removed_at': t1},
            {'value': 'c', 'removed_at': t2}]
    with patch.object(cd, 'run_query', return_value=rows):
        out = cd.list_values(12, 't')
    assert [r['value'] for r in out['current']] == ['a']
    assert [r['value'] for r in out['removed']] == ['c', 'b']
