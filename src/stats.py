"""Process-wide quality and cost counters. Thread-safe, dependency-free.

Counters answer: how often do turns come back empty, use context, get their audio cut
or lose audio; how decisive is retrieval (top score and the gap to the runner-up); and
how many Gnani calls have been spent against the credit budget.

One Gnani call is counted per HTTP attempt, so a retry spends a second credit. Both
budgets are hard stops: when either is spent, gnani_call() raises CreditExhausted and
no further provider request is made. The per-client budget stops one visitor from
burning the whole public demo's credits."""
import os
import threading

CREDIT_BUDGET = int(os.getenv('SIDDHA_CREDIT_BUDGET', '5000'))
CLIENT_CREDIT_BUDGET = int(os.getenv('SIDDHA_CLIENT_CREDIT_BUDGET', '250'))


class CreditExhausted(Exception):
    """The Gnani credit budget is spent; the call must not reach the provider."""

    def __init__(self, scope: str):
        self.scope = scope
        super().__init__(f'{scope} credit budget exhausted')


_lock = threading.Lock()
_counters: dict[str, int] = {}
_credits = {'stt': 0, 'tts': 0}
_client_credits: dict[str, int] = {}
_retrieval = {'n': 0, 'top_sum': 0.0, 'margin_sum': 0.0, 'margin_min': None, 'tie_n': 0}

# RRF contributes 1/(60 + rank) to a record's score. One rank position is worth
# 1/61 - 1/62 = 0.000264, so a top-2 margin below that is a dead tie between the
# two retrievers: the order is decided by rounding, not evidence. Rounded up to
# 0.0003. On the 30-query hand set this flags exactly the one exact tie (the
# risk-taking/NUDI query); the smallest nonzero margin among correct top-1
# queries is 0.0006, so the counter does not cry wolf on ordinary results.
TIE_MARGIN = 0.0003


def count(key: str, n: int = 1) -> None:
    with _lock:
        _counters[key] = _counters.get(key, 0) + n


def gnani_call(service: str, client: str = 'anon') -> None:
    """Record one outbound Gnani call ('stt' or 'tts'), or refuse it.

    The check and the increment happen under one lock, so two concurrent turns
    cannot both spend the last credit. Raises CreditExhausted before the caller
    issues the HTTP request."""
    with _lock:
        if sum(_credits.values()) >= CREDIT_BUDGET:
            raise CreditExhausted('global')
        spent = _client_credits.get(client, 0)
        if spent >= CLIENT_CREDIT_BUDGET:
            raise CreditExhausted('client')
        _credits[service] = _credits.get(service, 0) + 1
        _client_credits[client] = spent + 1


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
        clients = len(_client_credits)
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
                          'client_budget': CLIENT_CREDIT_BUDGET, 'clients': clients,
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
        _client_credits.clear()
        _retrieval.update({'n': 0, 'top_sum': 0.0, 'margin_sum': 0.0, 'margin_min': None, 'tie_n': 0})
