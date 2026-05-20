"""Single-process token-bucket rate limiter (degraded mode)."""

from __future__ import annotations

import asyncio
import time
from typing import Dict, Tuple

from src.api.middleware.rate_limit.base import RateLimitDecision, RateLimitKey, RateLimiter


class MemoryRateLimiter(RateLimiter):
    """asyncio-safe in-process token bucket.

    Suitable for single-instance deployments or as a degraded fallback when
    Redis is unavailable. Counters are never persisted.
    """

    def __init__(self) -> None:
        # bucket key -> (tokens, last_refill_ts)
        self._state: Dict[str, Tuple[float, float]] = {}
        self._lock = asyncio.Lock()

    async def check(
        self,
        key: RateLimitKey,
        *,
        limit: int,
        window_sec: int,
        burst: int,
    ) -> RateLimitDecision:
        if window_sec <= 0:
            window_sec = 1
        if burst <= 0:
            burst = limit
        rate_per_sec = limit / window_sec
        bucket_id = key.redis_key()

        async with self._lock:
            now = time.monotonic()
            tokens, last = self._state.get(bucket_id, (float(burst), now))
            elapsed = max(0.0, now - last)
            tokens = min(float(burst), tokens + elapsed * rate_per_sec)

            if tokens >= 1.0:
                tokens -= 1.0
                self._state[bucket_id] = (tokens, now)
                return RateLimitDecision(
                    allowed=True,
                    remaining=int(tokens),
                    retry_after_sec=0,
                    limit=limit,
                )

            # Not enough tokens. Compute the time needed to recover 1 token.
            deficit = 1.0 - tokens
            retry_after = int(deficit / rate_per_sec) + 1 if rate_per_sec > 0 else window_sec
            self._state[bucket_id] = (tokens, now)
            return RateLimitDecision(
                allowed=False,
                remaining=0,
                retry_after_sec=retry_after,
                limit=limit,
            )

    def reset(self) -> None:
        """Test-only helper."""
        self._state.clear()
