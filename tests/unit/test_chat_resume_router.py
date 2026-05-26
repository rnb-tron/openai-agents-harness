import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.api.middleware.auth.base import Principal
from src.api.routers.chat import ChatRequest, ChatResumeRequest, chat_stream, resume_chat


class _StreamingRuntime:
    def __init__(self):
        self.session = None
        self.user_input = None

    async def run_stream(self, session, user_input):
        self.session = session
        self.user_input = user_input
        yield {"type": "start", "session_id": session.session_id, "model": "test-model"}
        yield {"type": "delta", "delta": "完成"}
        yield {"type": "done", "data": {"session_id": session.session_id, "output": "完成"}}


@pytest.mark.asyncio
async def test_chat_stream_emits_ndjson_and_uses_authenticated_identity():
    runtime = _StreamingRuntime()

    response = await chat_stream(
        ChatRequest(message="回答我", session_id="session-1", user_id="body-user"),
        Principal(user_id="auth-user", is_anonymous=False),
        SimpleNamespace(runtime=runtime),
    )
    chunks = [chunk async for chunk in response.body_iterator]
    events = [json.loads(line) for chunk in chunks for line in chunk.splitlines()]

    assert response.media_type == "application/x-ndjson"
    assert response.headers["x-accel-buffering"] == "no"
    assert runtime.session.user_id == "auth-user"
    assert runtime.user_input == "回答我"
    assert events[1] == {"type": "delta", "delta": "完成"}
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_resume_chat_passes_native_state_and_authenticated_identity():
    runtime = SimpleNamespace(
        resume_with_approval=AsyncMock(return_value={"interrupted": False, "output": "完成"})
    )
    harness = SimpleNamespace(runtime=runtime)
    request = ChatResumeRequest(
        run_state={"snapshot": True},
        approval_request_id="approval-1",
        interruption_index=1,
        approved=False,
        session_id="session-1",
        message="删除数据",
        model="gpt-4o-mini",
        rejection_message="未经批准",
        user_id="body-user",
    )

    response = await resume_chat(
        request,
        Principal(user_id="auth-user", is_anonymous=False),
        harness,
    )

    runtime.resume_with_approval.assert_awaited_once()
    kwargs = runtime.resume_with_approval.await_args.kwargs
    assert kwargs["session"].session_id == "session-1"
    assert kwargs["session"].user_id == "auth-user"
    assert kwargs["run_state"] == {"snapshot": True}
    assert kwargs["approval_request_id"] == "approval-1"
    assert kwargs["reviewer"] == "auth-user"
    assert kwargs["interruption_index"] == 1
    assert kwargs["approved"] is False
    assert kwargs["rejection_message"] == "未经批准"
    assert response.data["output"] == "完成"


@pytest.mark.asyncio
async def test_resume_chat_returns_bad_request_for_invalid_sdk_state():
    runtime = SimpleNamespace(
        resume_with_approval=AsyncMock(side_effect=ValueError("审批中断不存在: 3"))
    )
    request = ChatResumeRequest(
        run_state={"snapshot": True},
        interruption_index=3,
        approved=True,
        session_id="session-1",
        message="删除数据",
        model="gpt-4o-mini",
    )

    with pytest.raises(HTTPException) as error:
        await resume_chat(
            request,
            Principal(user_id="anonymous", is_anonymous=True),
            SimpleNamespace(runtime=runtime),
        )

    assert error.value.status_code == 400
    assert error.value.detail == "审批中断不存在: 3"
