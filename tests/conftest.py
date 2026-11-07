"""Shared test fixtures: make src importable; give every test a clean slate of shared state."""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).parent.parent
# src/ for the modules, the repo root for server.py: a bare `pytest` (not `python -m pytest`)
# does not put the root on sys.path.
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT))


def _reset_shared_state():
    """Module-level singletons that one test can leave dirty for the next.

    The rate-limit table, the STT/TTS circuit breakers and the in-memory conversation store
    are process-wide. Without this, a test that opens a breaker or fills a session changes
    what a later, unrelated test sees, and failures depend on test order."""
    try:
        import server
        server._ip_calls.clear()
    except ImportError:
        pass
    try:
        import pipeline
        pipeline.STT_BREAKER.record_success()
        pipeline.TTS_BREAKER.record_success()
    except ImportError:
        pass
    try:
        import conversation
        with conversation.STORE._lock:
            conversation.STORE._data.clear()
    except ImportError:
        pass


@pytest.fixture(autouse=True)
def _clean_shared_state():
    _reset_shared_state()
    yield
    _reset_shared_state()
