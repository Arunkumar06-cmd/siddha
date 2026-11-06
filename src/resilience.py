"""Resilience primitives: retry with backoff+jitter, circuit breaker.
Deterministic, stdlib-only, thread-safe."""
import logging
import random
import threading
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar('T')
_log = logging.getLogger('siddha')


class CircuitOpen(Exception):
    pass


class CircuitBreaker:
    """closed -> open (after `threshold` consecutive failures) -> half-open.

    Half-open admits exactly one probe request once `cooldown_s` has elapsed.
    A probe that succeeds closes the circuit; a probe that fails re-opens it for
    another full cooldown. Callers must report every admitted request with
    record_success() or record_failure(), otherwise the probe slot stays held.
    Only provider-health failures (timeouts, connection errors, 5xx) count as
    failures; a 4xx means the provider answered, so callers record a success.
    """

    def __init__(self, name: str, threshold: int = 5, cooldown_s: float = 60.0):
        self.name = name
        self.threshold = threshold
        self.cooldown = cooldown_s
        self._fails = 0
        self._opened_at = 0.0
        self._probing = False
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            if self._fails < self.threshold:
                return True
            if time.time() - self._opened_at < self.cooldown:
                return False
            if self._probing:
                return False
            self._probing = True
            _log.info('circuit_half_open name=%s', self.name)
            return True

    def record_success(self):
        with self._lock:
            if self._fails >= self.threshold:
                _log.info('circuit_closed name=%s', self.name)
            self._fails = 0
            self._opened_at = 0.0
            self._probing = False

    def record_failure(self):
        with self._lock:
            self._fails += 1
            if self._probing:
                self._probing = False
                self._opened_at = time.time()
                _log.warning('circuit_reopened name=%s', self.name)
            elif self._fails == self.threshold:
                self._opened_at = time.time()
                _log.warning('circuit_opened name=%s failures=%d cooldown_s=%s',
                             self.name, self._fails, self.cooldown)

    def state(self) -> str:
        with self._lock:
            if self._fails < self.threshold:
                return 'closed'
            if time.time() - self._opened_at < self.cooldown:
                return 'open'
            return 'half_open'


def retry(call: Callable[[], T], *, attempts: int = 2, base_delay: float = 0.4,
          retryable: Callable[[Exception], bool] | None = None) -> T:
    """Retry idempotent external calls with exponential backoff + jitter."""
    last = None
    for i in range(attempts):
        try:
            return call()
        except Exception as e:
            last = e
            if retryable and not retryable(e):
                raise
            if i + 1 < attempts:
                time.sleep(base_delay * (2 ** i) + random.uniform(0, 0.15))  # noqa: S311 - jitter, not cryptography
    raise last
