"""FastAPI dependencies for accessing the authenticated Principal."""

from __future__ import annotations

from typing import Callable

from fastapi import HTTPException, Request, status

from src.api.middleware.auth.base import Principal


def get_current_principal(request: Request) -> Principal:
    """Return the current request's Principal.

    If AuthPlugin is not installed (auth_enabled=False), returns an
    anonymous Principal so route handlers stay simple.
    """
    principal = getattr(request.state, "principal", None)
    if principal is None:
        return Principal(user_id="anonymous", is_anonymous=True)
    return principal


def require_scope(*required: str) -> Callable[[Request], Principal]:
    """Build a Depends-friendly callable that enforces required scopes."""

    def _dep(request: Request) -> Principal:
        principal = get_current_principal(request)
        if principal.is_anonymous:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "unauthorized", "code": "auth_required"},
            )
        missing = [s for s in required if s not in principal.scopes]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "forbidden", "code": "missing_scope", "missing": missing},
            )
        return principal

    return _dep
