"""sysadmin_data lookups: key masking, grouping, and query shape.

The DB is stubbed; these tests pin the Python-side logic and the guarantees
that matter for safety (no password column, masked keys, bounded scans).
"""

import datetime
from unittest.mock import patch

from osprey.services import sysadmin_data as sd

T1 = datetime.datetime(2026, 10, 1, 12, 0)
T2 = datetime.datetime(2026, 10, 9, 12, 0)


def test_mask_key_keeps_last_four():
    assert sd._mask_key('0b1c2d3e-aaaa-bbbb-cccc-1234567890ab') == '…90ab'
    assert sd._mask_key(None) == ''


def test_users_never_selects_password():
    with patch.object(sd.db, 'run_query', return_value=[]) as rq:
        sd.users()
    query = rq.call_args[0][0]
    assert 'pass' not in query.replace('qp.', '').split('FROM')[0]


def test_schema_status_marks_tables_and_columns():
    def rq(query, params=None):
        if 'information_schema.TABLES' in query:
            return [{'name': 'kiosk'}, {'name': 'report_materializations'}]
        return [{'t': 'folders', 'c': 'preview_type'}]

    with patch.object(sd.db, 'run_query', side_effect=rq):
        rows = {r['target']: r['applied'] for r in sd.schema_status()}
    assert rows['kiosk'] is True
    assert rows['folders.preview_type'] is True
    assert rows['transcription_folders.preview_type'] is False
    assert rows['transcription_profile_settings'] is False


def test_api_keys_masks_and_merges_usage():
    key = '11111111-2222-3333-4444-555555556789'

    def rq(query, params=None):
        if 'FROM api_keys ORDER' in query:
            return [{'table_id': 1, 'api_key': key, 'api_user': 'worker', 'uid': None,
                     'is_active': 1, 'is_admin': 0, 'usage_rate': 100,
                     'expires_on': T1, 'expired': 1, 'updated_at': T1}]
        if 'GROUP BY api_key' in query:
            assert params == {'window': sd.API_USAGE_WINDOW}
            return [{'api_key': key, 'last_used': T2, 'calls_24h': 7, 'invalid': 0}]
        return [{'api_key': key, 'url': '/api/x', 'created_at': T2},
                {'api_key': 'nope', 'url': '/api/y', 'created_at': T1}]

    with patch.object(sd.db, 'run_query', side_effect=rq):
        out = sd.api_keys()
    k = out['keys'][0]
    assert 'api_key' not in k and k['key_masked'] == '…6789'
    assert k['last_used'] == T2 and k['calls_24h'] == 7
    assert [r['known_key'] for r in out['invalid']] == [True, False]
    assert all('api_key' not in r for r in out['invalid'])


def test_kiosks_groups_by_machine_and_flags_config(monkeypatch):
    monkeypatch.setattr(sd.settings, 'kiosks', ['10.0.0.1', '10.0.0.9'])

    def rq(query, params=None):
        if 'information_schema' in query:
            return [{'name': 'kiosk'}]
        return [
            {'machine_name': 'k1', 'ip': '10.0.0.1', 'last_seen': T2, 'checkins': 5},
            {'machine_name': 'k1', 'ip': '10.0.0.2', 'last_seen': T1, 'checkins': 2},
            {'machine_name': 'k2', 'ip': '10.0.0.3', 'last_seen': T2, 'checkins': 1},
        ]

    with patch.object(sd.db, 'run_query', side_effect=rq):
        out = sd.kiosks()
    k1, k2 = out['machines']
    assert (k1['ip'], k1['checkins'], k1['other_ips'], k1['configured']) == ('10.0.0.1', 7, ['10.0.0.2'], True)
    assert k2['configured'] is False
    assert out['configured_not_seen'] == ['10.0.0.9']


def test_kiosks_without_table(monkeypatch):
    monkeypatch.setattr(sd.settings, 'kiosks', [])
    with patch.object(sd.db, 'run_query', return_value=[]):
        assert sd.kiosks() == {'table_present': False, 'configured': []}


def test_folder_errors_merges_and_sorts_both_tables():
    def rq(query, params=None):
        assert "f.status = 1" in query
        assert "project_status != 'Completed'" in query
        assert params is None
        if 'FROM folders f' in query:
            return [{'folder_id': 1, 'project_id': 1, 'project_alias': 'p1',
                     'project_title': 'P1', 'folder_name': 'f1', 'folder_path': '/f1',
                     'status': 1, 'error_info': 'bad md5', 'file_errors': 2,
                     'no_files_errors': 2, 'updated_at': T1, 'source': 'folder'}]
        return [{'folder_id': 'u-2', 'project_id': 2, 'project_alias': 'p2',
                 'project_title': 'P2', 'folder_name': 'f2', 'folder_path': '/f2',
                 'status': 1, 'error_info': 'missing file', 'file_errors': 1,
                 'no_files_errors': 1, 'updated_at': T2, 'source': 'transcription_folder'}]

    with patch.object(sd.db, 'run_query', side_effect=rq):
        rows = sd.folder_errors()
    assert [r['folder_id'] for r in rows] == ['u-2', 1]
    assert [r['source'] for r in rows] == ['transcription_folder', 'folder']


