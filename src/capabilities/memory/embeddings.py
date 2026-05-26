"""可替换的记忆嵌入生成器。"""

from __future__ import annotations

from typing import Any, Protocol

from openai import AsyncOpenAI


class EmbeddingProvider(Protocol):
    """MemoryManager 使用的最小嵌入能力边界。"""

    provider_name: str

    async def embed(self, text: str) -> list[float]: ...


class OpenAIEmbeddingProvider:
    """使用 OpenAI Embeddings API 生成记忆向量。"""

    provider_name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimension: int = 1536,
        base_url: str | None = None,
        client: Any | None = None,
    ) -> None:
        if not api_key and client is None:
            raise ValueError("OPENAI_API_KEY is required for OpenAI memory embeddings")
        if dimension <= 0:
            raise ValueError("MEMORY_VECTOR_DIMENSION must be greater than zero")

        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self.client = client or AsyncOpenAI(**client_kwargs)
        self.model = model
        self.dimension = dimension

    async def embed(self, text: str) -> list[float]:
        if not text.strip():
            raise ValueError("Cannot generate an embedding for empty text")

        response = await self.client.embeddings.create(
            model=self.model,
            input=text,
            dimensions=self.dimension,
        )
        embedding = list(response.data[0].embedding)
        if len(embedding) != self.dimension:
            raise ValueError(
                f"Expected embedding dimension {self.dimension}, got {len(embedding)}"
            )
        return embedding
