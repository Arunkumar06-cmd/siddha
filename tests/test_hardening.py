"""Regression tests for the security and cost limits added before submission.

Each test fails on the code as it was before the fix:
  * a ?session= link let its author read the visitor's next transcript
  * session responses were cacheable, so a shared browser could replay them
  * the Gnani budget was only a counter: the 5,001st call still went out
  * multipart bodies were spooled to disk before the route's size check ran
  * the quality counters had denominators that were never incremented
"""
import concurrent.futures as cf
import pathlib

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import stats


@pytest.fixture(autouse=True)
def _clean_stats():
    stats.reset()
    yield
    stats.reset()


def _reset_breaker(breaker):
    breaker._fails = 0
    breaker._opened_at = 0.0
    breaker._probing = False


# -- credit budgets ----------------------------------------------------------

def test_global_budget_refuses_the_next_call(monkeypatch):
    monkeypatch.setattr(stats, 'CREDIT_BUDGET', 1)
    stats.gnani_call('stt', 'a')
    with pytest.raises(stats.CreditExhausted) as exc:
        stats.gnani_call('tts', 'b')
    assert exc.value.scope == 'global'
    assert stats.credits_used() == 1


def test_one_client_cannot_spend_the_whole_budget(monkeypatch):
    monkeypatch.setattr(stats, 'CLIENT_CREDIT_BUDGET', 2)
    stats.gnani_call('stt', 'greedy')
    stats.gnani_call('tts', 'greedy')
    with pytest.raises(stats.CreditExhausted) as exc:
        stats.gnani_call('stt', 'greedy')
    assert exc.value.scope == 'client'
    stats.gnani_call('stt', 'someone-else')       # other visitors are unaffected


def test_concurrent_calls_cannot_overspend_the_budget(monkeypatch):
    monkeypatch.setattr(stats, 'CREDIT_BUDGET', 5)

    def spend(_):
        try:
            stats.gnani_call('stt', f'client-{_}')
            return True
        except stats.CreditExhausted:
            return False

    with cf.ThreadPoolExecutor(max_workers=20) as ex:
        granted = list(ex.map(spend, range(20)))
    assert sum(granted) == 5
    assert stats.credits_used() == 5


def test_credit_exhaustion_is_a_503_and_does_not_reach_the_provider(monkeypatch, tmp_path):
    import pipeline

    _reset_breaker(pipeline.STT_BREAKER)
    called = []
    monkeypatch.setattr(stats, 'gnani_call',
                        lambda service, client='anon': (_ for _ in ()).throw(
                            stats.CreditExhausted('global')))
    monkeypatch.setattr('requests.post', lambda *a, **kw: called.append(1))

    def fake_wav():
        path = tmp_path / 'credit-test.wav'
        path.write_bytes(b'\x00')
        return path

    with pytest.raises(HTTPException) as exc:
        pipeline.transcribe(fake_wav())
    assert exc.value.status_code == 503
    assert not called, 'no provider request may be made once the budget is spent'


def test_a_refused_credit_does_not_hold_the_half_open_probe(monkeypatch, tmp_path):
    """The probe slot is claimed before the call. A budget refusal is our own
    limit, not a provider failure: it must release the slot, not re-open the
    circuit."""
    import time

    import pipeline

    breaker = pipeline.STT_BREAKER
    _reset_breaker(breaker)
    breaker._fails = breaker.threshold
    breaker._opened_at = time.time() - breaker.cooldown - 1
    monkeypatch.setattr(stats, 'gnani_call',
                        lambda service, client='anon': (_ for _ in ()).throw(
                            stats.CreditExhausted('client')))

    def fake_wav():
        path = tmp_path / 'probe-test.wav'
        path.write_bytes(b'\x00')
        return path

    try:
        with pytest.raises(HTTPException) as exc:
            pipeline.transcribe(fake_wav())
        assert exc.value.status_code == 503
        assert breaker._probing is False, 'the probe slot must be released'
        assert breaker.state() == 'half_open'
    finally:
        _reset_breaker(breaker)


# -- upload body limit -------------------------------------------------------

def test_declared_oversized_body_is_rejected_before_multipart_parsing(monkeypatch):
    import server

    server._ip_calls.clear()
    monkeypatch.setattr(server, 'MAX_UPLOAD_BYTES', 1024)
    client = TestClient(server.app, raise_server_exceptions=False)
    r = client.post('/api/ask_audio',
                    files={'audio': ('q.wav', b'x' * 4096, 'audio/wav')})
    assert r.status_code == 413
    assert 'too large' in r.json()['error']


