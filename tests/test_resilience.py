"""Circuit breaker and retry semantics."""
import time

import pytest
import requests

from resilience import CircuitBreaker, retry

COOLDOWN = 0.05


def _tripped(threshold=3):
    b = CircuitBreaker('t', threshold=threshold, cooldown_s=COOLDOWN)
    for _ in range(threshold):
        assert b.allow()
        b.record_failure()
    return b


def test_opens_after_threshold_consecutive_failures():
    b = _tripped()
    assert b.state() == 'open'
    assert not b.allow()


def test_a_success_resets_the_failure_count():
    b = CircuitBreaker('t', threshold=3, cooldown_s=COOLDOWN)
    for _ in range(2):
        b.record_failure()
    b.record_success()
    for _ in range(2):
        b.record_failure()
    assert b.state() == 'closed'


def test_half_open_admits_exactly_one_probe():
    b = _tripped()
    time.sleep(COOLDOWN * 1.5)
    assert b.state() == 'half_open'
    assert b.allow(), 'the first caller after cooldown is the probe'
    assert not b.allow(), 'everyone else keeps waiting; traffic must not flood back'


def test_a_successful_probe_closes_the_circuit():
    b = _tripped()
    time.sleep(COOLDOWN * 1.5)
    assert b.allow()
    b.record_success()
    assert b.state() == 'closed'
    assert b.allow() and b.allow()


def test_a_failed_probe_reopens_for_a_full_cooldown():
    b = _tripped()
    time.sleep(COOLDOWN * 1.5)
    assert b.allow()
    b.record_failure()
    assert b.state() == 'open'
    assert not b.allow()


def test_retry_repeats_a_retryable_error_and_returns_the_second_result():
    calls = []

    def call():
        calls.append(1)
        if len(calls) == 1:
            raise requests.Timeout('slow')
        return 'ok'

    assert retry(call, attempts=2, base_delay=0, retryable=lambda e: isinstance(e, requests.Timeout)) == 'ok'
    assert len(calls) == 2


def test_retry_does_not_repeat_a_non_retryable_error():
    calls = []

    def call():
        calls.append(1)
        raise ValueError('bad input')

    with pytest.raises(ValueError):
        retry(call, attempts=3, base_delay=0, retryable=lambda e: isinstance(e, requests.Timeout))
    assert len(calls) == 1
