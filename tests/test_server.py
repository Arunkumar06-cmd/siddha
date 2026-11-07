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


def fake_answer(q, hits, follow_up=False):
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


# --- session ids are bearer secrets -------------------------------------------------

SHORT_ID = '12345678'                      # valid under the old 8-char rule, trivially guessable
UUID_ID = '3f2b8c1e-9d4a-4e7b-a1c5-6d0e2f9b7a34'  # what browser crypto.randomUUID() produces


@pytest.mark.parametrize('bad', [SHORT_ID, 'a' * 31, 'x' * 81, 'has space ' * 4, 'semi;colon' * 4])
def test_short_or_malformed_session_ids_are_rejected(client, bad):
    assert client.get(f'/api/session/{bad}').status_code == 400
    assert client.delete(f'/api/session/{bad}').status_code == 400
    r = client.post('/api/ask_text', json={'text': 'SC scholarship?', 'session_id': bad})
    # 400 from our check; an over-long id is stopped earlier by the model's max_length (422).
    assert r.status_code in (400, 422)


def test_browser_uuid_is_accepted(client):
    r = client.post('/api/ask_text', json={'text': 'SC scholarship?', 'session_id': UUID_ID, 'speak': False})
    assert r.status_code == 200
    assert r.json()['session_id'] == UUID_ID


def test_minted_session_ids_are_unique_and_accepted(client):
    # 20 draws plus the two calls below stay under the 30/min per-IP rate limit.
    ids = {client.post('/api/session').json()['session_id'] for _ in range(20)}
    assert len(ids) == 20                      # no collisions
    sid = next(iter(ids))
    assert len(sid) >= 32
    # The minted id round-trips through the routes that validate it.
    assert client.get(f'/api/session/{sid}').json() == {'session_id': sid, 'turn': None}
    assert client.delete(f'/api/session/{sid}').json()['reset'] is True


def test_session_is_isolated_between_ids(client):
    a, b = (client.post('/api/session').json()['session_id'] for _ in range(2))
    client.post('/api/ask_text', json={'text': 'SC scholarship?', 'session_id': a, 'speak': False})
    assert client.get(f'/api/session/{a}').json()['turn'] is not None
    assert client.get(f'/api/session/{b}').json()['turn'] is None


def test_app_version_is_single_sourced(client):
    import server
    from version import VERSION
    assert server.app.version == VERSION
    assert client.get('/api/health').json()['version'] == VERSION