def test_streamed_body_without_content_length_is_cut_off(monkeypatch):
    """A client can omit Content-Length. The middleware must count bytes as they
    arrive instead of trusting the header."""
    import asyncio

    import server

    monkeypatch.setattr(server, 'MAX_UPLOAD_BYTES', 100)
    chunks = [b'x' * 60, b'x' * 60, b'x' * 60]
    sent = []

    async def app(scope, receive, send):
        while True:
            message = await receive()
            if not message.get('more_body'):
                break
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'ok'})

    async def receive():
        body = chunks.pop(0)
        return {'type': 'http.request', 'body': body, 'more_body': bool(chunks)}

    async def send(message):
        sent.append(message)

    scope = {'type': 'http', 'path': '/api/ask_audio', 'headers': []}
    asyncio.run(server._UploadBodyLimit(app)(scope, receive, send))
    assert sent[0]['type'] == 'http.response.start'
    assert sent[0]['status'] == 413


def test_other_routes_are_not_body_limited(monkeypatch):
    import asyncio

    import server

    monkeypatch.setattr(server, 'MAX_UPLOAD_BYTES', 10)
    sent = []

    async def app(scope, receive, send):
        message = await receive()
        assert message['body'] == b'x' * 100
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'ok'})

    async def receive():
        return {'type': 'http.request', 'body': b'x' * 100, 'more_body': False}

    async def send(message):
        sent.append(message)

    scope = {'type': 'http', 'path': '/api/ask_text', 'headers': []}
    asyncio.run(server._UploadBodyLimit(app)(scope, receive, send))
    assert sent[0]['status'] == 200


# -- session hygiene ---------------------------------------------------------

def test_session_responses_are_not_cacheable():
    import server

    server._ip_calls.clear()
    client = TestClient(server.app)
    created = client.post('/api/session')
    sid = created.json()['session_id']
    assert created.headers['cache-control'] == 'no-store'
    assert client.get(f'/api/session/{sid}').headers['cache-control'] == 'no-store'
    assert client.delete(f'/api/session/{sid}').headers['cache-control'] == 'no-store'


def test_the_page_never_adopts_a_session_id_from_the_url():
    page = (pathlib.Path(__file__).resolve().parent.parent / 'static' / 'index.html').read_text()
    assert "params.get('session')" not in page
    assert 'name="referrer"' in page


# -- quality counters --------------------------------------------------------

def test_audio_quality_counters_have_real_denominators(monkeypatch, tmp_path):
    import server

    server._ip_calls.clear()
    monkeypatch.setattr(server, 'to_wav', lambda raw, suffix: tmp_path / 'x.wav')
    monkeypatch.setattr(server, 'transcribe', lambda wav: ('', 'hi-IN'))
    client = TestClient(server.app)
    r = client.post('/api/ask_audio', files={'audio': ('q.wav', b'RIFFxxxxWAVE', 'audio/wav')})
    assert r.status_code == 200
    counters = stats.snapshot()['counters']
    assert counters['audio_turns'] == 1
    assert counters['empty_transcript'] == 1
    assert stats.snapshot()['rates']['empty_transcript'] == 1.0


def test_audio_and_tts_counters_are_incremented(monkeypatch, tmp_path):
    import server

    server._ip_calls.clear()
    monkeypatch.setattr(server, 'to_wav', lambda raw, suffix: tmp_path / 'x.wav')
    monkeypatch.setattr(server, 'transcribe', lambda wav: ('documents kya chahiye', 'hi-IN'))
    monkeypatch.setattr(server, 'rag_answer', lambda q, sid: ('Answer.', [], {'follow_up': False}))
    monkeypatch.setattr(server, 'synthesize', lambda reply: b'AUDIO')
    monkeypatch.setattr(server, 'speakable', lambda reply: (reply, True))
    client = TestClient(server.app)
    r = client.post('/api/ask_audio', files={'audio': ('q.wav', b'RIFFxxxxWAVE', 'audio/wav')})
    assert r.status_code == 200
    assert r.json()['audio_truncated'] is True
    counters = stats.snapshot()['counters']
    assert counters['audio_turns'] == 1
    assert counters['audio_returned'] == 1
    assert counters['audio_truncated'] == 1
    assert counters['tts_attempted'] == 1
    assert stats.snapshot()['rates']['audio_truncated'] == 1.0


def test_tts_degraded_rate_uses_the_attempt_denominator(monkeypatch):
    import server

    server._ip_calls.clear()
    monkeypatch.setattr(server, 'rag_answer', lambda q, sid: ('Answer.', [], {'follow_up': False}))
    monkeypatch.setattr(server, 'synthesize',
                        lambda reply: (_ for _ in ()).throw(HTTPException(502, 'down')))
    client = TestClient(server.app)
    r = client.post('/api/ask_text', json={'text': 'documents kya chahiye'})
    assert r.status_code == 200
    assert r.json()['audio_wav_b64'] is None
    snap = stats.snapshot()
    assert snap['counters']['tts_attempted'] == 1
    assert snap['counters']['tts_degraded'] == 1
    assert snap['rates']['tts_degraded'] == 1.0
