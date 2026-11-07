"""Retrieval confidence gate: answer, hedge, or admit the records do not cover the question."""
import pytest

import confidence
import conversation
import pipeline

REC = {
    'id': 'rec-1', 'name': 'Post-Matric Scholarship for SC students', 'level': 'Central',
    'eligibility': 'Students belonging to Scheduled Castes studying after class 10.',
    'benefits': 'Maintenance allowance and reimbursement of fees.',
    'documents': 'Aadhaar Card, Caste Certificate, Income Certificate',
    'application': 'Apply on the National Scholarship Portal.',
}
OTHER = dict(REC, id='rec-2', name='Some Other Scheme')


def hit(dense, rec=REC, rank=0.03):
    return {'rank_score': rank, 'dense_score': dense, 'record': rec}


# -- the tier function ---------------------------------------------------------------

@pytest.mark.parametrize('best, expected', [
    (0.30, confidence.LOW),
    (0.4999, confidence.LOW),
    (0.50, confidence.SOFT),      # the floor is inclusive: exactly MIN_DENSE is answerable
    (0.5799, confidence.SOFT),
    (0.58, confidence.OK),
    (0.80, confidence.OK),
])
def test_tier_boundaries(best, expected):
    assert confidence.tier([hit(best)]) == expected


def test_no_hits_is_low():
    assert confidence.tier([]) == confidence.LOW


def test_keyword_only_hits_have_no_semantic_support():
    # dense_score None = reached the list through BM25 alone, for every hit.
    assert confidence.tier([hit(None), hit(None, OTHER)]) == confidence.LOW


def test_best_of_the_top_k_is_used_not_the_first_hit():
    """State routing can lift a keyword-only State scheme to #1. Its missing dense score must
    not make a well-supported query look unanswerable."""
    assert confidence.tier([hit(None), hit(0.71, OTHER)]) == confidence.OK


def test_hits_that_never_came_from_the_retriever_are_not_judged():
    plain = {'rank_score': 0.0, 'record': REC}   # a carried-over scheme or a test double
    assert confidence.tier([plain]) == confidence.OK


def test_thresholds_are_ordered():
    assert 0 < confidence.MIN_DENSE < confidence.SOFT_DENSE < 1


# -- through the pipeline ------------------------------------------------------------

SID = 'c0ffee00c0ffee00c0ffee00c0ffee00c0ffee'   # 38 chars: a valid session id


@pytest.fixture
def search(monkeypatch):
    """Control exactly what the retriever returns, and record whether it was called."""
    state = {'hits': [hit(0.70)], 'calls': 0}

    def fake(query, k=5):
        state['calls'] += 1
        return state['hits']

    monkeypatch.setattr('retriever.search', fake)
    return state


def test_confident_answer_is_unchanged(search):
    reply, sources, meta = pipeline.rag_answer('SC scholarship ke documents', SID)
    assert 'Sabse relevant scheme yeh hai' in reply
    assert 'Pakka nahi hai' not in reply
    assert meta['confidence'] == 'ok'
    assert sources and sources[0]['name'] == REC['name']


def test_low_confidence_admits_it_and_names_no_scheme(search):
    search['hits'] = [hit(0.41, OTHER)]
    reply, sources, meta = pipeline.rag_answer('gym membership offers', SID)
    assert reply == confidence.NOT_FOUND
    assert OTHER['name'] not in reply
    assert sources == []
    assert meta['confidence'] == 'low'


def test_shaky_answer_is_hedged_and_invites_the_name(search):
    search['hits'] = [hit(0.54)]
    reply, _, meta = pipeline.rag_answer('SC scholarship ke documents', SID)
    assert 'Pakka nahi hai' in reply
    assert REC['name'] in reply                      # still answers, from the nearest scheme
    assert 'Sabse relevant scheme yeh hai' not in reply  # but does not claim it is *the* answer
    assert 'poora naam bol dijiye' in reply
    assert meta['confidence'] == 'soft'


def test_a_refusal_does_not_wipe_the_scheme_in_context(search):
    """An off-topic aside between two questions about one scheme must not break the follow-up."""
    pipeline.rag_answer('Post-Matric Scholarship for SC students ke documents', SID)   # good turn
    search['hits'] = [hit(0.38, OTHER)]
    off_topic, _, meta = pipeline.rag_answer('cricket score batao', SID)
    assert meta['confidence'] == 'low' and off_topic == confidence.NOT_FOUND

    calls_before = search['calls']
    reply, _, meta = pipeline.rag_answer('Aur is scheme ki last date kya hai?', SID)
    assert meta['context_used'] is True
    assert REC['name'] in reply
    assert search['calls'] == calls_before, 'an aspect-only follow-up must not trigger a new retrieval'


def test_a_carried_over_scheme_is_never_gated(search):
    pipeline.rag_answer('Post-Matric Scholarship for SC students ke documents', SID)
    search['hits'] = [hit(0.10, OTHER)]    # would be LOW if it were judged; it must not be consulted
    reply, _, meta = pipeline.rag_answer('Aur is scheme ki last date kya hai?', SID)
    assert meta['confidence'] == 'ok'
    assert REC['name'] in reply


def test_low_and_soft_are_counted(search):
    import stats

    stats.reset()
    search['hits'] = [hit(0.40)]
    pipeline.rag_answer('weather today', None)
    search['hits'] = [hit(0.55)]
    pipeline.rag_answer('SC scholarship ke documents', None)
    counters = stats.snapshot()['counters']
    assert counters.get('low_confidence') == 1
    assert counters.get('soft_confidence') == 1


def test_low_turn_leaves_the_session_untouched(search):
    search['hits'] = [hit(0.40)]
    pipeline.rag_answer('weather today', SID)
    assert conversation.STORE.last(SID) is None


def test_confidence_is_in_the_api_response(search):
    from fastapi.testclient import TestClient

    import server

    search['hits'] = [hit(0.40, OTHER)]
    r = TestClient(server.app).post('/api/ask_text', json={'text': 'weather today', 'speak': False})
    assert r.status_code == 200
    assert r.json()['confidence'] == 'low'
    assert r.json()['reply'] == confidence.NOT_FOUND
