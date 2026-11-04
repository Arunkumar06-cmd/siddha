"""Shared test fixtures: make src importable; reset the rate-limiter bucket between tests."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / 'src'))


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    """Each test starts with a clean per-IP bucket so rate-limit state never leaks."""
    try:
        import server
        server._ip_calls.clear()
    except ImportError:
        pass
    yield
