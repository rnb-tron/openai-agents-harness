import asyncio
import json
from types import SimpleNamespace

import pytest

from src.api.middleware.auth.base import Principal
import src.api.routers.chat as chat_router
from src.api.routers.chat import (
    ChatCancelRequest,
    ChatRequest,
    ChatResumeRequest,
    cancel_chat,
    chat_stream,
    list_chat_messages,
    resume_chat_stream,
)


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


class _MessageStore:
    def __init__(self):
        self.recent_calls = []
        self.list_calls = []

    async def get_session(self, session_id):
        return {"id": session_id, "user_id": "auth-user"}

    async def list_messages(self, **kwargs):
        self.list_calls.append(kwargs)
        return [{"content": "old"}]

    async def list_recent_messages(self, **kwargs):
        self.recent_calls.append(kwargs)
        return [{"content": "new"}]


class _FailingTurnStore:
    async def append_turn(self, **kwargs):
        raise RuntimeError("mysql unavailable")


class _RecordingTurnStore:
    def __init__(self):
        self.calls = []

    async def append_turn(self, **kwargs):
        self.calls.append(kwargs)


class _BlockingRuntime:
    def __init__(self):
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def run_stream(self, session, user_input):
        yield {"type": "start", "session_id": session.session_id, "model": "test-model"}
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise


class _FakeRedis:
    def __init__(self, *, fail: bool = False, values: list[str] | None = None):
        self.fail = fail
        self.values = values or []
        self.rpush_calls = []
        self.expire_calls = []
        self.lrange_calls = []

    async def rpush(self, key, value):
        if self.fail:
            raise RuntimeError("redis unavailable")
        self.rpush_calls.append((key, value))

    async def expire(self, key, ttl):
        self.expire_calls.append((key, ttl))

    async def lrange(self, key, start, end):
        if self.fail:
            raise RuntimeError("redis unavailable")
        self.lrange_calls.append((key, start, end))
        return self.values


def _parse_ndjson(chunks):
    return [json.loads(line) for chunk in chunks for line in chunk.splitlines()]


@pytest.mark.asyncio
async def test_list_chat_messages_can_return_recent_messages():
    store = _MessageStore()

    response = await list_chat_messages(
        "session-1",
        limit=20,
        recent=True,
        principal=Principal(user_id="auth-user", is_anonymous=False),
        harness=SimpleNamespace(session_store=store),
    )

    assert response.data == [{"content": "new"}]
    assert store.recent_calls == [{"session_id": "session-1", "limit": 20}]
    assert store.list_calls == []


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
async def test_chat_cancel_cancels_active_stream_and_persists_partial_cache(monkeypatch):
    runtime = _BlockingRuntime()
    store = _RecordingTurnStore()
    redis = _FakeRedis(
        values=[
            json.dumps({"type": "start", "session_id": "session-1", "model": "test-model", "input": "回答我"}),
            json.dumps({"type": "delta", "delta": "部"}),
            json.dumps({"type": "delta", "delta": "分完成"}),
        ]
    )
    monkeypatch.setattr(chat_router, "get_redis_client", lambda for_write=True: redis)
    response = await chat_stream(
        ChatRequest(message="回答我", session_id="session-1", user_id="body-user"),
        Principal(user_id="auth-user", is_anonymous=False),
        SimpleNamespace(runtime=runtime, session_store=store),
    )

    async def consume():
        return [chunk async for chunk in response.body_iterator]

    consumer = asyncio.create_task(consume())
    await asyncio.wait_for(runtime.started.wait(), timeout=1)

    result = await cancel_chat(
        ChatCancelRequest(sessionId="session-1", userId="body-user"),
        Principal(user_id="auth-user", is_anonymous=False),
        SimpleNamespace(session_store=store),
    )

    assert result.code == "1"
    assert result.msg == "取消成功"
    await asyncio.wait_for(runtime.cancelled.wait(), timeout=1)
    chunks = await asyncio.wait_for(consumer, timeout=1)
    events = _parse_ndjson(chunks)
    await asyncio.sleep(0)
    assert [event["type"] for event in events] == ["start"]
    assert redis.lrange_calls == [("chat:stream:events:session-1:auth-user", 0, -1)]
    assert store.calls == [
        {
            "session_id": "session-1",
            "user_id": "auth-user",
            "user_input": "回答我",
            "assistant_output": "部分完成",
            "model": "test-model",
            "status": "cancelled",
            "metadata": {"source": "chat_cancel_cache", "partial": True},
        }
    ]


