from typing import Optional

import redis.asyncio as redis

from src.core.logging import error_logger, service_logger

_redis_master: Optional[redis.Redis] = None
_redis_slave: Optional[redis.Redis] = None


async def init_redis(master_url: str, slave_url: Optional[str] = None) -> tuple[redis.Redis, Optional[redis.Redis]]:
    global _redis_master, _redis_slave
    try:
        _redis_master = redis.from_url(
            master_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=32,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        await _redis_master.ping()
        if slave_url:
            _redis_slave = redis.from_url(
                slave_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=10,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            await _redis_slave.ping()
        else:
            _redis_slave = None
        service_logger.info("Redis clients initialized")
        return _redis_master, _redis_slave
    except Exception as exc:
        error_logger.error(f"Redis initialization failed: {exc}", exc_info=True)
        raise


def get_redis_client(for_write: bool = True) -> Optional[redis.Redis]:
    if for_write:
        return _redis_master
    return _redis_slave if _redis_slave else _redis_master


async def close_redis() -> None:
    global _redis_master, _redis_slave
    if _redis_master:
        await _redis_master.close()
        _redis_master = None
    if _redis_slave:
        await _redis_slave.close()
        _redis_slave = None
    service_logger.info("Redis clients closed")
