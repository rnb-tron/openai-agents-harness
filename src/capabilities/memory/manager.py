"""
Memory Manager
统一记忆管理入口 - 协调短期、长期记忆和向量检索
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.capabilities.memory.store import ShortTermMemory
from src.capabilities.memory.repository import MemoryRepository
from src.capabilities.memory.embeddings import EmbeddingProvider, OpenAIEmbeddingProvider
from src.capabilities.memory.postgres_vector_store import PostgresVectorStore
from src.capabilities.memory.vector_store import ElasticsearchVectorStore, VectorStore
from src.capabilities.memory.context_manager import ContextManager
from src.capabilities.memory.lifecycle import MemoryLifecycleManager
from src.core.logging import service_logger
from src.core.config import Settings


class MemoryManager:
    """记忆管理器 - 统一入口"""

    def __init__(
        self,
        settings: Settings,
        db_session: AsyncSession,
        embedding_provider: EmbeddingProvider | None = None,
    ):
        """
        初始化记忆管理器

        Args:
            settings: 应用配置
            db_session: 数据库会话
        """
        self.settings = settings
        self.db_session = db_session

        # 1. 初始化短期记忆 (Redis)
        self.short_term = ShortTermMemory(
            redis_client=None,  # 需要从外部注入
            ttl=settings.memory_short_term_ttl,
        )

        # 2. 初始化长期记忆关系仓库 (由 DATABASE_URL 选择 MySQL / PostgreSQL)
        self.repository = MemoryRepository(db_session)

        # 3. 初始化可选向量存储 (ES / PostgreSQL pgvector)
        self.vector_store = self._build_vector_store()
        self.embedding_provider = embedding_provider or self._build_embedding_provider()

        # 4. 初始化上下文管理器
        self.context_manager = ContextManager(
            short_term=self.short_term,
            repository=self.repository,
            vector_store=self.vector_store,
            max_tokens=8000,  # 可根据模型调整
            embedding_provider=self.embedding_provider,
        )

        # 5. 初始化生命周期管理器
        self.lifecycle = MemoryLifecycleManager(
            repository=self.repository,
            importance_threshold=settings.memory_importance_threshold,
        )

        vector_backend = self.vector_store.backend_name if self.vector_store else "none"
        embedding_backend = (
            self.embedding_provider.provider_name if self.embedding_provider else "none"
        )
        service_logger.info(
            f"MemoryManager initialized: vector_backend={vector_backend}, "
            f"embedding_provider={embedding_backend}"
        )

    def _build_vector_store(self) -> VectorStore | None:
        if not self.settings.memory_long_term_enabled:
            return None

        backend = getattr(self.settings, "memory_vector_backend", "none").strip().lower()
        if backend == "elasticsearch":
            return ElasticsearchVectorStore(
                hosts=self.settings.memory_es_hosts,
                index_name=self.settings.memory_es_index,
                dimension=self.settings.memory_vector_dimension,
            )
        if backend in ("", "none"):
            return None
        if backend == "pgvector":
            database_url = getattr(self.settings, "database_url", "")
            if not database_url.startswith(("postgresql", "postgres")):
                raise ValueError(
                    "MEMORY_VECTOR_BACKEND=pgvector requires a PostgreSQL DATABASE_URL"
                )
            return PostgresVectorStore(
                session=self.db_session,
                table_name=getattr(self.settings, "memory_pgvector_table", "memory_vectors"),
                dimension=self.settings.memory_vector_dimension,
            )
        raise ValueError(f"Unsupported MEMORY_VECTOR_BACKEND: {backend}")

    def _build_embedding_provider(self) -> EmbeddingProvider | None:
        if not self.settings.memory_long_term_enabled or not self.vector_store:
            return None

        provider = getattr(self.settings, "memory_embedding_provider", "none").strip().lower()
        if provider in ("", "none"):
            return None
        if provider == "openai":
            return OpenAIEmbeddingProvider(
                api_key=getattr(self.settings, "openai_api_key", ""),
                base_url=getattr(self.settings, "openai_base_url", None),
                model=getattr(
                    self.settings,
                    "memory_embedding_model",
                    "text-embedding-3-small",
                ),
                dimension=self.settings.memory_vector_dimension,
            )
        raise ValueError(f"Unsupported MEMORY_EMBEDDING_PROVIDER: {provider}")

    async def init(self) -> None:
        """初始化记忆系统并创建所选向量后端的索引结构。"""
        try:
            if self.vector_store:
                await self.vector_store.create_index()
                service_logger.info(
                    f"Vector store initialized: backend={self.vector_store.backend_name}"
                )

            service_logger.info("Memory system initialized successfully")

        except Exception as e:
            service_logger.error(f"Failed to initialize memory system: {e}", exc_info=True)
            raise

    async def add_memory(
        self,
        session_id: str,
        user_id: str,
        role: str,
        content: str,
        memory_type: str = "long_term",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        添加记忆

        流程:
        1. 写入短期记忆 (Redis)
        2. 写入长期记忆关系仓库
        3. 在配置嵌入生成器后，生成向量并写入所选向量存储

        Args:
            session_id: 会话ID
            user_id: 用户ID
            role: 角色 (user/assistant/system)
            content: 记忆内容
            memory_type: 记忆类型
            metadata: 扩展元数据

        Returns:
            bool: 是否成功
        """
        try:
            # 1. 写入短期记忆
            await self.short_term.append(session_id, role, content, metadata)

            # 2. 写入长期记忆关系仓库
            record = await self.repository.create(
                user_id=user_id,
                session_id=session_id,
                role=role,
                content=content,
                memory_type=memory_type,
                metadata=metadata,
            )

            # 3. 向量检索是可选增强；失败时保留关系记录并降级为非语义记忆。
            if self.vector_store and self.embedding_provider and memory_type == "long_term":
                try:
                    embedding = await self.embedding_provider.embed(content)
                    indexed = await self.vector_store.upsert(
                        memory_id=str(record.id),
                        embedding=embedding,
                        user_id=user_id,
                        session_id=session_id,
                        memory_type=memory_type,
                        role=role,
                        content=content,
                        metadata=metadata,
                    )
                    if not indexed:
                        service_logger.warning(
                            f"Vector storage failed open: memory_id={record.id}"
                        )
                except Exception as exc:
                    service_logger.warning(
                        f"Embedding/vector storage failed open: memory_id={record.id}, "
                        f"error={exc}"
                    )

            await self.db_session.commit()
            service_logger.info(f"Memory added: session={session_id}, user={user_id}, role={role}")
            return True

        except Exception as e:
            service_logger.error(f"Failed to add memory: {e}", exc_info=True)
            return False

    async def get_context(
        self,
        session_id: str,
        user_id: str,
        user_input: str,
        max_turns: int | None = None,
        enable_retrieval: bool = True,
    ) -> str:
        """
        获取上下文

        Args:
            session_id: 会话ID
            user_id: 用户ID
            user_input: 当前用户输入
            max_turns: 最大对话轮数 (默认使用配置)
            enable_retrieval: 是否启用长期记忆检索

        Returns:
            str: 格式化后的上下文
        """
        return await self.context_manager.build_context(
            session_id=session_id,
            user_id=user_id,
            user_input=user_input,
            max_turns=max_turns or self.settings.memory_max_context_turns,
            enable_retrieval=enable_retrieval and self.settings.memory_long_term_enabled,
            retrieval_top_k=self.settings.memory_retrieval_top_k,
        )

    async def search_memories(
        self,
        user_id: str,
        query: str,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        搜索记忆

        Args:
            user_id: 用户ID
            query: 查询内容
            top_k: 返回数量 (默认使用配置)

        Returns:
            list[dict]: 搜索结果
        """
        try:
            if not self.vector_store or not self.embedding_provider:
                return []

            query_embedding = await self.embedding_provider.embed(query)
            candidates = await self.vector_store.search(
                query_embedding=query_embedding,
                top_k=top_k or self.settings.memory_retrieval_top_k,
                user_id=user_id,
            )
            results = []
            for memory in candidates:
                memory_id = int(memory["memory_id"])
                if await self.repository.get_by_id(memory_id):
                    results.append(memory)
                    await self.repository.increment_access(memory_id)
            return results

        except Exception as e:
            service_logger.error(f"Failed to search memories: {e}", exc_info=True)
            return []

    async def clear_session(self, session_id: str) -> bool:
        """
        清空会话记忆

        Args:
            session_id: 会话ID

        Returns:
            bool: 是否成功
        """
        try:
            # 清空短期记忆
            await self.short_term.clear(session_id)

            # 软删除长期记忆，同时尽力回收对应向量。
            memory_ids = await self.repository.list_ids_by_session(session_id)
            await self.repository.batch_delete_by_session(session_id)
            if self.vector_store and memory_ids:
                await self.vector_store.delete([str(memory_id) for memory_id in memory_ids])
            await self.db_session.commit()

            service_logger.info(f"Session memory cleared: {session_id}")
            return True

        except Exception as e:
            service_logger.error(f"Failed to clear session memory: {e}", exc_info=True)
            return False

    async def get_stats(self, user_id: str | None = None) -> dict:
        """
        获取记忆统计信息

        Args:
            user_id: 用户ID (可选)

        Returns:
            dict: 统计信息
        """
        try:
            return await self.repository.get_stats(user_id)

        except Exception as e:
            service_logger.error(f"Failed to get memory stats: {e}", exc_info=True)
            return {"error": str(e)}

    async def cleanup_old_memories(self) -> dict:
        """
        清理旧记忆 (执行维护任务)

        Returns:
            dict: 清理统计
        """
        try:
            if not self.settings.memory_forgetting_enabled:
                return {"skipped": True, "reason": "Forgetting policy disabled"}

            result = await self.lifecycle.run_maintenance()
            service_logger.info(f"Memory cleanup completed: {result}")
            return result

        except Exception as e:
            service_logger.error(f"Failed to cleanup old memories: {e}", exc_info=True)
            return {"error": str(e)}

    async def close(self) -> None:
        """关闭记忆系统"""
        try:
            if self.vector_store:
                await self.vector_store.close()
            service_logger.info("Memory system closed")

        except Exception as e:
            service_logger.error(f"Failed to close memory system: {e}", exc_info=True)
