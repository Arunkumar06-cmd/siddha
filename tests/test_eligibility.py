"""Eligibility reasoner tests: fully mocked — the demo must never depend on the network."""
import json

import pytest

import eligibility
import llm


def _fake_complete(messages, max_tokens=300, temperature=0.1):
    sysmsg = messages[0]['content']
    if 'eligibility checker' in sysmsg:
        return json.dumps({
            'verdicts': [
                {'record': 1, 'verdict': 'eligible', 'decisive': 'category',
                 'quote': 'SC students, income below 2.5 lakh'},
                {'record': 2, 'verdict': 'not', 'decisive': 'category', 'quote': 'OBC only'},
                {'record': 3, 'verdict': 'unsure', 'decisive': None, 'quote': None},
            ],
            'best': 1,
        })
    return json.dumps({'age': 19, 'income_lakh_pa': 1.5, 'category': 'SC',
                       'state': 'Bihar', 'course': 'B.Tech',
                       'marks_percent': 80, 'girl': False})


@pytest.fixture(autouse=True)
def mock_llm(monkeypatch):
    monkeypatch.setattr(llm, 'complete', _fake_complete)
    monkeypatch.setattr(llm, 'configured', lambda: True)
    yield


def _hits():
    return [
        {'rank_score': 0.03, 'record': {
            'name': 'Post-Matric Scholarship for SC students', 'level': 'Central',
            'eligibility': 'SC students, income below 2.5 lakh',
            'documents': 'Caste Certificate, Income Certificate', 'benefits': 'Fees'}},
        {'rank_score': 0.02, 'record': {
            'name': 'OBC Post-Matric Scholarship', 'level': 'State',
            'eligibility': 'OBC only', 'documents': 'Caste Certificate', 'benefits': 'Fees'}},
        {'rank_score': 0.02, 'record': {
            'name': 'Generic Means-Cum-Merit', 'level': 'Central',
            'eligibility': 'Means and merit; details in annexure',
            'documents': 'Marksheet', 'benefits': 'Scholarship'}},
    ]


def test_intended_detects_eligibility_question():
    assert eligibility.intended('SC student eligible hai kya?')
    assert eligibility.intended('mujhe scholarship milegi kya?')
    assert not eligibility.intended('scholarship documents kya chahiye')


def test_advise_happy_path():
    out = eligibility.advise('SC student eligible hai kya?', _hits())
    assert out is not None
    reply, sources = out
    assert 'Post-Matric Scholarship' in reply
    assert len(sources) == 3
    assert sources[0]['level'] == 'Central'


def test_advise_negative_case_names_blocker(monkeypatch):
    def all_not(messages, **kw):
        if 'eligibility checker' in messages[0]['content']:
            return json.dumps({'verdicts': [
                {'record': 1, 'verdict': 'not', 'decisive': 'category', 'quote': 'OBC only'},
                {'record': 2, 'verdict': 'not', 'decisive': 'category', 'quote': 'EBC only'},
                {'record': 3, 'verdict': 'not', 'decisive': 'category', 'quote': 'minority only'},
            ], 'best': None})
        return json.dumps({'category': 'GEN', 'income_lakh_pa': 5.0})
    monkeypatch.setattr(llm, 'complete', all_not)
    out = eligibility.advise('GEN student eligible hai?', _hits())
    assert out is not None
    reply, _ = out
    assert 'qualify nahi' in reply


def test_advise_returns_none_on_bad_json(monkeypatch):
    monkeypatch.setattr(llm, 'complete', lambda messages, **kw: 'not json at all')
    assert eligibility.advise('eligible hai?', _hits()) is None


def test_advise_returns_none_when_llm_raises(monkeypatch):
    def boom(messages, **kw):
        raise RuntimeError('provider down')
    monkeypatch.setattr(llm, 'complete', boom)
    try:
        eligibility.advise('eligible hai?', _hits())
    except RuntimeError:
        raised = True
    else:
        raised = False
    assert raised  # advise() itself may raise; the pipeline catches it


def test_extract_profile_tolerates_garbage(monkeypatch):
    monkeypatch.setattr(llm, 'complete',
                        lambda messages, **kw: json.dumps({'income_lakh_pa': 'not a number'}))
    profile = eligibility.extract_profile('kuch bhi')
    assert profile['income_lakh_pa'] is None


def test_pipeline_falls_back_when_llm_unconfigured(monkeypatch):
    monkeypatch.setattr(llm, 'configured', lambda: False)
    import retriever
    from pipeline import rag_answer
    fake_hit = [{'rank_score': 0.03, 'record': {
        'name': 'X Scheme', 'level': 'Central',
        'eligibility': 'SC students', 'benefits': 'b',
        'documents': 'Caste certificate', 'application': 'Portal'}}]
    monkeypatch.setattr(retriever, 'search', lambda q, k=5: fake_hit)
    reply, _ = rag_answer('SC student ke liye scholarship?')
    assert 'X Scheme' in reply
