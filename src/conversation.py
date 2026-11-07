"""Session-scoped conversation memory.

Text only: the last few queries, the grounded reply, and the scheme record the
answer was built from. No audio is stored. A session expires after 30 minutes
of inactivity and the store is capped so a public demo cannot grow unbounded.

This is deliberately not a free-form chat history: the answer path only needs
the previous scheme and its aspects to resolve a follow-up.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

TTL_SECONDS = 30 * 60
MAX_SESSIONS = 500
MAX_TURNS = 8


@dataclass
class Turn:
    query: str
    reply: str
    scheme: dict | None
    sources: list[dict] = field(default_factory=list)
    aspects: tuple[str, ...] = ()
    context_used: bool = False
    context_name: str | None = None
    at: float = field(default_factory=time.time)


@dataclass
class Conversation:
    turns: list[Turn] = field(default_factory=list)
    touched: float = field(default_factory=time.time)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False, compare=False)

    @property
    def last(self) -> Turn | None:
        with self._lock:
            return self.turns[-1] if self.turns else None

    def add(self, turn: Turn) -> None:
        with self._lock:
            self.turns.append(turn)
            del self.turns[:-MAX_TURNS]
            self.touched = time.time()

    def snapshot_last(self) -> Turn | None:
        with self._lock:
            return self.turns[-1] if self.turns else None


class ConversationStore:
    def __init__(self, ttl: int = TTL_SECONDS, max_sessions: int = MAX_SESSIONS):
        self._ttl = ttl
        self._max_sessions = max_sessions
        self._data: dict[str, Conversation] = {}
        self._lock = threading.Lock()

    def _touched(self, conv: Conversation) -> float:
        # Read under the conversation lock when available; safe for pruning decisions.
        lock = getattr(conv, '_lock', None)
        if lock is not None:
            with lock:
                return conv.touched
        return conv.touched

    def _prune(self, now: float) -> None:
        expired = [sid for sid, c in self._data.items() if now - self._touched(c) > self._ttl]
        for sid in expired:
            del self._data[sid]
        if len(self._data) > self._max_sessions:
            oldest = sorted(self._data, key=lambda sid: self._touched(self._data[sid]))
            for sid in oldest[: len(self._data) - self._max_sessions]:
                del self._data[sid]

    def _get_or_create(self, session_id: str, now: float) -> Conversation:
        self._prune(now)
        conv = self._data.get(session_id)
        if conv is None:
            conv = Conversation()
            self._data[session_id] = conv
        return conv

    def get(self, session_id: str) -> Conversation:
        """Return the live conversation (back-compat). Callers must not mutate it
        outside store methods; prefer `record`/`last`/`reset`."""
        with self._lock:
            return self._get_or_create(session_id, time.time())

    def last(self, session_id: str | None) -> Turn | None:
        if not session_id:
            return None
        with self._lock:
            self._prune(time.time())
            conv = self._data.get(session_id)
            if not conv:
                return None
            return conv.snapshot_last()

    def record(self, session_id: str | None, turn: Turn) -> None:
        if not session_id:
            return
        with self._lock:
            conv = self._get_or_create(session_id, time.time())
            conv.add(turn)

    def reset(self, session_id: str | None) -> None:
        if not session_id:
            return
        with self._lock:
            self._data.pop(session_id, None)


STORE = ConversationStore()
