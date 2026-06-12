from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.api.middleware.auth.base import Principal
from src.api.routers.memory import MemorySearchRequest, search_memories


@pytest.mark.asyncio
async def test_memory_search_rejects_cross_user_without_admin_scope():
    harness = SimpleNamespace(memory_manager=SimpleNamespace(search_memories=AsyncMock()))

    with pytest.raises(HTTPException) as exc:
        await search_memories(
            MemorySearchRequest(query="pref", user_id="other-user"),
            principal=Principal(user_id="auth-user", is_anonymous=False),
            harness=harness,
        )

    assert exc.value.status_code == 403
    harness.memory_manager.search_memories.assert_not_awaited()


@pytest.mark.asyncio
async def test_memory_search_allows_admin_cross_user_access():
    manager = SimpleNamespace(search_memories=AsyncMock(return_value=[{"content": "memory"}]))
    harness = SimpleNamespace(memory_manager=manager)

    response = await search_memories(
        MemorySearchRequest(query="pref", user_id="other-user"),
        principal=Principal(user_id="auth-user", scopes=["memory:admin"], is_anonymous=False),
        harness=harness,
    )

    assert response.data["user_id"] == "other-user"
    assert response.data["results"] == [{"content": "memory"}]
    manager.search_memories.assert_awaited_once_with(user_id="other-user", query="pref", top_k=5)
