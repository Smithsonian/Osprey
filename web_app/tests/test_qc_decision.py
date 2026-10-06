"""Unit tests for the cumulative folder QC decision."""

from decimal import Decimal

import pytest

from osprey.services import qc as qc_service
from osprey.services.qc import count_issues, folder_passes_qc, load_folder_qc_counts

# Defaults created by the /qc route for new projects
SETTINGS = {
    'qc_threshold_critical': 0,
    'qc_threshold_major': 1.5,
    'qc_threshold_minor': 4,
}


@pytest.mark.parametrize('critical, major, minor, expected', [
    (0, 0, 0, True),
    (1, 0, 0, False),     # any critical fails at threshold 0
    (0, 6, 0, True),      # 1.5% major, at the limit
    (0, 7, 0, False),     # 1.75% major
    (0, 0, 16, True),     # 4.0% total
    (0, 0, 17, False),    # 4.25% total
    (0, 6, 10, True),     # 16 issues = 4.0% total
    (0, 6, 16, False),    # 22 issues = 5.5% total; passed before the cumulative rule
])
def test_folder_passes_qc_sample_400(critical, major, minor, expected):
    assert folder_passes_qc(400, critical, major, minor, SETTINGS) is expected


def test_folder_passes_qc_accepts_decimal_strings():
    # MySQL DECIMAL columns may arrive as Decimal or str
    settings = {k: str(v) for k, v in SETTINGS.items()}
    assert folder_passes_qc(100, 0, 1, 3, settings) is True
    assert folder_passes_qc(100, 0, 1, 4, settings) is False


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
