"""Rate limit abstractions: RateLimitKey, RateLimitDecision, RateLimiter."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitKey:
    """Identifies a single bucket (per dimension+value+route)."""

    dim: str    # "user" / "ip" / "anonymous"
    value: str  # principal.user_id or client IP
    route: str  # request path used as bucket scope

    def redis_key(self) -> str:
        # rl:{route}:{dim}:{value}
        return f"rl:{self.route}:{self.dim}:{self.value}"


@dataclass
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after_sec: int
    limit: int


class RateLimitError(Exception):
    """Raised when an unrecoverable backend error happens (rare)."""


class RateLimiter(ABC):
    """Token-bucket-style rate limiter.

    `limit` tokens refill within `window_sec`; `burst` is the bucket capacity
    (total tokens that can be held at once). When called, the limiter
    consumes one token and returns the decision.
    """

    @abstractmethod
    async def check(
        self,
        key: RateLimitKey,
        *,
        limit: int,
        window_sec: int,
        burst: int,
    ) -> RateLimitDecision:
        ...

    async def setup(self) -> None:
        return None

    async def teardown(self) -> None:
        return None
