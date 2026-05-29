from types import SimpleNamespace

import pytest

from src.capabilities.memory.mem0_manager import Mem0MemoryManager


class _FakeMem0Client:
    def __init__(self):
        self.add_calls = []
        self.search_calls = []

    def add(self, messages, **kwargs):
        self.add_calls.append({"messages": messages, **kwargs})
        return {"results": [{"memory": "stored"}]}

    def search(self, *args, **kwargs):
        query = kwargs.get("query") or (args[0] if args else "")
        self.search_calls.append({"query": query, **kwargs})
        return {
            "results": [
                {"memory": f"memory for {query}", "score": 0.9},
            ]
        }


class _FakeSummaryClient:
    def __init__(self, content="结构化会话摘要"):
        self.calls = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )
        self._content = content

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content=self._content))
            ]
        )


class _FakeSessionStore:
    def __init__(self, summary=None):
        self.summary = summary
        self.upsert_calls = []
        self.get_calls = 0

    async def get_summary(self, session_id):
        self.get_calls += 1
        return self.summary

    async def upsert_summary(self, **kwargs):
        self.upsert_calls.append(kwargs)
        self.summary = {
            "session_id": kwargs["session_id"],
            "user_id": kwargs["user_id"],
            "summary": kwargs["summary"],
            "covered_message_count": kwargs["covered_message_count"],
            "model": kwargs["model"],
            "version": 1,
            "metadata": kwargs.get("metadata") or {},
        }
        return self.summary


