"""RateLimitPlugin: install token-bucket rate limiting as HTTP middleware."""

from __future__ import annotations

import json
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.api.middleware.rate_limit.base import RateLimitDecision, RateLimitKey, RateLimiter
from src.api.middleware.rate_limit.memory_backend import MemoryRateLimiter
from src.api.middleware.rate_limit.redis_backend import RedisRateLimiter
from src.core.logging import setup_logger

logger = setup_logger("api.middleware.rate_limit")

_DEFAULT_SKIP_PATHS = ("/health", "/docs", "/redoc", "/openapi.json", "/ui")


class RateLimitPlugin:
    """Protocol-layer rate limiting plugin.

    name: "rate_limit"
    """

    name = "rate_limit"

    def __init__(
        self,
        *,
        enabled: bool = False,
        backend: Optional[RateLimiter] = None,
        default_limit: int = 60,
        default_window_sec: int = 60,
        default_burst: int = 10,
        key_strategy: str = "principal",
        fail_open: bool = False,
        route_overrides: Optional[dict[str, dict[str, int]]] = None,
        skip_paths: Optional[list[str]] = None,
    ) -> None:
        self._enabled = enabled
        self._backend: RateLimiter = backend or MemoryRateLimiter()
        self._default_limit = default_limit
        self._default_window_sec = default_window_sec
        self._default_burst = default_burst
        self._key_strategy = key_strategy
        self._fail_open = fail_open
        self._route_overrides = route_overrides or {}
        self._skip_paths = tuple(skip_paths) if skip_paths else _DEFAULT_SKIP_PATHS

    @classmethod
    def from_settings(cls, settings) -> "RateLimitPlugin":
        enabled = bool(getattr(settings, "rate_limit_enabled", False))
        if not enabled:
            return cls(enabled=False)

        backend_name = (getattr(settings, "rate_limit_backend", "redis") or "redis").lower()
        if backend_name == "memory":
            backend: RateLimiter = MemoryRateLimiter()
        else:
            if not bool(getattr(settings, "redis_enabled", False)):
                raise ValueError("RATE_LIMIT_BACKEND=redis requires REDIS_ENABLED=true")
            backend = RedisRateLimiter(fail_open=bool(getattr(settings, "rate_limit_fail_open", False)))

        # `rate_limit_routes` is stored as a JSON string for env-var friendliness.
        raw_routes = getattr(settings, "rate_limit_routes", "") or ""
        route_overrides: dict[str, dict[str, int]] = {}
        if isinstance(raw_routes, str) and raw_routes.strip():
            try:
                parsed = json.loads(raw_routes)
                if isinstance(parsed, dict):
                    for path, cfg in parsed.items():
                        if isinstance(cfg, dict):
                            route_overrides[path] = {
                                "limit": int(cfg.get("limit", 0)) or None,  # type: ignore[assignment]
                                "window_sec": int(cfg.get("window_sec", cfg.get("window", 0))) or None,  # type: ignore[assignment]
                                "burst": int(cfg.get("burst", 0)) or None,  # type: ignore[assignment]
                            }
            except Exception as e:
                logger.warning("rate_limit_routes_parse_failed", extra={"error": str(e)})
        elif isinstance(raw_routes, dict):
            for path, cfg in raw_routes.items():
                if isinstance(cfg, dict):
                    route_overrides[path] = {
                        "limit": int(cfg.get("limit", 0)) or None,  # type: ignore[assignment]
                        "window_sec": int(cfg.get("window_sec", cfg.get("window", 0))) or None,  # type: ignore[assignment]
                        "burst": int(cfg.get("burst", 0)) or None,  # type: ignore[assignment]
                    }

        return cls(
            enabled=True,
            backend=backend,
            default_limit=int(getattr(settings, "rate_limit_default_limit", 60)),
            default_window_sec=int(getattr(settings, "rate_limit_default_window_sec", 60)),
            default_burst=int(getattr(settings, "rate_limit_default_burst", 10)),
            key_strategy=getattr(settings, "rate_limit_key_strategy", "principal"),
            fail_open=bool(getattr(settings, "rate_limit_fail_open", False)),
            route_overrides=route_overrides,
            skip_paths=list(getattr(settings, "rate_limit_skip_paths", _DEFAULT_SKIP_PATHS)),
        )

    def is_enabled(self) -> bool:
        return self._enabled

    async def setup(self) -> None:
        if self._enabled:
            await self._backend.setup()

    async def teardown(self) -> None:
        if self._enabled:
            await self._backend.teardown()

    def _should_skip(self, path: str) -> bool:
        for p in self._skip_paths:
            if path == p or path.startswith(p + "/"):
                return True
        return False

    def _resolve_config(self, path: str) -> tuple[int, int, int]:
        override = self._route_overrides.get(path) or {}
        limit = override.get("limit") or self._default_limit
        window = override.get("window_sec") or self._default_window_sec
        burst = override.get("burst") or self._default_burst
        return int(limit), int(window), int(burst)

    def _build_key(self, request: Request, path: str) -> RateLimitKey:
        principal = getattr(request.state, "principal", None)
        ip = request.client.host if request.client else "unknown"

        if self._key_strategy == "ip":
            return RateLimitKey(dim="ip", value=ip, route=path)
        if self._key_strategy == "principal":
            user = principal.user_id if principal and not principal.is_anonymous else "anonymous"
            return RateLimitKey(dim="user", value=user, route=path)
        # Compatibility strategy for deployments that explicitly opt into IP fallback.
        if principal and not principal.is_anonymous:
            return RateLimitKey(dim="user", value=principal.user_id, route=path)
        return RateLimitKey(dim="ip", value=ip, route=path)

    def install(self, app: FastAPI) -> None:
        if not self._enabled:
            return

        backend = self._backend
        should_skip = self._should_skip
        resolve_config = self._resolve_config
        build_key = self._build_key

        @app.middleware("http")
        async def rate_limit_middleware(request: Request, call_next):
            path = request.url.path
            if should_skip(path):
                return await call_next(request)

            key = build_key(request, path)
            limit, window_sec, burst = resolve_config(path)
            try:
                decision: RateLimitDecision = await backend.check(key, limit=limit, window_sec=window_sec, burst=burst)
            except Exception as e:  # pragma: no cover
                logger.error(
                    "rate_limit_check_failed",
                    extra={"path": path, "error": str(e)},
                    exc_info=True,
                )
                if self._fail_open:
                    return await call_next(request)
                return JSONResponse(
                    {
                        "error": "rate_limit_unavailable",
                        "message": "Rate limiting service unavailable",
                    },
                    status_code=503,
                )

            if not decision.allowed:
                logger.warning(
                    "rate_limited",
                    extra={
                        "path": path,
                        "dim": key.dim,
                        "value": key.value,
                        "limit": decision.limit,
                        "retry_after": decision.retry_after_sec,
                    },
                )
                return JSONResponse(
                    {
                        "error": "rate_limited",
                        "message": "Too Many Requests",
                        "retry_after": decision.retry_after_sec,
                    },
                    status_code=429,
                    headers={
                        "Retry-After": str(decision.retry_after_sec),
                        "X-RateLimit-Limit": str(decision.limit),
                        "X-RateLimit-Remaining": "0",
                    },
                )

            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(decision.limit)
            response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
            return response
