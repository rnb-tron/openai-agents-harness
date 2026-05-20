"""Self-test for protocol-layer JWT auth plugin.

Run: venv/bin/python -m tests.test_middleware_auth
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import jwt as pyjwt
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api.middleware.auth.base import Principal
from src.api.middleware.auth.deps import get_current_principal, require_scope
from src.api.middleware.auth.jwt_backend import JWTAuthBackend
from src.api.middleware.auth.plugin import AuthPlugin


SECRET = "unit-test-secret-do-not-use-in-prod"


def _build_app(*, strict: bool = False, scopes_required: tuple[str, ...] = ()) -> FastAPI:
    app = FastAPI()
    backend = JWTAuthBackend(algorithm="HS256", secret=SECRET, leeway_sec=5)
    plugin = AuthPlugin(enabled=True, strict=strict, backend=backend)
    plugin.install(app)

    @app.get("/whoami")
    def whoami(principal: Principal = Depends(get_current_principal)):
        return {
            "user_id": principal.user_id,
            "anonymous": principal.is_anonymous,
            "scopes": principal.scopes,
        }

    if scopes_required:
        @app.get("/admin")
        def admin(principal: Principal = Depends(require_scope(*scopes_required))):
            return {"user_id": principal.user_id}

    @app.get("/health")
    def health():
        return {"ok": True}

    return app


def _make_token(sub: str, *, exp_delta_sec: int = 60, secret: str = SECRET, scopes=None,
                algorithm: str = "HS256") -> str:
    now = dt.datetime.now(tz=dt.timezone.utc)
    claims = {
        "sub": sub,
        "iat": now,
        "exp": now + dt.timedelta(seconds=exp_delta_sec),
    }
    if scopes is not None:
        claims["scope"] = " ".join(scopes) if isinstance(scopes, (list, tuple)) else str(scopes)
    return pyjwt.encode(claims, secret, algorithm=algorithm)


def test_anonymous_when_not_strict():
    app = _build_app(strict=False)
    client = TestClient(app)
    r = client.get("/whoami")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["anonymous"] is True
    assert body["user_id"] == "anonymous"
    print("OK test_anonymous_when_not_strict")


def test_strict_rejects_missing_token():
    app = _build_app(strict=True)
    client = TestClient(app)
    r = client.get("/whoami")
    assert r.status_code == 401, r.text
    assert r.json()["code"] == "missing_credential"
    print("OK test_strict_rejects_missing_token")


def test_valid_token_resolves_principal():
    app = _build_app(strict=True)
    client = TestClient(app)
    tok = _make_token("user-42", scopes=["read", "write"])
    r = client.get("/whoami", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["anonymous"] is False
    assert body["user_id"] == "user-42"
    assert "read" in body["scopes"] and "write" in body["scopes"]
    print("OK test_valid_token_resolves_principal")


def test_expired_token_returns_401():
    app = _build_app(strict=True)
    client = TestClient(app)
    tok = _make_token("user-42", exp_delta_sec=-3600)
    r = client.get("/whoami", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 401, r.text
    assert r.json()["code"] == "token_expired"
    print("OK test_expired_token_returns_401")


def test_invalid_signature_returns_401():
    app = _build_app(strict=True)
    client = TestClient(app)
    tok = _make_token("user-42", secret="some-other-secret")
    r = client.get("/whoami", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 401, r.text
    assert r.json()["code"] in {"invalid_signature", "invalid_token"}
    print("OK test_invalid_signature_returns_401")


def test_skip_path_bypasses_strict():
    app = _build_app(strict=True)
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200, r.text
    print("OK test_skip_path_bypasses_strict")


def test_require_scope_enforced():
    app = _build_app(strict=True, scopes_required=("admin",))
    client = TestClient(app)

    # Token without admin scope -> 403
    tok = _make_token("user-1", scopes=["read"])
    r = client.get("/admin", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["code"] == "missing_scope"

    # Token with admin scope -> 200
    tok2 = _make_token("user-1", scopes=["read", "admin"])
    r2 = client.get("/admin", headers={"Authorization": f"Bearer {tok2}"})
    assert r2.status_code == 200, r2.text
    print("OK test_require_scope_enforced")


def test_x_api_token_fallback_header():
    app = _build_app(strict=True)
    client = TestClient(app)
    tok = _make_token("user-9")
    r = client.get("/whoami", headers={"X-Api-Token": tok})
    assert r.status_code == 200, r.text
    assert r.json()["user_id"] == "user-9"
    print("OK test_x_api_token_fallback_header")


def main():
    test_anonymous_when_not_strict()
    test_strict_rejects_missing_token()
    test_valid_token_resolves_principal()
    test_expired_token_returns_401()
    test_invalid_signature_returns_401()
    test_skip_path_bypasses_strict()
    test_require_scope_enforced()
    test_x_api_token_fallback_header()
    print("\nAll auth middleware tests passed.")


if __name__ == "__main__":
    main()
