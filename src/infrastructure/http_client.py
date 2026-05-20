import asyncio
from typing import Any

import httpx

from src.core.logging import error_logger, get_rid, log_event, service_logger

_http_client: httpx.AsyncClient | None = None
_client_lock = asyncio.Lock()


async def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        async with _client_lock:
            if _http_client is None:
                _http_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(timeout=30.0, connect=10.0, read=20.0, write=10.0),
                    limits=httpx.Limits(max_keepalive_connections=20, max_connections=100, keepalive_expiry=30.0),
                    follow_redirects=True,
                    verify=True,
                )
                service_logger.info("Global HTTP client initialized")
    return _http_client


async def close_http_client() -> None:
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None
        service_logger.info("Global HTTP client closed")


async def http_get(url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> httpx.Response:
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