@pytest.mark.asyncio
async def test_chat_cancel_returns_not_found_for_missing_or_forbidden_task():
    runtime = _BlockingRuntime()
    response = await chat_stream(
        ChatRequest(message="回答我", session_id="session-2", user_id="body-user"),
        Principal(user_id="auth-user", is_anonymous=False),
        SimpleNamespace(runtime=runtime),
    )

    async def consume():
        return [chunk async for chunk in response.body_iterator]

    consumer = asyncio.create_task(consume())
    await asyncio.wait_for(runtime.started.wait(), timeout=1)

    forbidden = await cancel_chat(
        ChatCancelRequest(sessionId="session-2", userId="other-user"),
        Principal(user_id="other-user", is_anonymous=False),
    )
    assert forbidden.code == "1"
    assert forbidden.msg == "未找到运行中的会话"
    assert not runtime.cancelled.is_set()

    missing = await cancel_chat(
        ChatCancelRequest(sessionId="missing", userId="auth-user"),
        Principal(user_id="auth-user", is_anonymous=False),
    )
    assert missing.msg == "未找到运行中的会话"

    await cancel_chat(
        ChatCancelRequest(sessionId="session-2", userId="auth-user"),
        Principal(user_id="auth-user", is_anonymous=False),
    )
    await asyncio.wait_for(runtime.cancelled.wait(), timeout=1)
    await asyncio.wait_for(consumer, timeout=1)


@pytest.mark.asyncio
async def test_chat_stream_caches_events_to_redis(monkeypatch):
    redis = _FakeRedis()
    monkeypatch.setattr(chat_router, "get_redis_client", lambda for_write=True: redis)

    response = await chat_stream(
        ChatRequest(message="回答我", session_id="session-3", user_id="body-user"),
        Principal(user_id="auth-user", is_anonymous=False),
        SimpleNamespace(runtime=_StreamingRuntime()),
    )
    chunks = [chunk async for chunk in response.body_iterator]
    events = _parse_ndjson(chunks)

    assert events[-1]["type"] == "done"
    assert [json.loads(value)["type"] for _, value in redis.rpush_calls] == ["start", "delta", "done"]
    assert redis.expire_calls == [
        ("chat:stream:events:session-3:auth-user", 600),
        ("chat:stream:events:session-3:auth-user", 600),
        ("chat:stream:events:session-3:auth-user", 600),
    ]


@pytest.mark.asyncio
async def test_chat_stream_ignores_redis_cache_failures(monkeypatch):
    monkeypatch.setattr(chat_router, "get_redis_client", lambda for_write=True: _FakeRedis(fail=True))

    response = await chat_stream(
        ChatRequest(message="回答我", session_id="session-4", user_id="body-user"),
        Principal(user_id="auth-user", is_anonymous=False),
        SimpleNamespace(runtime=_StreamingRuntime()),
    )
    chunks = [chunk async for chunk in response.body_iterator]
    events = _parse_ndjson(chunks)

    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_chat_stream_reports_session_persist_failure():
    runtime = _StreamingRuntime()

    response = await chat_stream(
        ChatRequest(message="回答我", session_id="session-1", user_id="body-user"),
        Principal(user_id="auth-user", is_anonymous=False),
        SimpleNamespace(runtime=runtime, session_store=_FailingTurnStore()),
    )
    chunks = [chunk async for chunk in response.body_iterator]
    events = [json.loads(line) for chunk in chunks for line in chunk.splitlines()]

    assert events[-1]["type"] == "error"
    assert "session persist failed" in events[-1]["detail"]
    assert all(event["type"] != "done" for event in events)


@pytest.mark.asyncio
async def test_resume_chat_stream_emits_ndjson_continuation_events():
    class Runtime:
        async def resume_stream_with_approval(self, **kwargs):
            self.kwargs = kwargs
            yield {"type": "start", "session_id": kwargs["session"].session_id}
            yield {"type": "delta", "delta": "继续"}
            yield {"type": "done", "data": {"output": "继续完成"}}

    runtime = Runtime()
    request = ChatResumeRequest(
        run_state={"snapshot": True},
        interruption_index=0,
        approved=True,
        session_id="session-1",
        message="查询天气",
        model="gpt-4o-mini",
    )

    response = await resume_chat_stream(
        request,
        Principal(user_id="auth-user", is_anonymous=False),
        SimpleNamespace(runtime=runtime),
    )
    chunks = [chunk async for chunk in response.body_iterator]
    events = [json.loads(line) for chunk in chunks for line in chunk.splitlines()]

    assert response.media_type == "application/x-ndjson"
    assert events[1] == {"type": "delta", "delta": "继续"}
    assert runtime.kwargs["session"].user_id == "auth-user"


@pytest.mark.asyncio
async def test_resume_chat_stream_emits_error_for_invalid_sdk_state():
    class Runtime:
        async def resume_stream_with_approval(self, **kwargs):
            raise ValueError("审批中断不存在: 3")
            yield  # pragma: no cover

    request = ChatResumeRequest(
        run_state={"snapshot": True},
        interruption_index=3,
        approved=True,
        session_id="session-1",
        message="删除数据",
        model="gpt-4o-mini",
    )

    response = await resume_chat_stream(
        request,
        Principal(user_id="anonymous", is_anonymous=True),
        SimpleNamespace(runtime=Runtime()),
    )
    chunks = [chunk async for chunk in response.body_iterator]
    events = [json.loads(line) for chunk in chunks for line in chunk.splitlines()]

    assert events == [{"type": "error", "detail": "审批中断不存在: 3"}]
