"""Simple in-memory per-user rate limiting."""

from __future__ import annotations

import time
from collections import defaultdict, deque

import config


class RateLimiter:
    """Sliding-window rate limiter keyed by Telegram user ID."""

    def __init__(
        self,
        max_requests: int = config.RATE_LIMIT_MAX_REQUESTS,
        window_seconds: float = config.RATE_LIMIT_WINDOW_SECONDS,
    ) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._events: dict[int, deque[float]] = defaultdict(deque)

    def is_allowed(self, user_id: int) -> bool:
        now = time.monotonic()
        window_start = now - self._window_seconds
        events = self._events[user_id]
        while events and events[0] < window_start:
            events.popleft()
        if len(events) >= self._max_requests:
            return False
        events.append(now)
        return True

    def clear(self, user_id: int) -> None:
        self._events.pop(user_id, None)


rate_limiter = RateLimiter()
