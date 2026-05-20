"""Authentication abstractions: Principal, AuthBackend, AuthError."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import Request


@dataclass
class Principal:
    """Authenticated identity carried across the HTTP request lifecycle.

    Stored on `request.state.principal` by the AuthPlugin.
    `is_anonymous=True` means no valid credential was presented and the
    middleware is running in non-strict mode (back-compat path).
    """

    user_id: str
    scopes: list[str] = field(default_factory=list)
    claims: dict[str, Any] = field(default_factory=dict)
    is_anonymous: bool = False

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


class AuthError(Exception):
    """Raised by an AuthBackend when authentication fails.

    The plugin translates this into a 401 response. `code` is a stable short
    identifier surfaced in the response body and structured logs.
    """

    def __init__(self, code: str, message: str, status_code: int = 401) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class AuthBackend(ABC):
    """Authenticate an incoming request.

    Returns:
        - `Principal` on success
        - `None` if no credential was presented (caller decides strict/non-strict)
        - raises `AuthError` if a credential was presented but invalid
    """

    @abstractmethod
    async def authenticate(self, request: Request) -> Optional[Principal]:
        ...
