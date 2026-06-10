import asyncio
import json
from types import SimpleNamespace

import pytest

from src.api.middleware.auth.base import Principal
import src.services.chat_service as chat_service
import src.services.chat_stream_cache as chat_stream_cache
from src.api.routers.chat import (
    ChatCancelRequest,
    ChatRequest,
    ChatResumeRequest,
    chat,
    cancel_chat,
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
        yield {"event": "init", "data": {"model": "test-model"}}
        yield {"event": "content", "data": {"text": "完成"}}
        yield {"event": "end", "data": {"status": "success", "model": "test-model", "output": "完成"}}


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
        yield {"event": "init", "data": {"model": "test-model"}}
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

    async def get(self, key):
        return None

    async def set(self, key, value, ex=None):
        return True


def _parse_sse(chunks):
    payload = "".join(chunks)
    events = []
    for block in payload.split("\n\n"):
        if not block.strip():
            continue
        event = {}
        for line in block.splitlines():
            if line.startswith("event:"):
                event["event"] = line[len("event:") :]
            elif line.startswith("id:"):
                event["id"] = line[len("id:") :]
            elif line.startswith("data:"):
                event["data"] = json.loads(line[len("data:") :])
        events.append(event)
    return events


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
async def test_chat_stream_emits_sse_and_uses_authenticated_identity(monkeypatch):
    runtime = _StreamingRuntime()
    monkeypatch.setattr(chat_service, "generate_turn_id", lambda: "turn-fixed")

    response = await chat(
        ChatRequest(
            query="回答我",
            session_id="session-1",
            user_id="body-user",
            options={"scene": "ticket_dispatch", "tenant_id": "tenant-1"},
        ),
        Principal(user_id="auth-user", is_anonymous=False),
        SimpleNamespace(runtime=runtime),
    )
    chunks = [chunk async for chunk in response.body_iterator]
    events = _parse_sse(chunks)

    assert response.media_type == "text/event-stream"
    assert response.headers["x-accel-buffering"] == "no"
    assert runtime.session.user_id == "auth-user"
    assert runtime.user_input == "回答我"
    assert runtime.session.context["business"] == {"scene": "ticket_dispatch", "tenant_id": "tenant-1"}
    assert events[0] == {
        "event": "init",
        "id": "turn-fixed_1",
        "data": {
            "protocol": {"sessionId": "session-1", "turnId": "turn-fixed"},
            "model": "test-model",
            "userId": "auth-user",
        },
    }
    assert events[1]["event"] == "content"
    assert events[1]["data"]["text"] == "完成"
    assert events[-1]["event"] == "end"
    assert events[-1]["data"]["status"] == "success"


@pytest.mark.asyncio
async def test_chat_cancel_cancels_active_stream_and_persists_partial_cache(monkeypatch):
    runtime = _BlockingRuntime()
    store = _RecordingTurnStore()
    redis = _FakeRedis(
        values=[
            json.dumps(
                {
                    "frame": {
                        "event": "init",
                        "id": "turn-fixed_1",
                        "data": {
                            "protocol": {"sessionId": "session-1", "turnId": "turn-fixed"},
                            "model": "test-model",
                        },
                    },
                    "meta": {"userInput": "回答我"},
                }
            ),
            json.dumps(
                {
                    "frame": {
                        "event": "content",
                        "id": "turn-fixed_2",
                        "data": {"protocol": {"sessionId": "session-1", "turnId": "turn-fixed"}, "text": "部"},
                    }
                }
            ),
            json.dumps(
                {
                    "frame": {
                        "event": "content",
                        "id": "turn-fixed_3",
                        "data": {"protocol": {"sessionId": "session-1", "turnId": "turn-fixed"}, "text": "分完成"},
                    }
                }
            ),
        ]
    )
    monkeypatch.setattr(chat_stream_cache, "get_redis_client", lambda for_write=True: redis)
    monkeypatch.setattr(chat_service, "generate_turn_id", lambda: "turn-fixed")
    response = await chat(
        ChatRequest(query="回答我", session_id="session-1", user_id="body-user"),
        Principal(user_id="auth-user", is_anonymous=False),
        SimpleNamespace(runtime=runtime, session_store=store),
    )

    async def consume():
        return [chunk async for chunk in response.body_iterator]

    consumer = asyncio.create_task(consume())
    await asyncio.wait_for(runtime.started.wait(), timeout=1)

    result = await cancel_chat(
        ChatCancelRequest(sessionId="session-1", turnId="turn-fixed", userId="body-user"),
        Principal(user_id="auth-user", is_anonymous=False),
        SimpleNamespace(session_store=store),
    )

    assert result.code == "1"
    assert result.msg == "取消成功"
    await asyncio.wait_for(runtime.cancelled.wait(), timeout=1)
    chunks = await asyncio.wait_for(consumer, timeout=1)
    events = _parse_sse(chunks)
    await asyncio.sleep(0)
    assert [event["event"] for event in events] == ["init"]
    assert redis.lrange_calls == [("chat:sse:events:session-1:turn-fixed", 0, -1)]
    assert store.calls == [
        {
            "session_id": "session-1",
            "user_id": "auth-user",
            "user_input": "回答我",
            "assistant_output": "部分完成",
            "turn_id": "turn-fixed",
            "model": "test-model",
            "status": "cancelled",
            "metadata": {"source": "chat_cancel_cache", "partial": True},
        }
    ]


@pytest.mark.asyncio
async def test_chat_cancel_returns_not_found_for_missing_or_forbidden_task(monkeypatch):
    runtime = _BlockingRuntime()
    monkeypatch.setattr(chat_service, "generate_turn_id", lambda: "turn-fixed")
    response = await chat(
        ChatRequest(query="回答我", session_id="session-2", user_id="body-user"),
        Principal(user_id="auth-user", is_anonymous=False),
        SimpleNamespace(runtime=runtime),
    )

    async def consume():
        return [chunk async for chunk in response.body_iterator]

    consumer = asyncio.create_task(consume())
    await asyncio.wait_for(runtime.started.wait(), timeout=1)

    forbidden = await cancel_chat(
        ChatCancelRequest(sessionId="session-2", turnId="turn-missing", userId="other-user"),
        Principal(user_id="other-user", is_anonymous=False),
    )
    assert forbidden.code == "1"
    assert forbidden.msg == "未找到运行中的会话"
    assert not runtime.cancelled.is_set()

    missing = await cancel_chat(
        ChatCancelRequest(sessionId="missing", turnId="turn-missing", userId="auth-user"),
        Principal(user_id="auth-user", is_anonymous=False),
    )
    assert missing.msg == "未找到运行中的会话"

    await cancel_chat(
        ChatCancelRequest(sessionId="session-2", turnId="turn-fixed", userId="auth-user"),
        Principal(user_id="auth-user", is_anonymous=False),
    )
    await asyncio.wait_for(runtime.cancelled.wait(), timeout=1)
    await asyncio.wait_for(consumer, timeout=1)


@pytest.mark.asyncio
async def test_chat_stream_caches_sse_frames_to_redis(monkeypatch):
    redis = _FakeRedis()
    monkeypatch.setattr(chat_stream_cache, "get_redis_client", lambda for_write=True: redis)
    monkeypatch.setattr(chat_service, "generate_turn_id", lambda: "turn-fixed")

    response = await chat(
        ChatRequest(query="回答我", session_id="session-3", user_id="body-user"),
        Principal(user_id="auth-user", is_anonymous=False),
        SimpleNamespace(runtime=_StreamingRuntime()),
    )
    chunks = [chunk async for chunk in response.body_iterator]
    events = _parse_sse(chunks)

    assert events[-1]["event"] == "end"
    assert [json.loads(value)["frame"]["event"] for _, value in redis.rpush_calls] == ["init", "content", "end"]
    assert redis.expire_calls == [
        ("chat:sse:events:session-3:turn-fixed", 600),
        ("chat:sse:events:session-3:turn-fixed", 600),
        ("chat:sse:events:session-3:turn-fixed", 600),
    ]


@pytest.mark.asyncio
async def test_chat_stream_ignores_redis_cache_failures(monkeypatch):
    monkeypatch.setattr(chat_stream_cache, "get_redis_client", lambda for_write=True: _FakeRedis(fail=True))
    monkeypatch.setattr(chat_service, "generate_turn_id", lambda: "turn-fixed")

    response = await chat(
        ChatRequest(query="回答我", session_id="session-4", user_id="body-user"),
        Principal(user_id="auth-user", is_anonymous=False),
        SimpleNamespace(runtime=_StreamingRuntime()),
    )
    chunks = [chunk async for chunk in response.body_iterator]
    events = _parse_sse(chunks)

    assert events[-1]["event"] == "end"


@pytest.mark.asyncio
async def test_chat_stream_reports_session_persist_failure():
    runtime = _StreamingRuntime()

    response = await chat(
        ChatRequest(query="回答我", session_id="session-1", user_id="body-user"),
        Principal(user_id="auth-user", is_anonymous=False),
        SimpleNamespace(runtime=runtime, session_store=_FailingTurnStore()),
    )
    chunks = [chunk async for chunk in response.body_iterator]
    events = _parse_sse(chunks)

    assert events[-1]["event"] == "error"
    assert "session persist failed" in events[-1]["data"]["msg"]
    assert all(event["event"] != "end" for event in events)


@pytest.mark.asyncio
async def test_chat_stream_can_replay_by_turn_id(monkeypatch):
    redis = _FakeRedis(
        values=[
            json.dumps(
                {
                    "frame": {
                        "event": "init",
                        "id": "turn-replay_1",
                        "data": {"protocol": {"sessionId": "session-9", "turnId": "turn-replay"}},
                    }
                }
            ),
            json.dumps(
                {
                    "frame": {
                        "event": "content",
                        "id": "turn-replay_2",
                        "data": {"protocol": {"sessionId": "session-9", "turnId": "turn-replay"}, "text": "重放"},
                    }
                }
            ),
        ]
    )
    monkeypatch.setattr(chat_stream_cache, "get_redis_client", lambda for_write=True: redis)

    response = await chat(
        ChatRequest(sessionId="session-9", turnId="turn-replay", userId="body-user"),
        Principal(user_id="auth-user", is_anonymous=False),
        SimpleNamespace(runtime=_StreamingRuntime()),
    )
    chunks = [chunk async for chunk in response.body_iterator]
    events = _parse_sse(chunks)

    assert [event["event"] for event in events] == ["init", "content"]


@pytest.mark.asyncio
async def test_resume_chat_stream_emits_ndjson_continuation_events():
    class Runtime:
        async def resume_stream_with_approval(self, **kwargs):
            self.kwargs = kwargs
            yield {"event": "init", "data": {"model": "gpt-4o-mini"}}
            yield {"event": "content", "data": {"text": "继续"}}
            yield {"event": "end", "data": {"status": "success", "model": "gpt-4o-mini", "output": "继续完成"}}

    runtime = Runtime()
    request = ChatResumeRequest(
        run_state={"snapshot": True},
        interruption_index=0,
        approved=True,
        session_id="session-1",
        turn_id="turn-1",
        message="查询天气",
        model="gpt-4o-mini",
    )

    response = await resume_chat_stream(
        request,
        Principal(user_id="auth-user", is_anonymous=False),
        SimpleNamespace(runtime=runtime),
    )
    chunks = [chunk async for chunk in response.body_iterator]
    events = _parse_sse(chunks)

    assert response.media_type == "text/event-stream"
    assert events[1]["event"] == "content"
    assert events[1]["data"]["text"] == "继续"
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
        turn_id="turn-1",
        message="删除数据",
        model="gpt-4o-mini",
    )

    response = await resume_chat_stream(
        request,
        Principal(user_id="anonymous", is_anonymous=True),
        SimpleNamespace(runtime=Runtime()),
    )
    chunks = [chunk async for chunk in response.body_iterator]
    events = _parse_sse(chunks)

    assert events == [
        {
            "event": "error",
            "data": {
                "protocol": {"sessionId": "session-1", "turnId": "turn-1"},
                "code": "chatError",
                "msg": "审批中断不存在: 3",
            },
        }
    ]
