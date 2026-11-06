"""Shared test fixtures: make src importable; reset the rate-limiter bucket between tests."""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).parent.parent
# src/ for the modules, the repo root for server.py: a bare `pytest` (not `python -m pytest`)
# does not put the root on sys.path.
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    """Each test starts with a clean per-IP bucket so rate-limit state never leaks."""
    try:
        import server
        server._ip_calls.clear()
    except ImportError:
        pass
    yield
