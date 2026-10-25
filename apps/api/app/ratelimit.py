"""In-memory sliding-window rate limits for /ask.

A public deployment shares one free-tier AI key between all visitors, so without limits one
person (or a bot) could use up the whole day's quota. Limits live in memory: they reset when the
server restarts and are per instance, which is fine for a single small server.
"""

import time
from collections import deque
from collections.abc import Callable
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from app.config import get_settings

MINUTE = 60.0
DAY = 24 * 60 * 60.0


class RateLimiter:
    def __init__(
        self,
        per_minute: int,
        per_day: int,
        global_per_minute: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        # (key prefix, window seconds, max hits); a max of 0 disables that limit.
        self._rules = [
            ("ip-min", MINUTE, per_minute),
            ("ip-day", DAY, per_day),
            ("all-min", MINUTE, global_per_minute),
        ]
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def check(self, visitor: str) -> float | None:
        """Record a request. Returns None if allowed, else seconds until it would be."""
        now = self._clock()
        keys = []
        for prefix, window, limit in self._rules:
            if limit <= 0:
                continue
            key = f"{prefix}:all" if prefix.startswith("all") else f"{prefix}:{visitor}"
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - window:
                hits.popleft()
            if len(hits) >= limit:
                return hits[0] + window - now
            keys.append(key)
        # Only count the request once every limit has allowed it.
        for key in keys:
            self._hits[key].append(now)
        return None


@lru_cache
def get_limiter() -> RateLimiter:
    s = get_settings()
    return RateLimiter(
        s.rate_limit_per_minute, s.rate_limit_per_day, s.global_rate_limit_per_minute
    )


def visitor_id(request: Request) -> str:
    # Behind a host's proxy (Hugging Face, Render, ...) the client address is the proxy's, and the
    # real one is the last entry the proxy appended to X-Forwarded-For.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request, limiter: Annotated[RateLimiter, Depends(get_limiter)]) -> None:
    wait = limiter.check(visitor_id(request))
    if wait is not None:
        seconds = max(1, round(wait))
        raise HTTPException(
            status_code=429,
            detail=f"Too many questions right now. Please try again in {seconds} seconds.",
            headers={"Retry-After": str(seconds)},
        )
