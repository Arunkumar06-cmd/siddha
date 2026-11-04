import base64, json
import pytest
from fastapi.testclient import TestClient

# Mock the network layer before importing server
import responder, retriever

class FakeHit(dict): pass
FAKE_HITS = [{'rank_score': 0.05, 'record': {
    'name': 'Test Scheme', 'level': 'State',
    'eligibility': 'All', 'benefits': '1000', 'documents': 'Aadhaar', 'application': 'Portal',
}}]

def fake_search(q, k=5): return FAKE_HITS
def fake_answer(q, hits): return ('Suno. Test answer with pauses.', [{'name':'Test Scheme','score':0.05,'level':'State'}], False)

class FakeResp:
    status_code = 200
    def json(self): return {'success': True, 'transcript': 'test', 'model':'prisma-v3.0', 'detected_language_code':'hi-IN'}
    content = b'RIFFFAKEWAV'

class FakeTimeout(Exception): pass

def fake_post(url, **kwargs):
    return FakeResp()

def test_health():
    from server import app
    from unittest.mock import patch
    with patch('retriever.search', fake_search), patch('responder.answer', fake_answer), \
         patch('requests.post', side_effect=lambda *a, **k: FakeResp()):
        r = TestClient(app).get('/api/health')
        assert r.status_code == 200 and r.json()['status'] == 'ok'

def test_ask_text_round_trip():
    from server import app
    from unittest.mock import patch
    with patch('retriever.search', fake_search), patch('responder.answer', fake_answer), \
         patch('requests.post', side_effect=lambda *a, **k: FakeResp()):
        r = TestClient(app).post('/api/ask_text', json={'text':'SC scholarship?'})
        j = r.json()
        assert r.status_code == 200
        assert j['transcript'] == 'SC scholarship?'
        assert j['reply'] == 'Suno. Test answer with pauses.'
        assert j['sources'][0]['name'] == 'Test Scheme'
        raw = base64.b64decode(j['audio_wav_b64']); assert raw == b'RIFFFAKEWAV'

def test_ask_text_rejects_empty():
    from server import app
    r = TestClient(app).post('/api/ask_text', json={'text':''})
    assert r.status_code == 422
