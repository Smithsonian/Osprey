"""Unit tests for the cumulative folder QC decision."""

from decimal import Decimal

import pytest

from osprey.services import qc as qc_service
from osprey.services.qc import count_issues, folder_passes_qc, load_folder_qc_counts

# Defaults created by the /qc route for new projects
SETTINGS = {
    'qc_threshold_critical': 0,
    'w_major': 1,
    'w_minor': 0.3,
    'weighted_rate': 6,
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
