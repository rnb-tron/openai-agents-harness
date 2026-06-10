from types import SimpleNamespace

import pytest

from src.capabilities.session_store import SessionStore
from src.infrastructure.database import DatabaseConfig, DatabaseResource

pytest.importorskip("aiosqlite")


@pytest.mark.asyncio
async def test_session_store_persists_sessions_and_messages(tmp_path):
    database = DatabaseResource(DatabaseConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}"))
    await database.create_all()
    store = SessionStore(database.session)

    await store.append_turn(
        session_id="session-1",
        user_id="user-1",
        user_input="我要去上海旅行",
        assistant_output="可以先看天气，再安排路线。",
        turn_id="turn-1",
        model="gpt-test",
        metadata={"source": "chat", "msg_id": "legacy-msg"},
    )

    sessions = await store.list_sessions(user_id="user-1")
    messages = await store.list_messages(session_id="session-1")

    assert sessions[0]["id"] == "session-1"
    assert sessions[0]["title"] == "我要去上海旅行"
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert [item["turn_id"] for item in messages] == ["turn-1", "turn-1"]
    assert messages[1]["model"] == "gpt-test"
    assert messages[1]["metadata"] == {"source": "chat"}

    await database.close()


@pytest.mark.asyncio
async def test_session_store_lists_recent_messages_in_chat_order(tmp_path):
    database = DatabaseResource(DatabaseConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}"))
    await database.create_all()
    store = SessionStore(database.session)

    for index in range(3):
        await store.append_turn(
            session_id="session-1",
            user_id="user-1",
            user_input=f"用户消息 {index}",
            assistant_output=f"助手消息 {index}",
        )

    recent = await store.list_recent_messages(session_id="session-1", limit=2)
    count = await store.count_messages("session-1")

    assert count == 6
    assert [item["content"] for item in recent] == ["用户消息 2", "助手消息 2"]

    await database.close()


@pytest.mark.asyncio
async def test_session_store_keeps_repeated_user_inputs_as_separate_turns(tmp_path):
    database = DatabaseResource(DatabaseConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}"))
    await database.create_all()
    store = SessionStore(database.session)

    await store.append_turn(
        session_id="session-1",
        user_id="user-1",
        user_input="介绍下三国演义这部小说",
        assistant_output="《三国演义》是中国古典小说。",
        model="qwen3.5-plus",
    )
    await store.append_turn(
        session_id="session-1",
        user_id="user-1",
        user_input="以后回答尽量使用英文",
        assistant_output="Understood. I will use English for my responses from now on.",
        model="qwen3.5-plus",
    )
    await store.append_turn(
        session_id="session-1",
        user_id="user-1",
        user_input="以后回答尽量使用英文",
        assistant_output="Understood. I will continue to respond in English as requested.",
        model="qwen3.5-plus",
    )

    messages = await store.list_messages(session_id="session-1")
    recent = await store.list_recent_messages(session_id="session-1", limit=6)

    assert await store.count_messages("session-1") == 6
    assert [item["role"] for item in messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert [item["content"] for item in messages] == [item["content"] for item in recent]
    assert messages[2]["content"] == "以后回答尽量使用英文"
    assert messages[4]["content"] == "以后回答尽量使用英文"
    assert messages[3]["content"] != messages[5]["content"]

    await database.close()


@pytest.mark.asyncio
async def test_session_store_creates_empty_session(tmp_path):
    database = DatabaseResource(DatabaseConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}"))
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
    database = DatabaseResource(DatabaseConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}"))
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
    database = DatabaseResource(DatabaseConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}"))
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
