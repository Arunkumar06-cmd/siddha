"""Per-stage latency: recorded per request, exposed as Server-Timing and in metrics."""
import re
import unittest.mock as mock

import pytest
from fastapi.testclient import TestClient

import pipeline
import timing

META = {'follow_up': False, 'context_used': False, 'context_name': None}


@pytest.fixture(autouse=True)
def _clean():
    timing.reset()
    yield
    timing.reset()


@pytest.fixture
def client():
    import server
    return TestClient(server.app)


# --- src/timing.py -----------------------------------------------------------

def test_stage_records_into_request_dict_and_aggregate():
    t = timing.begin()
    with timing.stage('stt'):
        pass
    with timing.stage('stt'):
        pass
    assert set(t) == {'stt'}
    assert timing.snapshot()['stt']['count'] == 2


def test_stage_is_recorded_even_when_the_block_raises():
    timing.begin()
    with pytest.raises(ValueError), timing.stage('tts'):
        raise ValueError('boom')
    assert timing.snapshot()['tts']['count'] == 1


def test_max_tracks_the_slowest_call():
    timing.record('stt', 0.2)
    timing.record('stt', 0.9)
    timing.record('stt', 0.4)
    s = timing.snapshot()['stt']
    assert s['count'] == 3
    assert s['max_s'] == 0.9
    assert s['sum_s'] == pytest.approx(1.5)


def test_server_timing_header_is_in_milliseconds():
    assert timing.server_timing({'stt': 0.4123, 'tts': 1.0}) == 'stt;dur=412.3, tts;dur=1000.0'
    assert timing.server_timing({}) == ''
    assert timing.server_timing(None) == ''


def test_prometheus_text_has_count_sum_and_max():
    timing.record('retrieve', 0.25)
    text = timing.prometheus()
    assert 'siddha_stage_seconds_count{stage="retrieve"} 1' in text
    assert 'siddha_stage_seconds_sum{stage="retrieve"} 0.25' in text
    assert 'siddha_stage_seconds_max{stage="retrieve"} 0.25' in text


# --- HTTP layer --------------------------------------------------------------

def test_ask_text_returns_server_timing_with_total(client):
    def fake_rag(q, sid=None):
        with timing.stage('retrieve'):
            pass
        with timing.stage('respond'):
            pass
        return 'Suno. jawab', [], META

    with mock.patch('server.rag_answer', fake_rag), mock.patch('server.synthesize', return_value=b'RIFFxxxx'):
        r = client.post('/api/ask_text', json={'text': 'scholarship for girls'})
    assert r.status_code == 200
    header = r.headers['Server-Timing']
    assert re.search(r'retrieve;dur=\d', header)
    assert re.search(r'respond;dur=\d', header)
    assert re.search(r'total;dur=\d', header)


def test_health_has_no_server_timing(client):
    assert 'Server-Timing' not in client.get('/api/health').headers


def test_timings_do_not_leak_between_requests(client):
    def fake_rag(q, sid=None):
        with timing.stage('retrieve'):
            pass
        return 'Suno.', [], META

    with mock.patch('server.rag_answer', fake_rag), mock.patch('server.synthesize', return_value=b'RIFFxxxx'):
        client.post('/api/ask_text', json={'text': 'first question'})
    with mock.patch('server.rag_answer', return_value=('Suno.', [], META)), \
            mock.patch('server.synthesize', return_value=b'RIFFxxxx'):
        second = client.post('/api/ask_text', json={'text': 'second question'})
    assert 'retrieve' not in second.headers['Server-Timing']


def test_api_metrics_and_prometheus_endpoint_expose_stages(client):
    timing.record('stt', 0.3)
    body = client.get('/api/metrics').json()
    assert body['stage_seconds']['stt']['count'] == 1
    prom = client.get('/metrics')
    assert prom.status_code == 200
    assert prom.headers['content-type'].startswith('text/plain')
    assert 'siddha_stage_seconds_count{stage="stt"} 1' in prom.text


def test_pipeline_stages_are_timed(tmp_path):
    """The real rag_answer path records retrieve and respond."""
    record = {'id': 'r1', 'name': 'Test Scheme', 'state': 'All'}
    with mock.patch.object(pipeline.retriever, 'search', return_value=[{'record': record, 'rank_score': 1.0}]), \
            mock.patch.object(pipeline.responder, 'answer', return_value=('Suno.', [], False)), \
            mock.patch.object(pipeline, '_eligibility_ready', return_value=False):
        timing.begin()
        pipeline.rag_answer('some scholarship', None)
    snap = timing.snapshot()
    assert snap['retrieve']['count'] == 1
    assert snap['respond']['count'] == 1
