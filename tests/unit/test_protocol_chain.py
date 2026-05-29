from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import pytest

from src.api.middleware.chain import ProtocolRequestChain


class _FailingPlugin:
    name = "failure"

    def install(self, app):
        return None

    async def setup(self):
        raise RuntimeError("setup unavailable")

    async def teardown(self):
        return None


class _RecordingPlugin:
    def __init__(self, name, calls):
        self.name = name
        self._calls = calls

    def install(self, app):
        name = self.name
        calls = self._calls

        @app.middleware("http")
        async def middleware(request: Request, call_next):
            calls.append(f"{name}:before")
            response = await call_next(request)
            calls.append(f"{name}:after")
            return response

    async def setup(self):
        return None

    async def teardown(self):
        return None


@pytest.mark.asyncio
async def test_protocol_chain_raises_plugin_startup_failure():
    chain = ProtocolRequestChain((_FailingPlugin(),))

    with pytest.raises(RuntimeError, match="setup unavailable"):
        await chain.startup()


def test_protocol_chain_executes_declared_request_order():
    calls = []
    chain = ProtocolRequestChain(
        (
            _RecordingPlugin("observability", calls),
            _RecordingPlugin("auth", calls),
            _RecordingPlugin("rate_limit", calls),
        )
    )
    app = FastAPI()

    @app.get("/")
    async def root():
        return {"ok": True}

    chain.install_on(app)

    assert [plugin.name for plugin in chain.request_order] == [
        "observability",
        "auth",
        "rate_limit",
    ]
    assert TestClient(app).get("/").status_code == 200
    assert calls == [
        "observability:before",
        "auth:before",
        "rate_limit:before",
        "rate_limit:after",
        "auth:after",
        "observability:after",
    ]
