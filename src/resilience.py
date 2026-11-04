"""Resilience primitives: retry with backoff+jitter, circuit breaker.
Deterministic, stdlib-only, thread-safe."""
import random
import threading
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar('T')

class CircuitOpen(Exception):
    pass

class CircuitBreaker:
    def __init__(self, name: str, threshold: int = 5, cooldown_s: float = 60.0):
        self.name = name
        self.threshold = threshold
        self.cooldown = cooldown_s
        self._fails = 0
        self._opened_at = 0.0
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            if self._fails >= self.threshold:
                if time.time() - self._opened_at >= self.cooldown:
                    self._fails = 0
                    self._opened_at = 0.0
                    return True
                return False
            return True

    def record_success(self):
        with self._lock:
            self._fails = 0
            self._opened_at = 0.0

    def record_failure(self):
        with self._lock:
            self._fails += 1
            if self._fails == self.threshold:
                self._opened_at = time.time()

    def state(self) -> str:
        with self._lock:
            if self._fails >= self.threshold and time.time() - self._opened_at < self.cooldown:
                return 'open'
            return 'closed'


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
