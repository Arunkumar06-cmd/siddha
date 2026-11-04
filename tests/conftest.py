import sys, pathlib, builtins, typing
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / 'src'))

import pytest

@pytest.fixture(autouse=True)
def _reset_rate_limit(monkeypatch):
    # each test starts with a clean per-IP bucket
    try:
        import server
        server._ip_calls.clear()
    except Exception:
        pass
    yield
