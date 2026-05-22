from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.capabilities.observability import ObservabilityConfig, ObservabilityPlugin


class _FakeTracer:
    pass


def test_observability_plugin_disabled_is_noop():
    app = FastAPI()
    plugin = ObservabilityPlugin(enabled=False)

    plugin.install(app)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    response = TestClient(app).get("/ping")

    assert response.status_code == 200
    assert "X-Trace-ID" not in response.headers


def test_observability_plugin_installs_request_trace_headers():
    app = FastAPI()
    plugin = ObservabilityPlugin(
        enabled=True,
        config=ObservabilityConfig(enabled=False),
    )

    plugin.install(app)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    response = TestClient(app).get("/ping")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"]
    assert response.headers["X-Trace-ID"]


async def test_observability_plugin_lifecycle_uses_injected_hooks():
    calls = []

    async def init(config):
        calls.append(("init", config.enabled))
        return _FakeTracer()

    async def shutdown():
        calls.append(("shutdown", None))

    plugin = ObservabilityPlugin(
        enabled=True,
        config=ObservabilityConfig(enabled=True),
        init_fn=init,
        shutdown_fn=shutdown,
    )

    await plugin.setup()
    await plugin.teardown()
    await plugin.teardown()

    assert calls == [("init", True), ("shutdown", None)]
