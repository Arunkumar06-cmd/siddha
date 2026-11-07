"""Retriever internals that do not need the embedding model: scores exposed, padding and ties handled."""
import numpy as np
import pytest

import retriever

RECS = [
    {'id': 'a', 'name': 'Alpha Scheme', 'category': 'x', 'level': 'Central'},
    {'id': 'b', 'name': 'Beta Scheme', 'category': 'x', 'level': 'Central'},
    {'id': 'z', 'name': 'Zed Scheme', 'category': 'x', 'level': 'Central'},   # the LAST record
]
DOCS = [r['name'] for r in RECS]


class FakeModel:
    def encode(self, texts, normalize_embeddings=True):
        return np.array([[1.0, 0.0]] * len(texts))


class FakeIndex:
    """FAISS returns id -1 (and a huge negative score) once it runs out of vectors."""

    def __init__(self, scores, ids):
        self._s, self._i = np.array([scores], dtype='float32'), np.array([ids])

    def search(self, q, k):
        return self._s, self._i


class FakeBM25:
    def __init__(self, scores):
        self._scores = np.array(scores, dtype=float)

    def get_scores(self, tokens):
        return self._scores


def install(monkeypatch, *, dense_scores, dense_ids, bm25_scores):
    monkeypatch.setattr(retriever, '_load', lambda: (
        RECS, DOCS, FakeModel(), FakeIndex(dense_scores, dense_ids), FakeBM25(bm25_scores)))


def test_dense_score_is_the_cosine_from_the_index(monkeypatch):
    install(monkeypatch, dense_scores=[0.91, 0.42], dense_ids=[0, 1], bm25_scores=[0, 0, 0])
    hits = retriever.search('anything', k=5)
    by_name = {h['record']['name']: h['dense_score'] for h in hits}
    assert by_name == {'Alpha Scheme': 0.91, 'Beta Scheme': 0.42}


def test_a_bm25_only_hit_has_no_dense_score(monkeypatch):
    install(monkeypatch, dense_scores=[0.9], dense_ids=[0], bm25_scores=[0, 0, 5.0])
    hits = {h['record']['name']: h['dense_score'] for h in retriever.search('zed', k=5)}
    assert hits['Zed Scheme'] is None
    assert hits['Alpha Scheme'] == 0.9


def test_faiss_padding_does_not_resolve_to_the_last_record(monkeypatch):
    """Id -1 is 'no result'. Indexing recs[-1] made the LAST record win RRF credit it never earned."""
    install(monkeypatch, dense_scores=[0.9, -3.4e38], dense_ids=[0, -1], bm25_scores=[0, 0, 0])
    names = [h['record']['name'] for h in retriever.search('anything', k=5)]
    assert names == ['Alpha Scheme']
    assert 'Zed Scheme' not in names


def test_zero_bm25_scores_do_not_hand_credit_to_the_first_records(monkeypatch):
    """A query with no token in the corpus (pure Devanagari/Tamil) scores 0 everywhere; argsort over
    those ties returned records 0..19 by position and fed them into the rank fusion."""
    install(monkeypatch, dense_scores=[0.8], dense_ids=[2], bm25_scores=[0, 0, 0])
    names = [h['record']['name'] for h in retriever.search('स्कॉलरशिप', k=5)]
    assert names == ['Zed Scheme'], 'only the dense hit may appear; BM25 had nothing to say'


@pytest.mark.parametrize('bm25', [[0, 0, 0], [3.0, 0, 0]])
def test_search_never_raises_on_empty_or_sparse_signals(monkeypatch, bm25):
    install(monkeypatch, dense_scores=[0.7], dense_ids=[1], bm25_scores=bm25)
    assert retriever.search('anything', k=3)


def test_data_paths_do_not_depend_on_the_working_directory(tmp_path, monkeypatch):
    """A relative 'data/...' path crashed the first query when the server started elsewhere."""
    monkeypatch.chdir(tmp_path)
    assert retriever.CORPUS.is_absolute() and retriever.CORPUS.exists()
    assert retriever.INDEX.is_absolute() and retriever.INDEX.exists()


# -- exact-name lookup must beat the generic Central prior -------------------------------

def _install_named(monkeypatch, recs, dense_ids):
    monkeypatch.setattr(retriever, '_load', lambda: (
        recs, [r['name'] for r in recs], FakeModel(),
        FakeIndex([0.9 - 0.01 * k for k in range(len(dense_ids))], dense_ids),
        FakeBM25([0.0] * len(recs))))


def _rec(name, level):
    return {'id': name, 'name': name, 'category': 'x', 'level': level}


def test_a_state_scheme_asked_for_by_its_exact_name_beats_a_central_scheme(monkeypatch):
    """No state is named, so every Central record gets x1.2 and the State scheme the user
    named word for word used to lose to whatever Central scheme ranked just above it."""
    recs = [_rec('Alpha Education Scheme', 'Central'), _rec('Beta Skill Training Subsidy', 'State')]
    _install_named(monkeypatch, recs, dense_ids=[0, 1])      # the Central scheme is dense-rank 1
    top = retriever.search('Beta Skill Training Subsidy kya hai', k=2)[0]['record']['name']
    assert top == 'Beta Skill Training Subsidy'


def test_without_a_name_in_the_query_the_central_prior_still_applies(monkeypatch):
    recs = [_rec('Alpha Education Scheme', 'Central'), _rec('Beta Skill Training Subsidy', 'State')]
    _install_named(monkeypatch, recs, dense_ids=[1, 0])      # the State scheme is dense-rank 1
    top = retriever.search('koi scholarship batao', k=2)[0]['record']['name']
    assert top == 'Alpha Education Scheme'


def test_a_generic_name_shared_by_several_states_is_not_boosted(monkeypatch):
    """"Post Matric Scholarship" exists once per state. Boosting them all would answer a state-less
    question with an arbitrary state's scheme, the very problem the Central prior fixes."""
    recs = [_rec('Alpha Education Scheme', 'Central'),
            _rec('Post Matric Scholarship', 'State'), _rec('Post Matric Scholarship', 'State')]
    _install_named(monkeypatch, recs, dense_ids=[0, 1, 2])
    top = retriever.search('post matric scholarship kya hai', k=3)[0]['record']['name']
    assert top == 'Alpha Education Scheme'


def test_the_most_specific_contained_name_wins(monkeypatch):
    recs = [_rec('Pre Matric Scholarship', 'Central'),
            _rec('Pre Matric Scholarship for Backward Class Students', 'State')]
    _install_named(monkeypatch, recs, dense_ids=[0, 1])
    top = retriever.search('Pre-Matric Scholarship for Backward Class Students', k=2)[0]['record']['name']
    assert top == 'Pre Matric Scholarship for Backward Class Students'


def test_dash_and_punctuation_variants_still_match(monkeypatch):
    recs = [_rec('Alpha Education Scheme', 'Central'), _rec('Merit·cum·Means Scholarship', 'State')]
    _install_named(monkeypatch, recs, dense_ids=[0, 1])
    top = retriever.search('merit-cum-means scholarship', k=2)[0]['record']['name']
    assert top == 'Merit·cum·Means Scholarship'


def test_one_word_names_are_too_generic_to_count_as_evidence(monkeypatch):
    recs = [_rec('Alpha Education Scheme', 'Central'), _rec('Biponi', 'State')]
    _install_named(monkeypatch, recs, dense_ids=[0, 1])
    top = retriever.search('biponi', k=2)[0]['record']['name']
    assert top == 'Alpha Education Scheme'
