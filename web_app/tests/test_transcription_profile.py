"""Unit tests for the transcription profile analysis helpers (no DB)."""

from osprey.services.transcription_profile import fill_percentages
from osprey.services.transcription_profile_analysis import (
    FieldAccumulator,
    build_field_profile,
    has_repetition,
    normalize,
    rank_suspicious,
    value_shape,
)

# Mirrors the column defaults in db/transcription_profile.sql.
SETTINGS = {
    'fuzzy_threshold': 90, 'top_n_common': 20, 'canonical_pool': 500, 'rare_max_count': 1,
    'free_text_ratio': 0.8, 'min_score': 2.0, 'max_suspicious': 500,
    'w_rare': 1.0, 'w_novel': 1.0, 'w_shape': 1.0, 'w_length': 1.0, 'w_repeat': 2.0, 'w_boilerplate': 3.0,
}
NONSTRING_TERMS = {'n/a', 'illegible'}
BOILERPLATE = ['the image shows']


def _profile(values, settings=SETTINGS):
    acc = FieldAccumulator(NONSTRING_TERMS)
    for i, value in enumerate(values):
        acc.add(f'file{i}', 'folderA' if i % 2 else 'folderB', value)
    return acc, build_field_profile(acc, settings, BOILERPLATE, 'collector')


def test_normalize_casefold_spaces_and_outer_punctuation():
    assert normalize('  Smith,  J. ') == 'smith, j'
    assert normalize('[Illegible]') == 'illegible'
    assert normalize('--') == ''
    assert normalize(None) == ''


def test_value_shape_collapses_runs():
    assert value_shape('2024-05-01') == '9-9-9'
    assert value_shape('Smith J') == 'a a'
    assert value_shape('USNM 12345') == 'a 9'


def test_has_repetition():
    assert has_repetition('the the the end')
    assert not has_repetition('the end the end')


def test_accumulator_splits_filled_nonstring_empty():
    acc = FieldAccumulator(NONSTRING_TERMS)
    acc.add('f1', 'A', 'Smith')
    acc.add('f2', 'A', 'N/A')
    acc.add('f3', 'A', '!!!')    # illegible marks only -> nonstring
    acc.add('f4', 'A', '   ')    # whitespace -> empty (not counted)
    acc.add('f5', 'A', None)
    assert acc.filled_by_folder['A'] == 1
    assert acc.nonstring_by_folder['A'] == 2


def test_partly_illegible_value_stays_filled():
    acc = FieldAccumulator(NONSTRING_TERMS)
    for value in ('!', '[!!]', ' !!! '):
        acc.add('f', 'A', value)
    acc.add('f', 'A', 'Sm!!! County')
    assert acc.nonstring_by_folder['A'] == 3
    assert acc.filled_by_folder['A'] == 1


def test_fuzzy_grouping_merges_small_differences():
    values = ['Smithsonian'] * 30 + ['Smithsonain'] * 3 + ['smithsonian.'] * 2 + ['Field Museum'] * 20
    _, profile = _profile(values)
    top = profile['common'][0]
    assert top['value'] == 'Smithsonian'
    assert top['count'] == 35
    assert top['n_variants'] == 3
    assert profile['common'][1]['count'] == 20


def test_suspicious_flags_rare_novel_and_boilerplate():
    values = ['Smith'] * 60 + ['Jones'] * 40 + ['The image shows a label', 'Q9#xz']
    _, profile = _profile(values)
    flagged = {row['value']: row for row in profile['suspicious']}
    assert 'boilerplate' in flagged['The image shows a label']['reasons']
    assert {'rare', 'novel', 'shape'} <= set(flagged['Q9#xz']['reasons'])
    assert 'Smith' not in flagged


def test_free_text_field_skips_rarity():
    values = [f'Collected near river bend {i}' for i in range(100)]
    _, profile = _profile(values)
    assert profile['free_text'] is True
    assert all('rare' not in row['reasons'] for row in profile['suspicious'])


def test_rank_suspicious_orders_and_caps():
    profiles = [
        {'suspicious': [{'field_name': 'a', 'value': 'x', 'score': 2.0}]},
        {'suspicious': [{'field_name': 'b', 'value': 'y', 'score': 5.0},
                        {'field_name': 'b', 'value': 'z', 'score': 3.0}]},
    ]
    ranked = rank_suspicious(profiles, 2)
    assert [r['value'] for r in ranked] == ['y', 'z']


def test_fill_percentages():
    out = fill_percentages(10, 7, 1)
    assert out['empty'] == 2
    assert (out['filled_pct'], out['nonstring_pct'], out['empty_pct']) == (70.0, 10.0, 20.0)
    assert fill_percentages(0, 0, 0)['filled_pct'] == 0.0
