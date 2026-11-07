"""The evaluation helpers are code too: a bug here silently produces a wrong benchmark.

(The first run of the harness reported recall@1 = 0.000 on the hand set because the expected
names were mixed-case and only the retrieved names were lower-cased. These tests pin that.)
"""
import pathlib
import random
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'scripts'))

import evalsets

EN = chr(0x2013)  # EN DASH, built with chr so the source carries no ambiguous character


@pytest.mark.parametrize('expected, names, substring, rank', [
    ('Post-Matric Scholarship for SC students', ['Other', 'Post-Matric Scholarship for SC students'], False, 2),
    ('post-matric scholarship for sc students', ['POST-MATRIC SCHOLARSHIP FOR SC STUDENTS'], False, 1),  # case
    ('Swanath', ['AICTE-Swanath Scholarship Scheme For Students'], True, 1),                               # substring
    ('Swanath', ['AICTE-Swanath Scholarship Scheme For Students'], False, None),                           # exact only
    ('AICTE - Saksham', ['AICTE-Saksham Scheme'], True, None),                                             # spaces around the dash differ
    ('AICTE-Saksham', [f'AICTE{EN}Saksham Scheme'], True, 1),                                             # en dash == hyphen
    ('AICTE - Saksham', [f'AICTE {EN} Saksham Scheme'], True, 1),                                         # en dash == hyphen, spaced
    ('Missing', ['A', 'B'], True, None),
    ('x', [], False, None),
])
def test_rank_of(expected, names, substring, rank):
    assert evalsets.rank_of(expected, names, substring) == rank


def test_metrics_on_a_known_list():
    m = evalsets.metrics([1, 2, None, 5, 6])
    assert m['n'] == 5
    assert m['recall@1'] == pytest.approx(1 / 5)
    assert m['recall@5'] == pytest.approx(3 / 5)           # ranks 1, 2 and 5; 6 and None miss
    assert m['mrr'] == pytest.approx((1 + 1 / 2 + 0 + 1 / 5 + 1 / 6) / 5)


def test_confidence_interval_brackets_the_estimate_and_is_reproducible():
    ranks = [1] * 70 + [3] * 20 + [None] * 10
    a, b = evalsets.summarise(ranks), evalsets.summarise(ranks)
    assert a == b, 'the bootstrap is seeded: the same input must give the same report'
    lo, hi = a['recall@1_ci']
    assert lo <= a['recall@1'] <= hi
    assert 0 < hi - lo < 0.25


def test_interval_is_wider_for_fewer_queries():
    big = evalsets.summarise([1] * 700 + [None] * 300)
    small = evalsets.summarise([1] * 7 + [None] * 3)
    width = lambda s: s['recall@1_ci'][1] - s['recall@1_ci'][0]  # noqa: E731
    assert width(small) > 3 * width(big)


def test_hand_set_is_well_formed():
    assert len(evalsets.PAIRS) == 30
    assert all(q.strip() and e.strip() for q, e in evalsets.PAIRS)
    assert len({q for q, _ in evalsets.PAIRS}) == 30, 'duplicate hand-written query'


def test_off_topic_set_is_clean():
    assert len(evalsets.OOD) == len(set(evalsets.OOD)) >= 30
    # An off-topic query that names a scheme would make the "should refuse" label wrong.
    banned = ('scholarship', 'scheme', 'yojana', 'aicte', 'matric')
    assert not [q for q in evalsets.OOD if any(b in q.lower() for b in banned)]


def test_noise_is_deterministic_and_actually_changes_the_text():
    name = 'Post-Matric Scholarship for SC students'
    a = evalsets.asr_noise(name, random.Random(4))
    assert a == evalsets.asr_noise(name, random.Random(4))
    assert a != name.lower()


def test_noisy_queries_are_seeded_and_labelled_with_the_clean_name():
    recs = [{'name': f'Scheme Number {i} For Students'} for i in range(50)]
    a, b = evalsets.noisy_queries(recs, seed=1, n=20), evalsets.noisy_queries(recs, seed=1, n=20)
    assert a == b and len(a) == 20
    assert all(expected.startswith('scheme number') for _, expected in a)
    assert a != evalsets.noisy_queries(recs, seed=2, n=20)


def test_named_queries_cover_every_record_once():
    recs = [{'name': 'A Scheme'}, {'name': 'B Scheme'}]
    assert evalsets.named_queries(recs) == [('A Scheme kya hai', 'a scheme'), ('B Scheme kya hai', 'b scheme')]
