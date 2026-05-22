"""Self-test for protocol-layer rate-limit plugin (memory backend).

Run: venv/bin/python -m tests.test_middleware_rate_limit
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api.middleware.rate_limit.base import RateLimitKey
from src.api.middleware.rate_limit.memory_backend import MemoryRateLimiter
from src.api.middleware.rate_limit.plugin import RateLimitPlugin


def _build_app(plugin: RateLimitPlugin) -> FastAPI:
    app = FastAPI()
    plugin.install(app)

    @app.get("/chat")
    def chat():
        return {"ok": True}

    @app.get("/heavy")
    def heavy():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"ok": True}

    return app


def test_blocks_after_burst_exhausted():
    backend = MemoryRateLimiter()
    plugin = RateLimitPlugin(
        enabled=True,
        backend=backend,
        default_limit=2,
        default_window_sec=60,
        default_burst=2,
        key_strategy="ip",
    )
    app = _build_app(plugin)
    client = TestClient(app)

    # First 2 allowed
    r1 = client.get("/chat")
    r2 = client.get("/chat")
    assert r1.status_code == 200
    assert r2.status_code == 200

    # 3rd should be limited
    r3 = client.get("/chat")
    assert r3.status_code == 429, r3.text
    assert r3.headers.get("Retry-After") is not None
    assert r3.headers.get("X-RateLimit-Limit") == "2"
    assert r3.headers.get("X-RateLimit-Remaining") == "0"
    body = r3.json()
    assert body["error"] == "rate_limited"
    assert body["retry_after"] >= 1
    print("OK test_blocks_after_burst_exhausted")


def test_independent_buckets_per_route():
    backend = MemoryRateLimiter()
    plugin = RateLimitPlugin(
        enabled=True,
        backend=backend,
        default_limit=1,
        default_window_sec=60,
        default_burst=1,
        key_strategy="ip",
    )
    app = _build_app(plugin)
    client = TestClient(app)

    r1 = client.get("/chat")
    r2 = client.get("/chat")
    r3 = client.get("/heavy")
    assert r1.status_code == 200
    assert r2.status_code == 429
    assert r3.status_code == 200, "different route -> different bucket"
    print("OK test_independent_buckets_per_route")


def test_route_override_applies():
    backend = MemoryRateLimiter()
    plugin = RateLimitPlugin(
        enabled=True,
        backend=backend,
        default_limit=100,
        default_window_sec=60,
        default_burst=100,
        key_strategy="ip",
        route_overrides={"/chat": {"limit": 1, "window_sec": 60, "burst": 1}},
    )
    app = _build_app(plugin)
    client = TestClient(app)

    # /chat tighter override
    assert client.get("/chat").status_code == 200
    assert client.get("/chat").status_code == 429
    # /heavy still has default generous quota
    for _ in range(5):
        assert client.get("/heavy").status_code == 200
    print("OK test_route_override_applies")


def test_skip_paths_bypass_limiter():
    backend = MemoryRateLimiter()
    plugin = RateLimitPlugin(
        enabled=True,
        backend=backend,
        default_limit=1,
        default_window_sec=60,
        default_burst=1,
        key_strategy="ip",
    )
    app = _build_app(plugin)
    client = TestClient(app)

    # /health is in default skip_paths
    for _ in range(5):
        assert client.get("/health").status_code == 200
    print("OK test_skip_paths_bypass_limiter")


def test_remaining_header_decrements():
    backend = MemoryRateLimiter()
    plugin = RateLimitPlugin(
        enabled=True,
        backend=backend,
        default_limit=3,
        default_window_sec=60,
        default_burst=3,
        key_strategy="ip",
    )
    app = _build_app(plugin)
    client = TestClient(app)
    r1 = client.get("/chat")
    r2 = client.get("/chat")
    assert r1.headers.get("X-RateLimit-Limit") == "3"
    rem1 = int(r1.headers["X-RateLimit-Remaining"])
    rem2 = int(r2.headers["X-RateLimit-Remaining"])
    assert rem1 >= rem2
    print("OK test_remaining_header_decrements")


def test_disabled_plugin_no_op():
    plugin = RateLimitPlugin(enabled=False)
    app = _build_app(plugin)
    client = TestClient(app)
    for _ in range(20):
        assert client.get("/chat").status_code == 200
    print("OK test_disabled_plugin_no_op")


import asyncio


def test_memory_backend_direct():
    """Validate MemoryRateLimiter math directly (no HTTP)."""
    backend = MemoryRateLimiter()
    key = RateLimitKey(dim="user", value="u1", route="/x")

    async def run():
        d1 = await backend.check(key, limit=2, window_sec=60, burst=2)
        d2 = await backend.check(key, limit=2, window_sec=60, burst=2)
        d3 = await backend.check(key, limit=2, window_sec=60, burst=2)
        assert d1.allowed and d2.allowed
        assert not d3.allowed
        assert d3.retry_after_sec >= 1

    asyncio.run(run())
    print("OK test_memory_backend_direct")


def main():
    test_blocks_after_burst_exhausted()
    test_independent_buckets_per_route()
    test_route_override_applies()
    test_skip_paths_bypass_limiter()
    test_remaining_header_decrements()
    test_disabled_plugin_no_op()
    test_memory_backend_direct()
    print("\nAll rate-limit middleware tests passed.")


if __name__ == "__main__":
    main()
