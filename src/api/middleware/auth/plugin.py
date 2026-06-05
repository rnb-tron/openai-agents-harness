"""AuthPlugin: install JWT auth as a FastAPI HTTP middleware."""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.api.middleware.auth.base import AuthBackend, AuthError, Principal
from src.api.middleware.auth.jwt_backend import JWTAuthBackend
from src.core.logging import bind_log_context, reset_log_context, setup_logger

logger = setup_logger("api.middleware.auth")

_DEFAULT_SKIP_PATHS = ("/health", "/docs", "/redoc", "/openapi.json", "/ui")


class AuthPlugin:
    """Protocol-layer authentication plugin.

    name: "auth"
    """

    name = "auth"

    def __init__(
        self,
        *,
        enabled: bool = False,
        strict: bool = False,
        backend: Optional[AuthBackend] = None,
        skip_paths: Optional[list[str]] = None,
    ) -> None:
        self._enabled = enabled
        self._strict = strict
        self._backend = backend
        self._skip_paths = tuple(skip_paths) if skip_paths else _DEFAULT_SKIP_PATHS

    @classmethod
    def from_settings(cls, settings) -> "AuthPlugin":
        """Build an AuthPlugin from `Settings`. Returns disabled plugin if not enabled."""
        enabled = bool(getattr(settings, "auth_enabled", False))
        if not enabled:
            return cls(enabled=False)
        strict = bool(getattr(settings, "auth_strict", False))
        backend = JWTAuthBackend(
            algorithm=getattr(settings, "auth_jwt_algorithm", "HS256"),
            secret=getattr(settings, "auth_jwt_secret", ""),
            public_key=getattr(settings, "auth_jwt_public_key", ""),
            issuer=getattr(settings, "auth_jwt_issuer", None) or None,
            audience=getattr(settings, "auth_jwt_audience", None) or None,
            leeway_sec=int(getattr(settings, "auth_jwt_leeway_sec", 30)),
        )
        skip_paths = list(getattr(settings, "auth_skip_paths", _DEFAULT_SKIP_PATHS))
        return cls(enabled=True, strict=strict, backend=backend, skip_paths=skip_paths)

    def is_enabled(self) -> bool:
        return self._enabled

    async def setup(self) -> None:
        return None

    async def teardown(self) -> None:
        return None

    def _should_skip(self, path: str) -> bool:
        for p in self._skip_paths:
            if path == p or path.startswith(p + "/"):
                return True
        return False

    def install(self, app: FastAPI) -> None:
        if not self._enabled or self._backend is None:
            return

        backend = self._backend
        strict = self._strict
        should_skip = self._should_skip

        @app.middleware("http")
        async def auth_middleware(request: Request, call_next):
            path = request.url.path
            if should_skip(path):
                return await call_next(request)

            try:
                principal = await backend.authenticate(request)
            except AuthError as e:
                logger.warning(
                    "auth_failed",
                    extra={"path": path, "code": e.code, "reason": e.message},
                )
                return JSONResponse(
                    {"error": "unauthorized", "code": e.code, "message": e.message},
                    status_code=e.status_code,
                )
            except Exception as e:  # pragma: no cover
                logger.error(
                    "auth_backend_error",
                    extra={"path": path, "error": str(e)},
                    exc_info=True,
                )
                return JSONResponse(
                    {"error": "unauthorized", "code": "auth_error", "message": "auth backend error"},
                    status_code=401,
                )

            if principal is None:
                if strict:
                    logger.warning("auth_missing_credential", extra={"path": path})
                    return JSONResponse(
                        {
                            "error": "unauthorized",
                            "code": "missing_credential",
                            "message": "missing or invalid Authorization header",
                        },
                        status_code=401,
                    )
                principal = Principal(user_id="anonymous", is_anonymous=True)

            request.state.principal = principal

            ctx_token = bind_log_context(
                principal_id=principal.user_id,
                anonymous=principal.is_anonymous,
            )
            try:
                return await call_next(request)
            finally:
                reset_log_context(ctx_token)
