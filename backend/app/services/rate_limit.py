"""In-process sliding-window rate limiter for the send path.

Deliberately simple and per-process: it is a guard rail for the demo, and the
place a Redis token bucket would slot in for a multi-node deployment.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from app.core.config import settings


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        cutoff = now - self.window
        while hits and hits[0] < cutoff:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)


message_limiter = SlidingWindowLimiter(
    settings.rate_limit_messages, settings.rate_limit_window_seconds
)
