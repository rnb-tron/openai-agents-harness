"""Memory capabilities."""

from src.capabilities.memory.store import ShortTermMemory, MemoryStore

try:
    from src.capabilities.memory.models import MemoryRecord
    from src.capabilities.memory.repository import MemoryRepository
    from src.capabilities.memory.vector_store import ElasticsearchVectorStore, VectorStore
    from src.capabilities.memory.postgres_vector_store import PostgresVectorStore
    from src.capabilities.memory.embeddings import EmbeddingProvider, OpenAIEmbeddingProvider
    from src.capabilities.memory.lifecycle import MemoryLifecycleManager
    from src.capabilities.memory.context_manager import ContextManager
    from src.capabilities.memory.manager import MemoryManager
    from src.capabilities.memory.capability import (
        LongTermMemoryCapability,
        MemoryCapability,
        VectorSearchCapability,
    )
except ImportError:  # pragma: no cover - optional dependencies may be absent in minimal installs
    MemoryRecord = None
    MemoryRepository = None
    ElasticsearchVectorStore = None
    PostgresVectorStore = None
    VectorStore = None
    EmbeddingProvider = None
    OpenAIEmbeddingProvider = None
    MemoryLifecycleManager = None
    ContextManager = None
    MemoryManager = None
    MemoryCapability = None
    LongTermMemoryCapability = None
    VectorSearchCapability = None

__all__ = [
    "ShortTermMemory",
    "MemoryStore",
    "MemoryRecord",
    "MemoryRepository",
    "ElasticsearchVectorStore",
    "PostgresVectorStore",
    "VectorStore",
    "EmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "MemoryLifecycleManager",
    "ContextManager",
    "MemoryManager",
    "MemoryCapability",
    "LongTermMemoryCapability",
    "VectorSearchCapability",
]
