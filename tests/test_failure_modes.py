"""Failure-mode tests: provider timeouts, breaker, concurrency, rate limit, artifact cleanup."""
import concurrent.futures as cf
import io
import time
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


def fake_answer(q, hits, follow_up=False):
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
        self.text = ''

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


@pytest.mark.parametrize('body', [
    [1],
    {'success': True, 'transcript': None},
    {'success': True, 'transcript': 42},
])
def test_malformed_stt_success_payload_returns_typed_error_and_cleans_audio(monkeypatch, tmp_path, body):
    import pipeline

    pipeline.STT_BREAKER.record_success()
    monkeypatch.setattr('requests.post', lambda url, **kw: FakeResp(200, body=body))
    wav = tmp_path / 'malformed-provider.wav'
    wav.write_bytes(b'RIFF')
    with pytest.raises(HTTPException) as exc:
        pipeline.transcribe(wav)
    assert exc.value.status_code == 502
    assert not wav.exists()


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

    monkeypatch.setattr(server, 'RATE_LIMIT', 3)  # restored on teardown; a bare assignment leaked into every later test
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


# -- regressions from the pre-submission review ------------------------------

def test_stt_retry_resends_the_whole_upload(monkeypatch):
    """The retry used to reuse a file handle already read to EOF, so the second
    attempt uploaded an empty file."""
    import server

    server.STT_BREAKER.record_success()
    sizes = []

    def fake_post(url, **kw):
        sizes.append(len(kw['files']['audio_file'][1]))
        if len(sizes) == 1:
            raise requests.Timeout('slow')
        return FakeResp(200)

    monkeypatch.setattr('requests.post', fake_post)
    monkeypatch.setattr('time.sleep', lambda s: None)  # skip the retry backoff
    wav = server.to_wav(silent_wav_bytes(1), '.wav')
    server.transcribe(wav)
    assert len(sizes) == 2
    assert sizes[0] == sizes[1] > 0


def test_wav_is_deleted_even_when_the_circuit_is_open():
    import pipeline

    wav = pipeline.to_wav(silent_wav_bytes(1), '.wav')
    pipeline.STT_BREAKER._fails = pipeline.STT_BREAKER.threshold
    pipeline.STT_BREAKER._opened_at = time.time()
    try:
        with pytest.raises(HTTPException):
            pipeline.transcribe(wav)
        assert not wav.exists(), 'temp file leaked when the circuit was open'
    finally:
        pipeline.STT_BREAKER.record_success()


def test_provider_4xx_does_not_trip_the_breaker(monkeypatch):
    """A bad upload is the caller's problem; six of them must not take STT down for everyone."""
    import pipeline

    pipeline.STT_BREAKER.record_success()
    monkeypatch.setattr('requests.post', lambda url, **kw: FakeResp(400, body={}))
    for _ in range(6):
        wav = pipeline.to_wav(silent_wav_bytes(1), '.wav')
        with pytest.raises(HTTPException) as exc:
            pipeline.transcribe(wav)
        assert exc.value.status_code == 422
    assert pipeline.STT_BREAKER.state() == 'closed'


def test_tts_text_is_cut_on_sentence_boundaries(monkeypatch):
    """The reply used to be sliced at character 600, mid-sentence or mid-tag."""
    import pipeline

    pipeline.TTS_BREAKER.record_success()
    sent = []

    def fake_post(url, **kw):
        sent.append(kw['json']['text'])
        return FakeResp(200, content=b'WAV')

    monkeypatch.setattr('requests.post', fake_post)
    long_reply = ' '.join(f'Yeh sentence number {i} hai.' for i in range(80))
    pipeline.synthesize(long_reply)
    assert len(sent[0]) <= pipeline.MAX_TTS_CHARS
    assert sent[0].rstrip().endswith('.')
    assert not sent[0].rstrip().endswith('<pauses>')
    assert pipeline.speakable(long_reply)[1] is True, 'the client must be told the audio is shorter than the text'


def test_oversized_upload_is_rejected_before_any_decoding(monkeypatch):
    import pipeline
    import server

    monkeypatch.setattr(pipeline, 'MAX_AUDIO_BYTES', 10)
    monkeypatch.setattr(server, 'MAX_AUDIO_BYTES', 10)
    r = TestClient(server.app).post('/api/ask_audio', files={'audio': ('q.wav', silent_wav_bytes(1), 'audio/wav')})
    assert r.status_code == 413


def test_non_audio_upload_is_refused_without_calling_ffmpeg():
    import pipeline

    with pytest.raises(HTTPException) as exc:
        pipeline.to_wav(b'#EXTM3U\nhttp://example.com/x\n', '.wav')
    assert exc.value.status_code == 415
