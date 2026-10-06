"""Pure helpers for the transcription profile: normalization, grouping, scoring.

No DB access here so it can be unit-tested directly. The DB side (streaming
rows in, storing results) is in transcription_profile.py. Algorithm notes are
in README.md, "Transcription profile".
"""

from __future__ import annotations

import re
import statistics
import unicodedata
from collections import Counter

import numpy as np
from rapidfuzz import fuzz, process

# Shape signal: a value's shape is rare if under this share of the field's values.
SHAPE_RARE_SHARE = 0.01
# Length signal: modified z-score cutoff (Iglewicz & Hoaglin).
LENGTH_Z_CUTOFF = 3.5
# Shape/length signals need this many filled values to mean anything.
MIN_SAMPLE = 50
# Same token repeated this many times in a row (typical model looping).
REPEAT_RUN = 3
# Rows per rapidfuzz.cdist call when matching the long tail to group heads.
CDIST_CHUNK = 5000
# Variants kept per common group in the stored payload.
MAX_VARIANTS = 10

_OUTER_PUNCT = re.compile(r'^[\W_]+|[\W_]+$')
_WHITESPACE = re.compile(r'\s+')


def normalize(text):
    """Return the comparison key: NFKC, casefold, collapsed spaces, no outer punctuation."""
    if text is None:
        return ''
    key = unicodedata.normalize('NFKC', str(text)).casefold()
    key = _WHITESPACE.sub(' ', key).strip()
    return _OUTER_PUNCT.sub('', key)


def value_shape(text):
    """Collapse a value to its character-class shape, e.g. '2024-05-01' -> '9-9-9'.

    Letters -> 'a' (case ignored), digits -> '9', whitespace -> ' ', other
    characters kept; runs of the same class collapse to one character.
    """
    out = []
    for ch in str(text).strip():
        if ch.isdigit():
            cls = '9'
        elif ch.isalpha():
            cls = 'a'
        elif ch.isspace():
            cls = ' '
        else:
            cls = ch
        if not out or out[-1] != cls or cls not in ('9', 'a', ' '):
            out.append(cls)
    return ''.join(out)


def has_repetition(key, run=REPEAT_RUN):
    """True when one token appears ``run`` or more times in a row."""
    tokens = key.split()
    streak = 1
    for prev, cur in zip(tokens, tokens[1:]):
        streak = streak + 1 if cur == prev else 1
        if streak >= run:
            return True
    return False


class FieldAccumulator:
    """Collect one field's values while rows stream in.

    Keeps counts per distinct normalized value (plus one example file and the
    first raw spelling), not the rows themselves, so memory scales with the
    number of distinct values.
    """

    def __init__(self, nonstring_terms):
        self.nonstring_terms = nonstring_terms  # set of normalized nonstring terms
        self.filled_by_folder = Counter()
        self.nonstring_by_folder = Counter()
        self.key_counts = Counter()
        self.key_display = {}
        self.key_example_file = {}
        self.raw_counts = Counter()  # (key, raw) -> count, for variant lists

    def add(self, file_id, folder_id, raw_text):
        stripped = (raw_text or '').strip()
        if not stripped:
            return  # empty: counted as total - filled - nonstring
        key = normalize(stripped)
        if not key or key in self.nonstring_terms:
            # Marks-only values count too: illegible marks ('!!!'), '--', '?'.
            self.nonstring_by_folder[folder_id] += 1
            return
        self.filled_by_folder[folder_id] += 1
        self.key_counts[key] += 1
        self.raw_counts[(key, stripped)] += 1
        if key not in self.key_display:
            self.key_display[key] = stripped
            self.key_example_file[key] = file_id

    @property
    def filled_total(self):
        return sum(self.filled_by_folder.values())


def _cluster_pool(pool, threshold):
    """Greedy grouping of the head values (most frequent first).

    Returns ({key: head_key}, {key: best similarity to any other pool value}).
    ``pool`` must be sorted by count, descending.
    """
    head_of = {}
    if not pool:
        return head_of, {}
    scores = process.cdist(pool, pool, scorer=fuzz.ratio, workers=-1)
    np.fill_diagonal(scores, 0)  # ignore self-similarity
    best_score = {key: float(scores[i].max()) for i, key in enumerate(pool)}
    for i, key in enumerate(pool):
        if key in head_of:
            continue
        head_of[key] = key
        for j in range(i + 1, len(pool)):
            if pool[j] not in head_of and scores[i][j] >= threshold:
                head_of[pool[j]] = key
    return head_of, best_score


def _match_tail(tail, heads, threshold):
    """Match tail values to the nearest head.

    Returns {key: (head_key or None, best_score)}; head is None below threshold.
    """
    matches = {}
    if not tail or not heads:
        return {key: (None, 0.0) for key in tail}
    for start in range(0, len(tail), CDIST_CHUNK):
        chunk = tail[start:start + CDIST_CHUNK]
        scores = process.cdist(chunk, heads, scorer=fuzz.ratio, workers=-1)
        best_idx = scores.argmax(axis=1)
        for row, key in enumerate(chunk):
            score = float(scores[row][best_idx[row]])
            head = heads[best_idx[row]] if score >= threshold else None
            matches[key] = (head, score)
    return matches


