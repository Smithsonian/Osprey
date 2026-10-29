"""Unit tests for the folder QC decision (weighted and cumulative methods)."""

from decimal import Decimal
from unittest.mock import patch

import pytest

from osprey.services import qc as qc_service
from osprey.services.qc import count_issues, folder_passes_qc, load_folder_qc_counts, qc_math, qc_method

# Defaults created by the /qc route for new projects
SETTINGS = {
    'qc_threshold_critical': 0,
    'w_major': 1,
    'w_minor': 0.3,
    'weighted_rate': 6,
}

CUMULATIVE = {
    'qc_method': 'cumulative',
    'qc_threshold_critical': 0,
    'qc_threshold_major': 1.5,
    'qc_threshold_minor': 4,
}


@pytest.mark.parametrize('critical, major, minor, expected', [
    (0, 0, 0, True),
    (1, 0, 0, False),      # any critical fails at threshold 0
    (0, 24, 0, True),      # weighted = 24*1 = 24 -> 6.0% of 400, at the limit
    (0, 25, 0, False),     # weighted = 25 -> 6.25%
    (0, 0, 80, True),      # weighted = 80*0.3 = 24.0 -> 6.0%
    (0, 0, 81, False),     # weighted = 24.3 -> 6.075%
    (0, 10, 46, True),     # weighted = 10 + 13.8 = 23.8 -> 5.95%
    (0, 10, 47, False),    # weighted = 10 + 14.1 = 24.1 -> 6.025%
])
def test_folder_passes_qc_sample_400(critical, major, minor, expected):
    assert folder_passes_qc(400, critical, major, minor, SETTINGS) is expected


def test_folder_passes_qc_accepts_decimal_strings():
    # MySQL DECIMAL columns may arrive as Decimal or str
    settings = {k: str(v) for k, v in SETTINGS.items()}
    assert folder_passes_qc(100, 0, 0, 20, settings) is True   # weighted = 6.0, at the limit
    assert folder_passes_qc(100, 0, 0, 21, settings) is False  # weighted = 6.3


def test_folder_passes_qc_empty_sample():
    with pytest.raises(ValueError):
        folder_passes_qc(0, 0, 0, 0, SETTINGS)


def test_count_issues_by_label():
    rows = [
        {'qc_results': 'Critical Issue'},
        {'qc_results': 'Major Issue'},
        {'qc_results': 'Major Issue'},
        {'qc_results': 'Minor Issue'},
        {'qc_results': None},
    ]
    assert count_issues(rows, 'qc_results') == {'critical': 1, 'major': 2, 'minor': 1}
    assert count_issues(None, 'file_qc') == {'critical': 0, 'major': 0, 'minor': 0}


@pytest.mark.parametrize('critical, major, minor, expected', [
    (0, 24, 0, True),
    (0, 25, 0, False),
])
def test_qc_math_passed_matches_folder_passes_qc(critical, major, minor, expected):
    result = qc_math(400, critical, major, minor, SETTINGS)
    assert result['passed'] is expected
    assert result['passed'] is folder_passes_qc(400, critical, major, minor, SETTINGS)


def test_qc_math_breakdown():
    result = qc_math(400, 0, 10, 46, SETTINGS)
    assert result['method'] == 'weighted'
    critical, weighted = result['checks']
    assert critical['pct'] == 0
    assert critical['passed'] is True
    assert result['weighted_issues'] == weighted['issues'] == 23.8   # 10*1 + 46*0.3
    assert weighted['pct'] == 5.95
    assert weighted['passed'] is True
    assert result['passed'] is True


def test_qc_method_default_and_unknown():
    assert qc_method(SETTINGS) == 'weighted'
    assert qc_method(dict(SETTINGS, qc_method=None)) == 'weighted'
    assert qc_method(CUMULATIVE) == 'cumulative'
    with pytest.raises(ValueError):
        qc_method({'qc_method': 'other'})


