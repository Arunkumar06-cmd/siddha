"""Per-stage latency: one dict per request, plus process-wide count/sum/max per stage.

A request's timings live in a contextvar holding a mutable dict, so stages that run
in the worker thread (FastAPI copies the context into it) write to the same dict the
middleware reads back after the response, for the Server-Timing header.

No dependencies on purpose, like reqid.py: it can be tested without FastAPI."""
import contextlib
import contextvars
import threading
import time

STAGES = ('ffmpeg', 'stt', 'retrieve', 'respond', 'tts')

_current: contextvars.ContextVar[dict | None] = contextvars.ContextVar('siddha_timings', default=None)
_lock = threading.Lock()
_agg: dict[str, dict] = {}


def begin() -> dict:
    """Start collecting for this request; returns the dict the middleware keeps."""
    timings: dict[str, float] = {}
    _current.set(timings)
    return timings


def _record(name: str, seconds: float) -> None:
    timings = _current.get()
    if timings is not None:
        timings[name] = timings.get(name, 0.0) + seconds
    with _lock:
        a = _agg.setdefault(name, {'count': 0, 'sum': 0.0, 'max': 0.0})
        a['count'] += 1
        a['sum'] += seconds
        a['max'] = max(a['max'], seconds)


@contextlib.contextmanager
def stage(name: str):
    """Time a block. Recorded on failure too: a slow error is still latency."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        _record(name, time.perf_counter() - t0)


def record(name: str, seconds: float) -> None:
    _record(name, seconds)


def server_timing(timings: dict | None) -> str:
    """Server-Timing header value, durations in milliseconds, e.g. 'stt;dur=412.3'."""
    if not timings:
        return ''
    return ', '.join(f'{k};dur={v * 1000:.1f}' for k, v in timings.items())


def snapshot() -> dict:
    """count / sum_s / max_s per stage, for /api/metrics."""
    with _lock:
        return {k: {'count': v['count'], 'sum_s': round(v['sum'], 4), 'max_s': round(v['max'], 4)}
                for k, v in sorted(_agg.items())}


def prometheus() -> str:
    """Prometheus text exposition (summary-style count/sum plus a max gauge)."""
    lines = [
        '# HELP siddha_stage_seconds Time spent per pipeline stage.',
        '# TYPE siddha_stage_seconds summary',
    ]
    snap = snapshot()
    for name, v in snap.items():
        lines.append(f'siddha_stage_seconds_count{{stage="{name}"}} {v["count"]}')
        lines.append(f'siddha_stage_seconds_sum{{stage="{name}"}} {v["sum_s"]}')
    lines += ['# HELP siddha_stage_seconds_max Slowest observed call per stage.',
              '# TYPE siddha_stage_seconds_max gauge']
    for name, v in snap.items():
        lines.append(f'siddha_stage_seconds_max{{stage="{name}"}} {v["max_s"]}')
    return '\n'.join(lines) + '\n'


def reset() -> None:
    """Test helper."""
    with _lock:
        _agg.clear()
