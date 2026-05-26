"""按需初始化的共享 HTTP 客户端。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from src.core.logging import error_logger, get_rid, log_event, service_logger


@dataclass(frozen=True)
class HttpClientConfig:
    enabled: bool = True
    timeout_seconds: float = 30.0
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 20.0
    write_timeout_seconds: float = 10.0
    max_connections: int = 100
    max_keepalive_connections: int = 20
    keepalive_expiry_seconds: float = 30.0
    follow_redirects: bool = True
    verify_tls: bool = True

    @classmethod
    def from_settings(cls, settings: Any) -> "HttpClientConfig":
        return cls(
            enabled=bool(getattr(settings, "http_client_enabled", True)),
            timeout_seconds=float(getattr(settings, "http_timeout_seconds", 30.0)),
            connect_timeout_seconds=float(
                getattr(settings, "http_connect_timeout_seconds", 10.0)
            ),
            read_timeout_seconds=float(getattr(settings, "http_read_timeout_seconds", 20.0)),
            write_timeout_seconds=float(
                getattr(settings, "http_write_timeout_seconds", 10.0)
            ),
            max_connections=int(getattr(settings, "http_max_connections", 100)),
            max_keepalive_connections=int(
                getattr(settings, "http_max_keepalive_connections", 20)
            ),
            keepalive_expiry_seconds=float(
                getattr(settings, "http_keepalive_expiry_seconds", 30.0)
            ),
            follow_redirects=bool(getattr(settings, "http_follow_redirects", True)),
            verify_tls=bool(getattr(settings, "http_verify_tls", True)),
        )


_http_client: httpx.AsyncClient | None = None
_http_config = HttpClientConfig()
_client_lock = asyncio.Lock()


def configure_http_client(settings: Any) -> None:
    """设置懒加载客户端参数；已创建客户端时不允许热切换。"""
    global _http_config
    if _http_client is not None:
        raise RuntimeError("HTTP client is already initialized")
    _http_config = HttpClientConfig.from_settings(settings)


async def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if not _http_config.enabled:
        raise RuntimeError("HTTP client is disabled")
    if _http_client is None:
        async with _client_lock:
            if _http_client is None:
                _http_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(
                        timeout=_http_config.timeout_seconds,
                        connect=_http_config.connect_timeout_seconds,
                        read=_http_config.read_timeout_seconds,
                        write=_http_config.write_timeout_seconds,
                    ),
                    limits=httpx.Limits(
                        max_keepalive_connections=_http_config.max_keepalive_connections,
                        max_connections=_http_config.max_connections,
                        keepalive_expiry=_http_config.keepalive_expiry_seconds,
                    ),
                    follow_redirects=_http_config.follow_redirects,
                    verify=_http_config.verify_tls,
                )
                service_logger.info("Global HTTP client initialized")
    return _http_client


async def close_http_client() -> None:
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None
        service_logger.info("Global HTTP client closed")


async def http_get(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    client = await get_http_client()
    request_headers = dict(headers or {})
    if get_rid() and "X-Request-ID" not in request_headers:
        request_headers["X-Request-ID"] = get_rid() or ""
    try:
        log_event(service_logger, "http_client.get.start", url=url)
        response = await client.get(url, params=params, headers=request_headers)
        response.raise_for_status()
        log_event(service_logger, "http_client.get.end", url=url, status_code=response.status_code)
        return response
    except httpx.HTTPError as exc:
        error_logger.error(f"HTTP GET failed: url={url}, error={exc}")
        raise


async def http_post(
    url: str,
    data: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    client = await get_http_client()
    request_headers = dict(headers or {})
    if get_rid() and "X-Request-ID" not in request_headers:
        request_headers["X-Request-ID"] = get_rid() or ""
    try:
        log_event(service_logger, "http_client.post.start", url=url)
        response = await client.post(url, data=data, json=json, headers=request_headers)
        response.raise_for_status()
        log_event(service_logger, "http_client.post.end", url=url, status_code=response.status_code)
        return response
    except httpx.HTTPError as exc:
        error_logger.error(f"HTTP POST failed: url={url}, error={exc}")
        raise