def _settings(**overrides):
    defaults = dict(
        memory_short_term_ttl=3600,
        memory_max_context_turns=6,
        memory_retrieval_top_k=3,
        memory_preference_cache_ttl_sec=900,
        memory_mem0_mode="local",
        memory_mem0_api_key="",
        memory_mem0_config_json="",
        memory_vector_store="none",
        memory_pgvector_database_url="",
        memory_pgvector_table="agent_memories",
        memory_es_hosts="http://localhost:9200",
        memory_es_index="agent_memories",
        openai_api_key="test-key",
        openai_base_url=None,
        agent_model_default="gpt-4o-mini",
        memory_embedding_model="text-embedding-3-small",
        memory_vector_dimension=1536,
        memory_session_summary_enabled=False,
        memory_session_summary_cache_ttl=2592000,
        memory_session_summary_initial_messages=4,
        memory_session_summary_update_messages=6,
        memory_session_summary_model="",
        memory_session_summary_max_tokens=512,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_mem0_manager_persists_meaningful_user_assistant_pair():
    client = _FakeMem0Client()
    manager = Mem0MemoryManager(_settings(), client=client)

    assert await manager.add_memory("s1", "u1", "user", "请记住我的偏好是中文回答")
    assert client.add_calls == []

    assert await manager.add_memory("s1", "u1", "assistant", "好的，之后我会优先用中文回答。")

    assert len(client.add_calls) == 1
    call = client.add_calls[0]
    assert call["user_id"] == "u1"
    assert call["run_id"] == "s1"
    assert call["messages"][0]["role"] == "user"
    assert call["messages"][1]["role"] == "assistant"
    assert call["metadata"]["source_session_id"] == "s1"
    assert "memory_kind" not in call["metadata"]
    assert "preference_key" not in call["metadata"]


@pytest.mark.asyncio
async def test_mem0_manager_skips_low_value_long_term_write():
    client = _FakeMem0Client()
    manager = Mem0MemoryManager(_settings(), client=client)

    await manager.add_memory("s1", "u1", "user", "好的")
    await manager.add_memory("s1", "u1", "assistant", "收到")

    assert client.add_calls == []
    assert await manager.short_term.get_recent("s1", 2)


@pytest.mark.asyncio
async def test_mem0_manager_submits_meaningful_pair_to_mem0_without_keyword_gate():
    client = _FakeMem0Client()
    manager = Mem0MemoryManager(_settings(), client=client)

    await manager.add_memory("s1", "u1", "user", "我最近在做一个面向管理者的 agent harness 验收页面")
    await manager.add_memory("s1", "u1", "assistant", "明白，这类页面应该突出能力装配、运行链路和可验证结果。")

    assert len(client.add_calls) == 1
    call = client.add_calls[0]
    assert call["messages"][0]["content"] == "我最近在做一个面向管理者的 agent harness 验收页面"
    assert "memory_kind" not in call["metadata"]


@pytest.mark.asyncio
async def test_mem0_manager_filters_failed_or_rejected_outputs_before_mem0():
    client = _FakeMem0Client()
    manager = Mem0MemoryManager(_settings(), client=client)

    await manager.add_memory("s1", "u1", "user", "查询上海天气")
    await manager.add_memory("s1", "u1", "assistant", "工具调用失败: timeout")
    await manager.add_memory("s2", "u1", "user", "查询上海天气")
    await manager.add_memory("s2", "u1", "assistant", "操作已被拒绝，工具未运行。")

    assert client.add_calls == []


@pytest.mark.asyncio
async def test_mem0_manager_caches_preferences_and_gates_long_term_search():
    client = _FakeMem0Client()
    manager = Mem0MemoryManager(_settings(), client=client)

    context = await manager.get_context(
        session_id="s1",
        user_id="u1",
        user_input="这个项目的记忆架构应该怎么做？",
    )

    assert "=== User Preferences ===" in context
    assert "=== Relevant Long-Term Memories ===" in context
    assert len(client.search_calls) == 2

    client.search_calls.clear()
    context = await manager.get_context(
        session_id="s1",
        user_id="u1",
        user_input="好",
    )

    assert "user: 好" in context
    assert client.search_calls == []


@pytest.mark.asyncio
async def test_mem0_manager_keeps_latest_preference_per_key_in_context():
    client = _FakeMem0Client()
    client.search = lambda *args, **kwargs: {  # noqa: E731
        "results": [
            {
                "id": "old-language",
                "memory": "User prefers responses in Chinese and wants the conclusion first.",
                "metadata": {
                    "memory_kind": "preference",
                    "preference_keys": ["response_language", "answer_order"],
                    "updated_at": "2026-05-28T10:00:00+00:00",
                },
            },
            {
                "id": "new-language",
                "memory": "User prefers responses that present the conclusion first and use English as much as possible.",
                "metadata": {
                    "memory_kind": "preference",
                    "preference_keys": ["response_language", "answer_order"],
                    "updated_at": "2026-05-29T10:00:00+00:00",
                },
            },
        ]
    }
    manager = Mem0MemoryManager(_settings(), client=client)

    context = await manager.get_context(
        session_id="s1",
        user_id="u1",
        user_input="介绍一下当前项目",
        enable_retrieval=False,
    )

    assert "use English as much as possible" in context
    assert "responses in Chinese" not in context


def test_mem0_manager_infers_preference_keys_for_legacy_memories():
    memories = [
        {
            "content": "User prefers responses in Chinese and wants the conclusion presented first.",
            "created_at": "2026-05-28T10:00:00+00:00",
        },
        {
            "content": "User prefers responses that present the conclusion first and use English as much as possible.",
            "created_at": "2026-05-29T10:00:00+00:00",
        },
    ]

    selected = Mem0MemoryManager._select_effective_preferences(memories)

    assert len(selected) == 1
    assert "English" in selected[0]["content"]


@pytest.mark.asyncio
async def test_mem0_manager_filters_preference_search_results():
    client = _FakeMem0Client()
    client.search = lambda *args, **kwargs: {  # noqa: E731
        "results": [
            {
                "content": "User prefers responses in Chinese.",
                "created_at": "2026-05-28T10:00:00+00:00",
            },
            {
                "content": "User prefers responses in English.",
                "created_at": "2026-05-29T10:00:00+00:00",
            },
        ]
    }
    manager = Mem0MemoryManager(_settings(), client=client)

    results = await manager.search_memories("u1", "用户偏好", top_k=5)

    assert len(results) == 1
    assert "English" in results[0]["content"]


@pytest.mark.asyncio
async def test_mem0_manager_normalizes_platform_style_results():
    client = _FakeMem0Client()
    client.search = lambda *args, **kwargs: {  # noqa: E731
        "memories": [
            {"content": "偏好简洁回答", "id": "m1"},
            {"memory": "项目使用 Mem0", "id": "m2"},
        ]
    }
    manager = Mem0MemoryManager(_settings(), client=client)

    results = await manager.search_memories("u1", "偏好", top_k=2)

    assert [item["content"] for item in results] == ["偏好简洁回答", "项目使用 Mem0"]


@pytest.mark.asyncio
async def test_mem0_manager_reads_session_summary_from_store_without_rebuilding():
    store = _FakeSessionStore(
        summary={
            "session_id": "s1",
            "user_id": "u1",
            "summary": "当前任务：验证会话摘要",
            "covered_message_count": 8,
            "model": "gpt-test",
        }
    )
    summary_client = _FakeSummaryClient()
    manager = Mem0MemoryManager(
        _settings(memory_session_summary_enabled=True),
        client=_FakeMem0Client(),
        session_store=store,
        summary_client=summary_client,
    )

    context = await manager.get_context(
        session_id="s1",
        user_id="u1",
        user_input="继续",
        enable_retrieval=False,
    )

    assert "=== Session Summary ===" in context
    assert "当前任务：验证会话摘要" in context
    assert store.get_calls == 1
    assert store.upsert_calls == []
    assert summary_client.calls == []


@pytest.mark.asyncio
async def test_mem0_manager_updates_session_summary_after_threshold():
    store = _FakeSessionStore()
    summary_client = _FakeSummaryClient(content="当前任务：设计 memory summary")
    manager = Mem0MemoryManager(
        _settings(
            memory_session_summary_enabled=True,
            memory_session_summary_initial_messages=4,
        ),
        client=_FakeMem0Client(),
        session_store=store,
        summary_client=summary_client,
    )
    await manager.short_term.append("s1", "user", "我想设计短期摘要")
    await manager.short_term.append("s1", "assistant", "可以用 Redis 缓存和 MySQL 持久化")
    await manager.short_term.append("s1", "user", "summary 不要短 TTL")
    await manager.short_term.append("s1", "assistant", "MySQL 作为权威存储")

    updated = await manager.update_session_summary(session_id="s1", user_id="u1")

    assert updated is True
    assert len(summary_client.calls) == 1
    assert store.upsert_calls[0]["covered_message_count"] == 4
    assert store.upsert_calls[0]["summary"] == "当前任务：设计 memory summary"
    cached = await manager.short_term.get_summary("s1")
    assert cached["summary"] == "当前任务：设计 memory summary"


def test_mem0_manager_builds_pgvector_config_from_memory_database_url():
    manager = Mem0MemoryManager(
        _settings(
            memory_vector_store="pgvector",
            memory_pgvector_database_url="postgresql://user:pass@localhost/memory",
            memory_pgvector_table="agent_memories_test",
        ),
        client=_FakeMem0Client(),
    )

    config = manager._build_vector_store_config()

    assert config["provider"] == "pgvector"
    assert config["config"]["connection_string"].startswith("postgresql://")
    assert config["config"]["collection_name"] == "agent_memories_test"


def test_mem0_manager_local_config_injects_openai_base_url():
    manager = Mem0MemoryManager(
        _settings(
            openai_api_key="sk-test",
            openai_base_url="https://openapi-ait.ke.com/v1",
            agent_model_default="qwen3.5-plus",
            memory_embedding_model="text-embedding-3-small",
        ),
        client=_FakeMem0Client(),
    )

    config = manager._build_local_config()

    assert config["llm"]["config"] == {
        "api_key": "sk-test",
        "model": "qwen3.5-plus",
        "openai_base_url": "https://openapi-ait.ke.com/v1",
    }
    assert config["embedder"]["config"] == {
        "api_key": "sk-test",
        "model": "text-embedding-3-small",
        "openai_base_url": "https://openapi-ait.ke.com/v1",
    }


def test_mem0_manager_local_config_is_accepted_by_mem0_config_classes():
    from mem0.configs.embeddings.base import BaseEmbedderConfig
    from mem0.configs.llms.openai import OpenAIConfig

    manager = Mem0MemoryManager(
        _settings(openai_base_url="https://openapi-ait.ke.com/v1"),
        client=_FakeMem0Client(),
    )

    config = manager._build_local_config()

    OpenAIConfig(**config["llm"]["config"])
    BaseEmbedderConfig(**config["embedder"]["config"])


def test_mem0_manager_builds_elasticsearch_config():
    manager = Mem0MemoryManager(
        _settings(
            memory_vector_store="elasticsearch",
            memory_es_hosts="http://es:9200",
            memory_es_index="memories",
        ),
        client=_FakeMem0Client(),
    )

    config = manager._build_vector_store_config()

    assert config == {
        "provider": "elasticsearch",
        "config": {"host": "http://es:9200", "index_name": "memories"},
    }
