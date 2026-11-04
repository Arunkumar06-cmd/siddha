"""HTTP integration tests for Siddha's routes, with provider HTTP calls mocked."""
import base64
import unittest.mock as mock

import pytest
from fastapi.testclient import TestClient

FAKE_HITS = [
    {
        'rank_score': 0.05,
        'record': {
            'name': 'Test Scheme',
            'level': 'State',
            'eligibility': 'All',
            'benefits': '1000',
            'documents': 'Aadhaar',
            'application': 'Portal',
        },
    },
]


def fake_search(q, k=5):
    return FAKE_HITS


def fake_answer(q, hits):
    return (
        'Suno. Test answer with pauses.',
        [{'name': 'Test Scheme', 'score': 0.05, 'level': 'State'}],
        False,
    )


class FakeResp:
    """Minimal stand-in for provider HTTP responses."""

    def __init__(self, status=200, body=None, content=b""):
        self.status_code = status
        self._body = body or {'success': True, 'transcript': 'test', 'detected_language_code': 'hi-IN'}
        self.content = content

    def json(self):
        return self._body


def good_post(url, **kwargs):
    return FakeResp(200, content=b'RIFFFAKEWAV')


@pytest.fixture
def client():
    import server

    with mock.patch('retriever.search', fake_search), \
         mock.patch('responder.answer', fake_answer), \
         mock.patch('requests.post', side_effect=good_post):
        yield TestClient(server.app, raise_server_exceptions=True)


def test_health(client):
    r = client.get('/api/health')
    assert r.status_code == 200
    assert r.json()['status'] == 'ok'


def test_ask_text_round_trip(client):
    r = client.post('/api/ask_text', json={'text': 'SC scholarship?'})
    j = r.json()
    assert r.status_code == 200
    assert j['transcript'] == 'SC scholarship?'
    assert j['reply'] == 'Suno. Test answer with pauses.'
    assert j['sources'][0]['name'] == 'Test Scheme'

    raw = base64.b64decode(j['audio_wav_b64'])
    assert raw == b'RIFFFAKEWAV'


def test_ask_text_rejects_empty(client):
    r = client.post('/api/ask_text', json={'text': ''})
    assert r.status_code == 422
    assert r.json()['error'].startswith('Invalid request')
