"""Failure-mode tests: provider timeouts, breaker, concurrency, rate limit, artifact cleanup."""
import concurrent.futures as cf
import io
import wave

import pytest
import requests
from fastapi import HTTPException
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
        'Suno. Test answer.',
        [{'name': 'Test Scheme', 'score': 0.05, 'level': 'State'}],
        False,
    )


class FakeResp:
    def __init__(self, status=200, body=None, content=b''):
        self.status_code = status
        self._body = body or {'success': True, 'transcript': 'test', 'detected_language_code': 'hi-IN'}
        self.content = content

    def json(self):
        return self._body


def silent_wav_bytes(seconds=1):
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b'\x00\x01' * 16000 * seconds)
    return buf.getvalue()


def test_temp_wav_is_deleted(monkeypatch):
    import server

    monkeypatch.setattr('requests.post', lambda url, **kw: FakeResp(200))
    monkeypatch.setattr('retriever.search', fake_search)
    monkeypatch.setattr('responder.answer', fake_answer)

    wav = server.to_wav(silent_wav_bytes(1), '.wav')
    assert wav.exists()
    server.transcribe(wav)
    assert not wav.exists(), 'wav must be deleted after transcribe'


def test_stt_retries_on_timeout_then_circuit_opens(monkeypatch):
    import server

    server.STT_BREAKER._fails = 0
    server.STT_BREAKER._opened_at = 0.0
    monkeypatch.setattr('retriever.search', fake_search)
    monkeypatch.setattr('responder.answer', fake_answer)

    def fake_post(url, **kw):
        raise requests.Timeout('boom')

    monkeypatch.setattr('requests.post', fake_post)
    client = TestClient(server.app, raise_server_exceptions=False)

    for _ in range(5):
        r = client.post('/api/ask_audio', files={'audio': ('q.wav', silent_wav_bytes(1), 'audio/wav')})
        assert r.status_code == 502
    assert server.STT_BREAKER.state() == 'open'


def test_concurrent_text_requests_all_succeed(monkeypatch):
    import server

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
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429


def test_to_wav_without_ffmpeg_raises_typed_503(monkeypatch):
    import pipeline

    monkeypatch.setattr(pipeline, 'FFMPEG_BIN', None)
    with pytest.raises(HTTPException) as exc:
        pipeline.to_wav(b'not really audio', '.wav')
    assert exc.value.status_code == 503
    assert 'unavailable' in exc.value.detail


def test_health_reports_missing_ffmpeg(monkeypatch):
    import server

    monkeypatch.setattr(server, 'FFMPEG_BIN', None)
    r = TestClient(server.app).get('/api/health')
    assert r.status_code == 503
    assert 'ffmpeg' in r.json()['error']


def test_health_is_independent_of_working_directory(tmp_path, monkeypatch):
    import server

    monkeypatch.chdir(tmp_path)
    r = TestClient(server.app).get('/api/health')
    assert r.status_code == 200
    assert r.json()['status'] == 'ok'
