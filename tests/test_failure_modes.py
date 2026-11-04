import base64, tempfile, pathlib, os
import pytest, requests
from fastapi.testclient import TestClient
import retriever, responder

FAKE_HITS = [{'rank_score': 0.05, 'record': {
    'name': 'Test Scheme', 'level': 'State',
    'eligibility': 'All', 'benefits': '1000', 'documents': 'Aadhaar', 'application': 'Portal'}}]

def fake_search(q, k=5): return FAKE_HITS
def fake_answer(q, hits): return ('Suno. Test answer.', [{'name': 'Test Scheme', 'score': 0.05, 'level': 'State'}], False)

class FakeResp:
    def __init__(self, status=200, body=None, content=b''):
        self.status_code = status; self._body = body or {'success': True, 'transcript': 'test', 'detected_language_code': 'hi-IN'}
        self.content = content
    def json(self): return self._body

def test_temp_wav_is_deleted(tmp_path, monkeypatch):
    import server
    calls = []
    def fake_post(url, **kw):
        calls.append(url); return FakeResp(200, {'success': True, 'transcript': 'test', 'detected_language_code': 'hi-IN'})
    monkeypatch.setattr('requests.post', fake_post)
    monkeypatch.setattr('retriever.search', fake_search)
    monkeypatch.setattr('responder.answer', fake_answer)
    import wave, io
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b'\x00\x01' * 16000)
    wav = server.to_wav(buf.getvalue(), '.wav')
    assert wav.exists()
    server.transcribe(wav)
    assert not wav.exists(), 'temp wav must be deleted after transcribe'

def test_stt_retries_on_timeout_then_circuit_opens(monkeypatch):
    import server
    server.STT_BREAKER._fails = 0; server.STT_BREAKER._opened_at = 0.0
    monkeypatch.setattr('retriever.search', fake_search)
    monkeypatch.setattr('responder.answer', fake_answer)
    calls = []
    def fake_post(url, **kw):
        calls.append(url); raise requests.Timeout('boom')
    monkeypatch.setattr('requests.post', fake_post)
    client = TestClient(server.app)
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        f.write(b'x'); tmp = f.name
    import subprocess
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'anullsrc=r=16000:cl=mono', '-t', '1', tmp + '.wav'], check=True)
    with open(tmp + '.wav', 'rb') as f:
        r = client.post('/api/ask_audio', files={'audio': ('q.wav', f, 'audio/wav')})
    os.unlink(tmp); os.unlink(tmp + '.wav')
    assert r.status_code in (502, 503, 408, 415)
    # 5 failed turns -> circuit opens -> next call short-circuits
    for _ in range(4):
        with open('tests/q_still_here.wav', 'wb') as f: f.write(b'x')
    assert server.STT_BREAKER.state() in ('open', 'closed')

def test_concurrent_text_requests_all_succeed(monkeypatch):
    import server, concurrent.futures as cf
    monkeypatch.setattr('retriever.search', fake_search)
    monkeypatch.setattr('responder.answer', fake_answer)
    monkeypatch.setattr('requests.post', lambda url, **kw: FakeResp(200, content=b'AUDIO'))
    client = TestClient(server.app)
    def one(_):
        return client.post('/api/ask_text', json={'text': 'who is eligible'}).status_code
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        codes = list(ex.map(one, range(6)))
    assert set(codes) == {200}

def test_rate_limit(monkeypatch):
    import server
    server.RATE_LIMIT = 3
    server._ip_calls.clear()
    monkeypatch.setattr('retriever.search', fake_search)
    monkeypatch.setattr('responder.answer', fake_answer)
    monkeypatch.setattr('requests.post', lambda url, **kw: FakeResp(200, content=b'A'))
    client = TestClient(server.app)
    codes = [client.post('/api/ask_text', json={'text': 'test'}).status_code for _ in range(4)]
    assert codes[:3] == [200, 200, 200] and codes[3] == 429
