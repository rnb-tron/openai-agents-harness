from types import SimpleNamespace

import pytest

from src.api.routers.advanced import advanced_session_state


@pytest.mark.asyncio
async def test_advanced_session_state_returns_runtime_snapshot():
    runtime = SimpleNamespace(
        advanced_state=lambda session_id: {
            "session_id": session_id,
            "agent_path": ["MinimalChatAgent", "billing"],
        }
    )

    response = await advanced_session_state("session-1", SimpleNamespace(runtime=runtime))

    assert response.data["session_id"] == "session-1"
    assert response.data["agent_path"] == ["MinimalChatAgent", "billing"]
