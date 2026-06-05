"""Redis-backed token-bucket rate limiter (atomic via Lua)."""

from __future__ import annotations

from typing import Optional

from src.api.middleware.rate_limit.base import RateLimitDecision, RateLimitError, RateLimitKey, RateLimiter
from src.core.logging import setup_logger

logger = setup_logger("api.middleware.rate_limit.redis")


# Lua script: atomic token-bucket consume.
#
# KEYS[1] = bucket key
# ARGV[1] = burst       (bucket capacity, integer)
# ARGV[2] = rate_num    (numerator of refill rate; tokens per window)
# ARGV[3] = rate_den    (denominator of refill rate; window seconds)
# ARGV[4] = now_ms      (current time in milliseconds)
# ARGV[5] = ttl_sec     (key TTL)
#
# Returns: { allowed (1/0), remaining_int, retry_after_sec_int }
_LUA_TOKEN_BUCKET = """
local key = KEYS[1]
local burst = tonumber(ARGV[1])
local rate_num = tonumber(ARGV[2])
local rate_den = tonumber(ARGV[3])
local now_ms = tonumber(ARGV[4])
local ttl_sec = tonumber(ARGV[5])

local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])

if tokens == nil then
  tokens = burst
  ts = now_ms
end

local elapsed_ms = math.max(0, now_ms - ts)
-- refill = elapsed_ms / 1000 * (rate_num / rate_den)
local refill = (elapsed_ms / 1000.0) * (rate_num / rate_den)
tokens = math.min(burst, tokens + refill)

local allowed = 0
local retry_after = 0
if tokens >= 1.0 then
  tokens = tokens - 1.0
  allowed = 1
else
  local deficit = 1.0 - tokens
  local rate_per_sec = rate_num / rate_den
  if rate_per_sec > 0 then
    retry_after = math.ceil(deficit / rate_per_sec)
  else
    retry_after = rate_den
  end
end

redis.call('HSET', key, 'tokens', tokens, 'ts', now_ms)
redis.call('EXPIRE', key, ttl_sec)
return { allowed, math.floor(tokens), retry_after }
"""


class RedisRateLimiter(RateLimiter):
    """Distributed rate limiter using a single Redis instance + Lua.

    Lazily resolves the redis client (so the limiter can be constructed
    before `init_redis()` runs in lifespan startup).
    """

    def __init__(self, *, get_client=None, fail_open: bool = False) -> None:
        # `get_client` lets callers/tests inject a redis client factory.
        # When None, falls back to `src.infrastructure.redis_client.get_redis_client`.
        self._get_client = get_client
        self._script_sha: Optional[str] = None
        self._fail_open = fail_open

    async def _client(self):
        if self._get_client is not None:
            return self._get_client()
        # Lazy import to avoid pulling redis at module load.
        from src.infrastructure.redis_client import get_redis_client

        return get_redis_client(for_write=True)

    async def _ensure_script(self, client) -> str:
        if self._script_sha is None:
            self._script_sha = await client.script_load(_LUA_TOKEN_BUCKET)
        return self._script_sha

    async def setup(self) -> None:
        """启动时验证 Redis 与 Lua 脚本，避免启用限流后静默失效。"""
        client = await self._client()
        if client is None:
            raise RuntimeError("Redis rate limiting requires an initialized Redis client")
        await client.ping()
        await self._ensure_script(client)

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

        client = await self._client()
        if client is None:
            if self._fail_open:
                logger.warning(
                    "rate_limit_redis_unavailable_allow_through",
                    extra={"key": key.redis_key()},
                )
                return RateLimitDecision(allowed=True, remaining=burst, retry_after_sec=0, limit=limit)
            raise RateLimitError("Redis rate limiting backend is unavailable")

        import time as _time

        now_ms = int(_time.time() * 1000)
        ttl_sec = max(window_sec * 2, 60)

        try:
            sha = await self._ensure_script(client)
            result = await client.evalsha(
                sha,
                1,
                key.redis_key(),
                str(burst),
                str(limit),
                str(window_sec),
                str(now_ms),
                str(ttl_sec),
            )
        except Exception:
            # NOSCRIPT or other transient error -> reload & retry once.
            try:
                self._script_sha = await client.script_load(_LUA_TOKEN_BUCKET)
                result = await client.evalsha(
                    self._script_sha,
                    1,
                    key.redis_key(),
                    str(burst),
                    str(limit),
                    str(window_sec),
                    str(now_ms),
                    str(ttl_sec),
                )
            except Exception as e2:  # pragma: no cover
                logger.error(
                    "rate_limit_redis_eval_failed",
                    extra={"key": key.redis_key(), "error": str(e2)},
                    exc_info=True,
                )
                if self._fail_open:
                    return RateLimitDecision(allowed=True, remaining=burst, retry_after_sec=0, limit=limit)
                raise RateLimitError("Redis rate limiting backend failed") from e2

        # result is [allowed, remaining, retry_after]
        try:
            allowed_i = int(result[0])
            remaining_i = int(result[1])
            retry_after_i = int(result[2])
        except (TypeError, ValueError, IndexError) as exc:  # pragma: no cover
            if self._fail_open:
                return RateLimitDecision(allowed=True, remaining=burst, retry_after_sec=0, limit=limit)
            raise RateLimitError("Redis rate limiting backend returned invalid data") from exc

        return RateLimitDecision(
            allowed=bool(allowed_i),
            remaining=max(0, remaining_i),
            retry_after_sec=max(0, retry_after_i),
            limit=limit,
        )
