"""JWT verification backend (consumer side; does not issue tokens)."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import Request

try:
    import jwt as pyjwt
    from jwt import (
        ExpiredSignatureError,
        InvalidAudienceError,
        InvalidIssuerError,
        InvalidSignatureError,
        InvalidTokenError,
    )

    _JWT_AVAILABLE = True
except ImportError:  # pragma: no cover
    pyjwt = None  # type: ignore[assignment]
    _JWT_AVAILABLE = False

from src.api.middleware.auth.base import AuthBackend, AuthError, Principal
from src.core.logging import setup_logger

logger = setup_logger("api.middleware.auth.jwt")


class JWTAuthBackend(AuthBackend):
    """Verify a Bearer JWT and produce a Principal.

    Supports HS256 (symmetric secret) and RS256 (public key).
    """

    def __init__(
        self,
        *,
        algorithm: str = "HS256",
        secret: str = "",
        public_key: str = "",
        issuer: Optional[str] = None,
        audience: Optional[str] = None,
        leeway_sec: int = 30,
        bearer_header: str = "Authorization",
        fallback_header: Optional[str] = "X-Api-Token",
    ) -> None:
        if not _JWT_AVAILABLE:
            raise RuntimeError("PyJWT is not installed. Add `PyJWT>=2.8` to requirements.txt")
        self.algorithm = algorithm
        self.issuer = issuer
        self.audience = audience
        self.leeway_sec = leeway_sec
        self.bearer_header = bearer_header
        self.fallback_header = fallback_header

        if algorithm.startswith("HS"):
            if not secret:
                raise ValueError("auth_jwt_secret is required for HS* algorithms")
            self._key: str = secret
        elif algorithm.startswith("RS") or algorithm.startswith("ES"):
            if not public_key:
                raise ValueError("auth_jwt_public_key is required for RS*/ES* algorithms")
            self._key = public_key
        else:
            raise ValueError(f"unsupported jwt algorithm: {algorithm}")

    def _extract_token(self, request: Request) -> Optional[str]:
        auth = request.headers.get(self.bearer_header)
        if auth:
            parts = auth.split(None, 1)
            if len(parts) == 2 and parts[0].lower() == "bearer":
                token = parts[1].strip()
                if token:
                    return token
        if self.fallback_header:
            tok = request.headers.get(self.fallback_header)
            if tok:
                return tok.strip()
        return None

    async def authenticate(self, request: Request) -> Optional[Principal]:
        token = self._extract_token(request)
        if not token:
            return None

        options: dict[str, Any] = {
            "verify_signature": True,
            "require": ["exp"],
        }
        kwargs: dict[str, Any] = {
            "algorithms": [self.algorithm],
            "leeway": self.leeway_sec,
            "options": options,
        }
        if self.issuer:
            kwargs["issuer"] = self.issuer
        if self.audience:
            kwargs["audience"] = self.audience

        try:
            claims: dict[str, Any] = pyjwt.decode(token, self._key, **kwargs)
        except ExpiredSignatureError as e:
            raise AuthError("token_expired", "JWT expired") from e
        except InvalidSignatureError as e:
            raise AuthError("invalid_signature", "JWT signature invalid") from e
        except InvalidIssuerError as e:
            raise AuthError("invalid_issuer", "JWT issuer mismatch") from e
        except InvalidAudienceError as e:
            raise AuthError("invalid_audience", "JWT audience mismatch") from e
        except InvalidTokenError as e:
            raise AuthError("invalid_token", f"JWT invalid: {e}") from e

        sub = claims.get("sub")
        if not sub:
            raise AuthError("missing_sub", "JWT missing 'sub' claim")

        scope_field = claims.get("scope") or claims.get("scopes") or []
        if isinstance(scope_field, str):
            scopes = [s for s in scope_field.split() if s]
        elif isinstance(scope_field, list):
            scopes = [str(s) for s in scope_field]
        else:
            scopes = []

        return Principal(user_id=str(sub), scopes=scopes, claims=claims, is_anonymous=False)