@pytest.mark.parametrize('critical, major, minor, expected', [
    (0, 0, 0, True),
    (1, 0, 0, False),      # any critical fails at threshold 0
    (0, 6, 0, True),       # critical + major = 1.5%, at the limit
    (0, 7, 0, False),      # 1.75%
    (0, 6, 10, True),      # all issues = 4.0%, at the limit
    (0, 6, 16, False),     # 5.5%
    (0, 0, 17, False),     # 4.25% minor alone
])
def test_folder_passes_qc_cumulative_sample_400(critical, major, minor, expected):
    assert folder_passes_qc(400, critical, major, minor, CUMULATIVE) is expected
    assert qc_math(400, critical, major, minor, CUMULATIVE)['passed'] is expected


def test_methods_disagree_on_same_sample():
    # 0 major + 17 minor of 400: cumulative fails (4.25% > 4), weighted passes (1.275% <= 6)
    both = dict(SETTINGS, **CUMULATIVE)
    assert folder_passes_qc(400, 0, 0, 17, both) is False
    assert folder_passes_qc(400, 0, 0, 17, dict(both, qc_method='weighted')) is True


def test_qc_math_cumulative_breakdown():
    result = qc_math(400, 0, 6, 16, CUMULATIVE)
    assert result['method'] == 'cumulative'
    assert 'weighted_issues' not in result
    assert [(c['label'], c['issues'], c['pct'], c['limit'], c['passed']) for c in result['checks']] == [
        ('Critical', 0, 0, 0.0, True),
        ('Critical + major', 6, 1.5, 1.5, True),
        ('Critical + major + minor', 22, 5.5, 4.0, False),
    ]
    assert result['passed'] is False


@pytest.mark.parametrize('transcription, column', [(False, 'folder_id'), (True, 'folder_uid')])
def test_load_folder_qc_counts(monkeypatch, transcription, column):
    calls = []

    def fake_run_query(query, params):
        calls.append((query, params))
        # MySQL returns COUNT as int and SUM as Decimal
        return [{'no_files': 40, 'unrated': Decimal('0'), 'critical': Decimal('0'),
                 'major': Decimal('1'), 'minor': Decimal('2')}]

    monkeypatch.setattr(qc_service, 'run_query', fake_run_query)
    counts = load_folder_qc_counts('abc', transcription)
    assert counts == {'no_files': 40, 'unrated': 0, 'critical': 0, 'major': 1, 'minor': 2}
    assert f'WHERE {column} = %(folder_id)s' in calls[0][0]
    assert calls[0][1] == {'folder_id': 'abc'}


# ---- QC lock resets (shared by /qc_reset and the sysadmin QC locks card) ----


@pytest.mark.parametrize('transcription,column', [(0, 'folder_id'), (1, 'folder_uid')])
def test_reset_folder_qc_keys_by_folder_kind(transcription, column):
    with patch.object(qc_service, 'query_database_insert') as ins:
        qc_service.reset_folder_qc('x', transcription)
    queries = [c[0][0] for c in ins.call_args_list]
    assert len(queries) == 3
    assert queries[0].startswith('UPDATE qc_folders SET qc_status = 9, qc_by = NULL')
    assert queries[1].startswith('DELETE FROM qc_files')
    assert "badge_type = 'qc_status'" in queries[2]
    assert all('WHERE {} = %(folder_id)s'.format(column) in q for q in queries)
    assert all(c[0][1] == {'folder_id': 'x'} for c in ins.call_args_list)


def test_reset_transcription_text_qc_scopes_to_source():
    with patch.object(qc_service, 'query_database_insert') as ins:
        qc_service.reset_transcription_text_qc('f-uuid', 's-uuid')
    queries = [c[0][0] for c in ins.call_args_list]
    assert 'UPDATE transcription_qc_folders' in queries[0]
    assert 'DELETE FROM transcription_qc ' in queries[1]
    assert "transcription_qc_status" in queries[2]
    assert all('transcription_source_id = %(source_id)s' in q or 'folder_transcription_id = %(source_id)s' in q
               for q in queries)
    assert all(c[0][1] == {'folder_id': 'f-uuid', 'source_id': 's-uuid'} for c in ins.call_args_list)
