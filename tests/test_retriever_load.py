"""The retriever loads its 2 GB model exactly once, even under a cold-start race."""
import threading
import time

from fastapi.testclient import TestClient


def test_concurrent_first_queries_share_one_load(monkeypatch):
    import retriever

    calls = []
    gate = threading.Barrier(8)

    def slow_read():
        calls.append(1)
        time.sleep(0.05)          # widen the window in which a second loader could start
        return ('recs', 'docs', 'model', 'index', 'bm25')

    monkeypatch.setattr(retriever, '_read_all', slow_read)
    monkeypatch.setattr(retriever, '_cache', None)
    results = []

    def load():
        gate.wait()
        results.append(retriever._load())

    threads = [threading.Thread(target=load) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1, 'the model must not be built once per racing request'
    assert len(results) == 8
    assert all(r is results[0] for r in results)


def test_is_loaded_tracks_the_cache_and_warm_up_fills_it(monkeypatch):
    import retriever

    monkeypatch.setattr(retriever, '_read_all', lambda: ('recs', 'docs', 'model', 'index', 'bm25'))
    monkeypatch.setattr(retriever, '_cache', None)
    assert retriever.is_loaded() is False
    retriever.warm_up()
    assert retriever.is_loaded() is True


def test_the_server_warms_up_on_startup(monkeypatch):
    import server

    called = threading.Event()
    monkeypatch.setattr(server.retriever, 'warm_up', lambda: called.set())
    with TestClient(server.app):
        pass
    assert called.wait(2), 'the lifespan must start the warm-up thread'