def test_folder_errors_filters_by_project():
    def rq(query, params=None):
        assert "f.project_id = %(project_id)s" in query
        assert params == {'project_id': 2}
        return []

    with patch.object(sd.db, 'run_query', side_effect=rq) as run_query:
        sd.folder_errors(project_id=2)
    assert run_query.call_count == 2


def test_folder_error_projects_unions_both_tables():
    with patch.object(sd.db, 'run_query', return_value=[
            {'project_id': 2, 'project_alias': 'p2', 'project_title': 'P2'}]) as run_query:
        rows = sd.folder_error_projects()
    query = run_query.call_args[0][0]
    assert 'UNION' in query and "project_status != 'Completed'" in query
    assert rows == [{'project_id': 2, 'project_alias': 'p2', 'project_title': 'P2'}]


def test_projects_overview_groups_users_and_settings():
    def rq(query, params=None):
        if 'FROM projects ORDER' in query:
            return [{'project_id': 1, 'project_alias': 'a', 'project_title': 'A',
                     'project_status': 'Ongoing', 'project_unit': 'U', 'qc_status': 1}]
        if 'FROM qc_projects' in query:
            return [{'project_id': 1, 'project_alias': 'a', 'project_title': 'A', 'project_status': 'Ongoing',
                     'user_id': 5, 'username': 'alice', 'full_name': 'Alice', 'user_active': 1},
                    {'project_id': 99, 'project_alias': 'z', 'project_title': 'Z', 'project_status': None,
                     'user_id': 5, 'username': 'alice', 'full_name': 'Alice', 'user_active': 1}]
        return [{'project_id': 1, 'project_setting': 'project_checks', 'settings_value': 'md5'},
                {'project_id': 1, 'project_setting': 'project_checks', 'settings_value': 'tifpages'}]

    with patch.object(sd.db, 'run_query', side_effect=rq):
        (p,) = sd.projects_overview()
    assert [u['username'] for u in p['users']] == ['alice']
    assert p['settings'] == {'project_checks': ['md5', 'tifpages']}


def test_reports_without_materializations_skips_join():
    def rq(query, params=None):
        if 'information_schema' in query:
            return []
        assert 'report_materializations' not in query
        return []

    with patch.object(sd.db, 'run_query', side_effect=rq):
        assert sd.reports() == {'materializations': False, 'rows': []}



def test_stats_without_table():
    with patch.object(sd.db, 'run_query', return_value=[]):
        assert sd.stats() == {'table_present': False}


def test_stats_groups_by_job_and_attaches_last_run():
    def rq(query, params=None):
        if 'information_schema' in query:
            return [{'name': 'sysadmin_stats'}, {'name': 'report_materializations'}]
        if 'FROM report_materializations' in query:
            assert params == {'pid': 0, 'prefix': 'stat:%'}
            return [{'report_id': 'stat:files_exif', 'status': 'failed', 'last_succeeded_at': T1,
                     'last_failed_at': T2, 'duration_ms': 900, 'error_message': 'boom'}]
        assert 'files_exif' not in query.split('FROM')[1]  # never scans the big table
        base = {'project_alias': 'a', 'project_title': 'A', 'project_status': None}
        return [dict(base, stat_id='files_exif_rows', project_id=10, value=100, computed_at=T1),
                dict(base, stat_id='files_exif_files', project_id=10, value=4, computed_at=T1),
                dict(base, stat_id='files_exif_rows', project_id=0, value=500, computed_at=T2),
                dict(base, stat_id='old_removed_stat', project_id=10, value=1, computed_at=T1)]

    with patch.object(sd.db, 'run_query', side_effect=rq):
        out = sd.stats()
    (job,) = out['jobs']
    assert job['job_id'] == 'files_exif'
    assert [p['project_id'] for p in job['projects']] == [0, 10]  # sorted by first stat
    assert job['projects'][1]['values'] == {'files_exif_rows': 100, 'files_exif_files': 4}
    assert job['totals'] == {'files_exif_rows': 600, 'files_exif_files': 4}
    assert job['computed_at'] == T2
    assert job['run']['status'] == 'failed'
