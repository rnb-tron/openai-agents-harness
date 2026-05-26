from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers.ui import router


def test_chat_ui_serves_local_e2e_console():
    app = FastAPI()
    app.include_router(router)

    response = TestClient(app).get("/ui")

    assert response.status_code == 200
    assert "Agent Harness / Chat E2E Console" in response.text
    assert 'fetch("/chat/stream"' in response.text
    assert 'fetch("/chat/resume"' in response.text
