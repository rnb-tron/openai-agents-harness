"""JWT-based authentication plugin."""

from src.api.middleware.auth.base import AuthBackend, AuthError, Principal
from src.api.middleware.auth.deps import get_current_principal, require_scope
from src.api.middleware.auth.jwt_backend import JWTAuthBackend
from src.api.middleware.auth.plugin import AuthPlugin

__all__ = [
    "AuthBackend",
    "AuthError",
    "Principal",
    "JWTAuthBackend",
    "AuthPlugin",
    "get_current_principal",
    "require_scope",
]