def _length_flags(key_counts):
    """Return the set of keys whose length is an outlier (modified z-score)."""
    lengths = Counter()
    for key, count in key_counts.items():
        lengths[len(key)] += count
    expanded = sorted(lengths.elements())
    if len(expanded) < MIN_SAMPLE:
        return set()
    median = statistics.median(expanded)
    mad = statistics.median(abs(x - median) for x in expanded)
    if mad == 0:
        return set()  # all values the same length; shape covers this case
    return {
        key for key in key_counts
        if 0.6745 * abs(len(key) - median) / mad > LENGTH_Z_CUTOFF
    }


def build_field_profile(acc, settings, boilerplate, field_name):
    """Group one field's values and score suspicious ones.

    ``settings`` is a transcription_profile_settings row (dict);
    ``boilerplate`` is a list of normalized terms. Returns a JSON-ready dict
    with 'common', 'suspicious' and summary counts.
    """
    threshold = int(settings['fuzzy_threshold'])
    filled = acc.filled_total
    distinct = len(acc.key_counts)
    free_text = filled > 0 and distinct / filled > float(settings['free_text_ratio'])

    ordered = [key for key, _ in acc.key_counts.most_common()]
    if free_text:
        # Mostly unique values: grouping and rarity would only add noise.
        head_of = {key: key for key in ordered}
        best_score = {}
    else:
        pool = ordered[:int(settings['canonical_pool'])]
        head_of, best_score = _cluster_pool(pool, threshold)
        heads = sorted(set(head_of.values()), key=lambda k: -acc.key_counts[k])
        for key, (head, score) in _match_tail(ordered[len(pool):], heads, threshold).items():
            head_of[key] = head or key  # unmatched values form their own group
            best_score[key] = score

    groups = {}
    for key in ordered:
        groups.setdefault(head_of[key], []).append(key)
    group_total = {head: sum(acc.key_counts[k] for k in keys) for head, keys in groups.items()}

    top_heads = sorted(groups, key=lambda h: -group_total[h])[:int(settings['top_n_common'])]
    # One pass over raw spellings, kept only for the listed groups.
    variants_of = {head: Counter() for head in top_heads}
    for (key, raw), count in acc.raw_counts.items():
        head = head_of[key]
        if head in variants_of:
            variants_of[head][raw] += count

    common = []
    for head in top_heads:
        variants = variants_of[head]
        common.append({
            'value': acc.key_display[head],
            'count': group_total[head],
            'pct': round(100.0 * group_total[head] / filled, 1) if filled else 0.0,
            'n_variants': len(variants),
            'variants': [{'value': v, 'count': c} for v, c in variants.most_common(MAX_VARIANTS)],
        })

    suspicious = _score_values(acc, settings, boilerplate, field_name, free_text,
                               head_of, group_total, best_score)
    return {
        'field_name': field_name,
        'filled': filled,
        'distinct': distinct,
        'free_text': free_text,
        'common': common,
        'suspicious': suspicious,
    }


def _score_values(acc, settings, boilerplate, field_name, free_text, head_of, group_total, best_score):
    """Score every distinct value; return the ones at or above min_score."""
    filled = acc.filled_total
    rare_max = int(settings['rare_max_count'])
    min_score = float(settings['min_score'])
    weights = {name: float(settings['w_' + name])
               for name in ('rare', 'novel', 'shape', 'length', 'repeat', 'boilerplate')}

    shapes = {key: value_shape(acc.key_display[key]) for key in acc.key_counts}
    shape_counts = Counter()
    for key, count in acc.key_counts.items():
        shape_counts[shapes[key]] += count
    long_or_short = _length_flags(acc.key_counts)
    enough = filled >= MIN_SAMPLE

    rows = []
    for key, count in acc.key_counts.items():
        score = 0.0
        reasons = []
        if not free_text and group_total[head_of[key]] <= rare_max:
            score += weights['rare']
            reasons.append('rare')
            # Graded: the less it resembles any common value, the higher.
            novelty = 1.0 - best_score.get(key, 0.0) / 100.0
            if novelty > 0:
                score += weights['novel'] * novelty
                reasons.append('novel')
        if enough and shape_counts[shapes[key]] / filled < SHAPE_RARE_SHARE:
            score += weights['shape']
            reasons.append('shape')
        if key in long_or_short:
            score += weights['length']
            reasons.append('length')
        if has_repetition(key):
            score += weights['repeat']
            reasons.append('repeat')
        if any(term in key for term in boilerplate):
            score += weights['boilerplate']
            reasons.append('boilerplate')
        if score >= min_score:
            rows.append({
                'field_name': field_name,
                'value': acc.key_display[key],
                'count': count,
                'score': round(score, 2),
                'reasons': reasons,
                'file_id': acc.key_example_file[key],
            })
    return rows


def rank_suspicious(field_profiles, max_rows):
    """Merge suspicious rows from all fields, highest score first, capped."""
    rows = [row for profile in field_profiles for row in profile['suspicious']]
    rows.sort(key=lambda r: (-r['score'], r['field_name'], r['value']))
    return rows[:max_rows]
