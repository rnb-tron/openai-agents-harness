from types import SimpleNamespace

import pytest

from src.capabilities.session_store import SessionStore
from src.infrastructure.database import DatabaseConfig, DatabaseResource

pytest.importorskip("aiosqlite")


@pytest.mark.asyncio
async def test_session_store_persists_sessions_and_messages(tmp_path):
    database = DatabaseResource(
        DatabaseConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}")
    )
    await database.create_all()
    store = SessionStore(database.session)

    await store.append_turn(
        session_id="session-1",
        user_id="user-1",
        user_input="我要去上海旅行",
        assistant_output="可以先看天气，再安排路线。",
        model="gpt-test",
        metadata={"source": "chat"},
    )

    sessions = await store.list_sessions(user_id="user-1")
    messages = await store.list_messages(session_id="session-1")

    assert sessions[0]["id"] == "session-1"
    assert sessions[0]["title"] == "我要去上海旅行"
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert messages[1]["model"] == "gpt-test"

    await database.close()


@pytest.mark.asyncio
async def test_session_store_creates_empty_session(tmp_path):
    database = DatabaseResource(
        DatabaseConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}")
    )
    await database.create_all()
    store = SessionStore(database.session)

    session = await store.create_session(
        session_id="session-empty",
        user_id="user-1",
        title="新会话",
        metadata={"source": "ui"},
    )
    sessions = await store.list_sessions(user_id="user-1")
    messages = await store.list_messages(session_id="session-empty")

    assert session["id"] == "session-empty"
    assert session["title"] == "新会话"
    assert session["metadata"]["source"] == "ui"
    assert sessions[0]["id"] == "session-empty"
    assert messages == []

    await database.close()


@pytest.mark.asyncio
async def test_session_store_deletes_session_and_messages(tmp_path):
    database = DatabaseResource(
        DatabaseConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}")
    )
    await database.create_all()
    store = SessionStore(database.session)

    await store.append_turn(
        session_id="session-1",
        user_id="user-1",
        user_input="请记住我的偏好",
        assistant_output="已记住。",
    )

    assert await store.delete_session("session-1") is True
    assert await store.get_session("session-1") is None
    assert await store.list_messages(session_id="session-1") == []
    assert await store.delete_session("session-1") is False

    await database.close()


@pytest.mark.asyncio
async def test_session_store_upserts_session_summary(tmp_path):
    database = DatabaseResource(
        DatabaseConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}")
    )
    await database.create_all()
    store = SessionStore(database.session)

    created = await store.upsert_summary(
        session_id="session-1",
        user_id="user-1",
        summary="当前任务：验证摘要",
        covered_message_count=4,
        model="gpt-test",
    )
    updated = await store.upsert_summary(
        session_id="session-1",
        user_id="user-1",
        summary="当前任务：验证更新后的摘要",
        covered_message_count=8,
        model="gpt-test",
    )
    loaded = await store.get_summary("session-1")

    assert created["version"] == 1
    assert updated["version"] == 2
    assert loaded["summary"] == "当前任务：验证更新后的摘要"
    assert loaded["covered_message_count"] == 8

    await database.close()


def test_session_store_is_plain_resource_for_harness():
    settings = SimpleNamespace(
        database_url="mysql+aiomysql://agent:secret@localhost/agent",
        debug=False,
        database_pool_size=5,
        database_max_overflow=0,
        database_pool_timeout_seconds=30,
        database_pool_recycle_seconds=1800,
        database_pool_pre_ping=True,
    )

    config = DatabaseConfig.from_settings(settings)

    assert config.url == "mysql+aiomysql://agent:secret@localhost/agent"
