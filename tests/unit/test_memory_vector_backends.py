from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.capabilities.memory.embeddings import OpenAIEmbeddingProvider
from src.capabilities.memory.manager import MemoryManager
from src.capabilities.memory.postgres_vector_store import PostgresVectorStore
from src.capabilities.memory.vector_store import ElasticsearchVectorStore


def _settings(**overrides):
    defaults = dict(
        database_url="",
        memory_long_term_enabled=True,
        memory_vector_backend="none",
        memory_pgvector_table="memory_vectors",
        memory_embedding_provider="none",
        memory_embedding_model="text-embedding-3-small",
        memory_short_term_ttl=3600,
        memory_es_hosts="http://localhost:9200",
        memory_es_index="agent_memories",
        memory_vector_dimension=3,
        memory_importance_threshold=0.3,
        memory_retrieval_top_k=3,
        openai_api_key="",
        openai_base_url=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_memory_manager_does_not_create_vector_backend_by_default():
    manager = MemoryManager(_settings(), AsyncMock())

    assert manager.vector_store is None


def test_memory_manager_selects_elasticsearch_when_configured():
    manager = MemoryManager(
        _settings(memory_vector_backend="elasticsearch"),
        AsyncMock(),
    )

    assert isinstance(manager.vector_store, ElasticsearchVectorStore)
    assert manager.vector_store.backend_name == "elasticsearch"


def test_memory_manager_selects_pgvector_for_postgres_database():
    manager = MemoryManager(
        _settings(
            database_url="postgresql+asyncpg://agent:secret@localhost/agent",
            memory_vector_backend="pgvector",
        ),
        AsyncMock(),
    )

    assert isinstance(manager.vector_store, PostgresVectorStore)
    assert manager.vector_store.backend_name == "pgvector"


def test_pgvector_backend_requires_postgres_database_url():
    with pytest.raises(ValueError, match="PostgreSQL DATABASE_URL"):
        MemoryManager(
            _settings(
                database_url="mysql+aiomysql://agent:secret@localhost/agent",
                memory_vector_backend="pgvector",
            ),
            AsyncMock(),
        )


@pytest.mark.asyncio
async def test_pgvector_store_creates_extension_and_upserts_vector_metadata():
    session = AsyncMock()
    store = PostgresVectorStore(session=session, dimension=3)

    await store.create_index()
    success = await store.upsert(
        memory_id="memory-1",
        embedding=[0.1, 0.2, 0.3],
        user_id="user-1",
        session_id="session-1",
        memory_type="long_term",
        role="user",
        content="记住我的偏好",
        metadata={"source": "chat"},
    )

    statements = [str(call.args[0]) for call in session.execute.await_args_list]
    upsert_params = session.execute.await_args_list[-1].args[1]

    assert any("CREATE EXTENSION IF NOT EXISTS vector" in sql for sql in statements)
    assert any("CREATE TABLE IF NOT EXISTS memory_vectors" in sql for sql in statements)
    assert session.commit.await_count == 1
    assert success is True
    assert upsert_params["embedding"] == "[0.1,0.2,0.3]"
    assert '"content": "记住我的偏好"' in upsert_params["metadata"]


@pytest.mark.asyncio
async def test_pgvector_store_rejects_wrong_vector_dimension():
    store = PostgresVectorStore(session=AsyncMock(), dimension=3)

    success = await store.upsert(
        memory_id="memory-1",
        embedding=[0.1],
        user_id="user-1",
        session_id="session-1",
        memory_type="long_term",
        role="user",
        content="content",
    )

    assert success is False


@pytest.mark.asyncio
async def test_pgvector_store_searches_with_metadata_and_filters():
    session = AsyncMock()
    session.execute.return_value = [
        SimpleNamespace(
            memory_id="memory-1",
            score=0.91,
            user_id="user-1",
            session_id="session-1",
            memory_type="long_term",
            role="user",
            metadata={"content": "偏好中文"},
        )
    ]
    store = PostgresVectorStore(session=session, dimension=3)

    results = await store.search(
        query_embedding=[0.1, 0.2, 0.3],
        user_id="user-1",
        memory_type="long_term",
    )

    statement = str(session.execute.await_args.args[0])
    params = session.execute.await_args.args[1]

    assert "embedding <=> CAST(:embedding AS vector)" in statement
    assert "user_id = :user_id" in statement
    assert "memory_type = :memory_type" in statement
    assert params["embedding"] == "[0.1,0.2,0.3]"
    assert results[0]["metadata"]["content"] == "偏好中文"


@pytest.mark.asyncio
async def test_openai_embedding_provider_returns_dimension_checked_vectors():
    client = SimpleNamespace(
        embeddings=SimpleNamespace(
            create=AsyncMock(
                return_value=SimpleNamespace(
                    data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])]
                )
            )
        )
    )
    provider = OpenAIEmbeddingProvider(
        api_key="",
        model="text-embedding-3-small",
        dimension=3,
        client=client,
    )

    result = await provider.embed("偏好中文")

    assert result == [0.1, 0.2, 0.3]
    client.embeddings.create.assert_awaited_once_with(
        model="text-embedding-3-small",
        input="偏好中文",
        dimensions=3,
    )


def test_openai_embedding_provider_requires_api_key_when_not_injected():
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        OpenAIEmbeddingProvider(api_key="", dimension=3)


@pytest.mark.asyncio
async def test_memory_manager_embeds_and_indexes_long_term_memory():
    provider = SimpleNamespace(provider_name="fake", embed=AsyncMock(return_value=[0.1, 0.2, 0.3]))
    session = AsyncMock()
    manager = MemoryManager(_settings(memory_vector_backend="none"), session, provider)
    manager.vector_store = AsyncMock(backend_name="pgvector")
    manager.repository = AsyncMock()
    manager.repository.create.return_value = SimpleNamespace(id=42)

    success = await manager.add_memory(
        session_id="session-1",
        user_id="user-1",
        role="user",
        content="记住我偏好中文",
    )

    assert success is True
    provider.embed.assert_awaited_once_with("记住我偏好中文")
    manager.vector_store.upsert.assert_awaited_once()
    assert manager.vector_store.upsert.await_args.kwargs["memory_id"] == "42"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_memory_manager_search_filters_soft_deleted_vector_results():
    provider = SimpleNamespace(provider_name="fake", embed=AsyncMock(return_value=[0.1, 0.2, 0.3]))
    manager = MemoryManager(_settings(memory_vector_backend="none"), AsyncMock(), provider)
    manager.vector_store = AsyncMock(backend_name="pgvector")
    manager.vector_store.search.return_value = [
        {"memory_id": "42", "score": 0.9},
        {"memory_id": "43", "score": 0.8},
    ]
    manager.repository = AsyncMock()
    manager.repository.get_by_id.side_effect = [object(), None]

    results = await manager.search_memories("user-1", "中文")

    assert results == [{"memory_id": "42", "score": 0.9}]
    provider.embed.assert_awaited_once_with("中文")
    manager.repository.increment_access.assert_awaited_once_with(42)


@pytest.mark.asyncio
async def test_memory_manager_clears_vectors_with_session_records():
    manager = MemoryManager(_settings(memory_vector_backend="none"), AsyncMock())
    manager.vector_store = AsyncMock(backend_name="pgvector")
    manager.repository = AsyncMock()
    manager.repository.list_ids_by_session.return_value = [42, 43]

    success = await manager.clear_session("session-1")

    assert success is True
    manager.vector_store.delete.assert_awaited_once_with(["42", "43"])
