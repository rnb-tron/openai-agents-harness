from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.capabilities.observability import ObservabilityPlugin
from src.api.middleware.request_context import install_request_context


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
    )

    plugin.install(app)
    install_request_context(app)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    response = TestClient(app).get("/ping")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"]
    assert response.headers["X-Trace-ID"]


async def test_observability_protocol_adapter_has_no_resource_lifecycle():
    plugin = ObservabilityPlugin(enabled=True)

    assert await plugin.setup() is None
    assert await plugin.teardown() is None
