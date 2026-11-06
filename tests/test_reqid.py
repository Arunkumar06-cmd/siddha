"""Request-id correlation: minted per request, logged, returned, and sent to Gnani."""
import contextvars
import logging
import re
import unittest.mock as mock

import pytest
from fastapi.testclient import TestClient

import pipeline
import reqid

HEX32 = re.compile(r'^[0-9a-f]{32}$')
META = {'follow_up': False, 'context_used': False, 'context_name': None}


@pytest.fixture
def client():
    import server
    return TestClient(server.app)


# --- helpers in src/reqid.py -------------------------------------------------

@pytest.mark.parametrize('good', ['abcdefgh', 'req-1234_AB.cd', 'a' * 64])
def test_well_formed_caller_id_is_kept(good):
    assert reqid.accept_or_new(good) == good


@pytest.mark.parametrize('bad', [None, '', 'short', 'a' * 65, 'has space in it', 'line\nbreak12345', 'x;rm -rf /1'])
def test_malformed_caller_id_is_replaced(bad):
    assert HEX32.match(reqid.accept_or_new(bad))


def test_upstream_id_is_per_stage_and_stable_within_a_request():
    def run():
        reqid.set_current('abcdefgh1234')
        return reqid.upstream('stt'), reqid.upstream('stt'), reqid.upstream('tts')

    stt1, stt2, tts = contextvars.copy_context().run(run)
    assert stt1 == stt2 == 'abcdefgh1234-stt'   # a retry of the same call reuses its id
    assert tts == 'abcdefgh1234-tts'            # a different call never shares it


def test_upstream_id_outside_a_request_is_still_unique():
    a, b = reqid.upstream('stt'), reqid.upstream('stt')
    assert a != b and a.endswith('-stt')


def test_every_log_record_carries_the_id():
    reqid.install_log_factory()

    def run():
        reqid.set_current('trace-me-0001')
        return logging.makeLogRecord({}).request_id

    assert contextvars.copy_context().run(run) == 'trace-me-0001'
    assert logging.makeLogRecord({}).request_id == reqid.NO_REQUEST


# --- HTTP layer --------------------------------------------------------------

def test_response_carries_a_minted_id(client):
    r = client.get('/api/health')
    assert HEX32.match(r.headers['X-Request-ID'])


def test_inbound_id_is_echoed_and_junk_is_replaced(client):
    assert client.get('/api/health', headers={'X-Request-ID': 'client-trace-42'}).headers['X-Request-ID'] == 'client-trace-42'
    junk = client.get('/api/health', headers={'X-Request-ID': 'no good!'}).headers['X-Request-ID']
    assert HEX32.match(junk)


def test_id_is_on_error_and_rate_limited_responses(client):
    bad = client.get('/api/session/!!', headers={'X-Request-ID': 'client-trace-43'})
    assert bad.status_code == 400 and bad.headers['X-Request-ID'] == 'client-trace-43'
    with mock.patch('server.RATE_LIMIT', 0):
        limited = client.get('/api/metrics', headers={'X-Request-ID': 'client-trace-44'})
    assert limited.status_code == 429 and limited.headers['X-Request-ID'] == 'client-trace-44'


def test_id_reaches_the_threadpool_route(client):
    seen = {}

    def spy(text, sid=None):
        seen['id'] = reqid.current()
        return 'ok', [], META

    with mock.patch('server.rag_answer', spy), mock.patch('server.synthesize', return_value=b'RIFF'):
        r = client.post('/api/ask_text', json={'text': 'scholarship'}, headers={'X-Request-ID': 'client-trace-45'})
    assert r.status_code == 200
    assert seen['id'] == 'client-trace-45'


def test_unhandled_error_still_returns_the_id(client):
    import server
    with mock.patch('server.rag_answer', side_effect=RuntimeError('boom')):
        r = TestClient(server.app, raise_server_exceptions=False).post(
            '/api/ask_text', json={'text': 'scholarship'}, headers={'X-Request-ID': 'client-trace-46'})
    assert r.status_code == 500 and r.headers['X-Request-ID'] == 'client-trace-46'


# --- upstream headers --------------------------------------------------------

class _Resp:
    status_code = 200
    text = ''
    content = b'RIFF'

    def json(self):
        return {'success': True, 'transcript': 'hello', 'detected_language_code': 'en-IN'}


def test_gnani_calls_send_the_request_id(tmp_path):
    wav = tmp_path / 'q.wav'
    wav.write_bytes(b'RIFF0000WAVE')
    sent = []

    def fake_post(url, headers=None, **kw):
        sent.append((url, headers['X-API-Request-ID']))
        return _Resp()

    def run():
        reqid.set_current('trace-me-0002')
        with mock.patch.object(pipeline.requests, 'post', fake_post):
            pipeline.transcribe(wav)
            pipeline.synthesize('Suno. Test.')

    with mock.patch.object(pipeline, 'STT_BREAKER', mock.Mock(allow=lambda: True)), \
         mock.patch.object(pipeline, 'TTS_BREAKER', mock.Mock(allow=lambda: True)):
        contextvars.copy_context().run(run)

    assert [h for _, h in sent] == ['trace-me-0002-stt', 'trace-me-0002-tts']
