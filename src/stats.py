"""Process-wide quality and cost counters. Thread-safe, dependency-free.

Counters answer: how often do turns come back empty, use context, get their audio cut
or lose audio; how decisive is retrieval (top score and the gap to the runner-up); and
how many Gnani calls have been spent against the credit budget.

One Gnani call is counted per HTTP attempt, so a retry spends a second credit."""
import os
import threading

CREDIT_BUDGET = int(os.getenv('SIDDHA_CREDIT_BUDGET', '5000'))

_lock = threading.Lock()
_counters: dict[str, int] = {}
_credits = {'stt': 0, 'tts': 0}
_retrieval = {'n': 0, 'top_sum': 0.0, 'margin_sum': 0.0, 'margin_min': None, 'tie_n': 0}

# Margin (top score minus runner-up) below which the top hit is treated as a coin flip.
# Placeholder until item 7 derives the threshold from the eval set.
TIE_MARGIN = 0.0010


def count(key: str, n: int = 1) -> None:
    with _lock:
        _counters[key] = _counters.get(key, 0) + n


def gnani_call(service: str) -> None:
    """Record one outbound Gnani call ('stt' or 'tts')."""
    with _lock:
        _credits[service] = _credits.get(service, 0) + 1


def credits_used() -> int:
    with _lock:
        return sum(_credits.values())


def observe_retrieval(hits) -> None:
    """Record the top score and its margin over the runner-up for one retrieval."""
    if not hits:
        count('retrieval_empty')
        return
    top = float(hits[0].get('rank_score', 0.0))
    margin = top - float(hits[1].get('rank_score', 0.0)) if len(hits) > 1 else top
    with _lock:
        r = _retrieval
        r['n'] += 1
        r['top_sum'] += top
        r['margin_sum'] += margin
        r['margin_min'] = margin if r['margin_min'] is None else min(r['margin_min'], margin)
        if margin < TIE_MARGIN:
            r['tie_n'] += 1


def _rate(counters: dict, key: str, base: str):
    denom = counters.get(base, 0)
    return round(counters.get(key, 0) / denom, 4) if denom else None


def snapshot() -> dict:
    with _lock:
        c = dict(_counters)
        credits = dict(_credits)
        r = dict(_retrieval)
    used = sum(credits.values())
    return {
        'counters': c,
        'rates': {
            'empty_transcript': _rate(c, 'empty_transcript', 'audio_turns'),
            'context_used': _rate(c, 'context_used', 'turns'),
            'audio_truncated': _rate(c, 'audio_truncated', 'audio_returned'),
            'tts_degraded': _rate(c, 'tts_degraded', 'tts_attempted'),
        },
        'retrieval': {
            'count': r['n'],
            'mean_top_score': round(r['top_sum'] / r['n'], 5) if r['n'] else None,
            'mean_margin': round(r['margin_sum'] / r['n'], 5) if r['n'] else None,
            'min_margin': round(r['margin_min'], 5) if r['margin_min'] is not None else None,
            'near_ties': r['tie_n'],
            'tie_margin': TIE_MARGIN,
        },
        'gnani_credits': {**credits, 'used': used, 'budget': CREDIT_BUDGET,
                          'remaining': max(CREDIT_BUDGET - used, 0)},
    }


def prometheus() -> str:
    s = snapshot()
    lines = ['# TYPE siddha_quality_total counter']
    lines += [f'siddha_quality_total{{event="{k}"}} {v}' for k, v in sorted(s['counters'].items())]
    lines += ['# TYPE siddha_gnani_calls_total counter']
    lines += [f'siddha_gnani_calls_total{{service="{k}"}} {s["gnani_credits"][k]}' for k in ('stt', 'tts')]
    lines += ['# TYPE siddha_gnani_credits_remaining gauge',
              f'siddha_gnani_credits_remaining {s["gnani_credits"]["remaining"]}',
              '# TYPE siddha_retrieval_near_ties_total counter',
              f'siddha_retrieval_near_ties_total {s["retrieval"]["near_ties"]}']
    return '\n'.join(lines) + '\n'


def reset() -> None:
    """Test helper."""
    with _lock:
        _counters.clear()
        _credits.update({'stt': 0, 'tts': 0})
        _retrieval.update({'n': 0, 'top_sum': 0.0, 'margin_sum': 0.0, 'margin_min': None, 'tie_n': 0})
