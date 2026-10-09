from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int = 0


class SessionRateLimiter:
    """Small in-memory limiter for the single-worker public demo profile."""

    def __init__(self, max_sessions: int = 10_000) -> None:
        self._events: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._totals: dict[tuple[str, str], int] = defaultdict(int)
        self._last_seen: dict[tuple[str, str], float] = {}
        self._max_sessions = max_sessions
        self._lock = Lock()

    def check(
        self,
        session_id: str,
        bucket: str,
        limit: int,
        window_seconds: int = 60,
        total_limit: int | None = None,
    ) -> RateLimitDecision:
        now = time.monotonic()
        key = (session_id, bucket)
        with self._lock:
            events = self._events[key]
            cutoff = now - window_seconds
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                return RateLimitDecision(False, max(1, int(events[0] + window_seconds - now) + 1))
            if total_limit is not None and self._totals[key] >= total_limit:
                return RateLimitDecision(False, window_seconds)
            events.append(now)
            self._totals[key] += 1
            self._last_seen[key] = now
            if len(self._last_seen) > self._max_sessions:
                oldest = min(self._last_seen, key=self._last_seen.get)
                self._last_seen.pop(oldest, None)
                self._events.pop(oldest, None)
                self._totals.pop(oldest, None)
        return RateLimitDecision(True)
