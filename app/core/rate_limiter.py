import functools
import inspect
from typing import Any, Callable

import redis.asyncio as redis

from app.core.logging import error_logger, service_logger


class RateLimiter:
    def __init__(self, redis_master: redis.Redis, redis_slave: redis.Redis | None = None):
        self.redis_master = redis_master
        self.redis_slave = redis_slave if redis_slave else redis_master

    async def check_and_set(self, key: str, ttl_seconds: int = 30, prefix: str = "rate_limit") -> tuple[bool, int | None]:
        if not self.redis_master:
            return True, None
        full_key = f"{prefix}:{key}"
        try:
            is_set = await self.redis_master.set(full_key, "1", nx=True, ex=ttl_seconds)
            if is_set:
                return True, None
            ttl = await self.redis_slave.ttl(full_key)
            return False, max(ttl, 0)
        except Exception as exc:
            error_logger.error(f"Rate limiter Redis error: {exc}", exc_info=True)
            return True, None


def rate_limit(key_param: str, ttl_seconds: int = 30, prefix: str = "rate_limit", rate_limiter_attr: str = "_rate_limiter"):
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            self_instance = args[0] if args else None
            key_params = [param.strip() for param in key_param.split(",")]
            sig = inspect.signature(func)
            params = list(sig.parameters.keys())
            key_values: list[str] = []
            for param in key_params:
                param_value = kwargs.get(param)
                if not param_value and param in params:
                    idx = params.index(param)
                    if idx < len(args):
                        param_value = args[idx]
                if not param_value:
                    service_logger.warning(f"Missing rate-limit param: {param}")
                    return await func(*args, **kwargs)
                key_values.append(str(param_value))
            limiter: RateLimiter | None = getattr(self_instance, rate_limiter_attr, None) if self_instance else None
            if not limiter:
                return await func(*args, **kwargs)
            allowed, remaining = await limiter.check_and_set(
                key="_".join(key_values),
                ttl_seconds=ttl_seconds,
                prefix=prefix,
            )
            if not allowed:
                return {"success": False, "rate_limited": True, "remaining_seconds": remaining}
            return await func(*args, **kwargs)

        return wrapper

    return decorator
