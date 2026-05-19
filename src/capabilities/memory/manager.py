"""
Memory Manager
统一记忆管理入口 - 协调短期、长期记忆和向量检索
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.capabilities.memory.store import ShortTermMemory
from src.capabilities.memory.repository import MemoryRepository
from src.capabilities.memory.vector_store import ElasticsearchVectorStore
from src.capabilities.memory.context_manager import ContextManager
from src.capabilities.memory.lifecycle import MemoryLifecycleManager
from src.core.logging import service_logger
from src.core.config import Settings


class MemoryManager:
    """记忆管理器 - 统一入口"""

    def __init__(self, settings: Settings, db_session: AsyncSession):
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

        # 2. 初始化长期记忆仓库 (MySQL)
        self.repository = MemoryRepository(db_session)

        # 3. 初始化向量存储 (ES)
        self.vector_store: ElasticsearchVectorStore | None = None
        if settings.memory_long_term_enabled:
            self.vector_store = ElasticsearchVectorStore(
                hosts=settings.memory_es_hosts,
                index_name=settings.memory_es_index,
                dimension=settings.memory_vector_dimension,
            )

        # 4. 初始化上下文管理器
        self.context_manager = ContextManager(
            short_term=self.short_term,
            repository=self.repository,
            vector_store=self.vector_store,
            max_tokens=8000,  # 可根据模型调整
        )

        # 5. 初始化生命周期管理器
        self.lifecycle = MemoryLifecycleManager(
            repository=self.repository,
            importance_threshold=settings.memory_importance_threshold,
        )

        service_logger.info("MemoryManager initialized")

    async def init(self) -> None:
        """初始化记忆系统 (创建ES索引等)"""
        try:
            if self.vector_store:
                await self.vector_store.create_index()
                service_logger.info("Vector store index created")

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
        2. 写入长期记忆 (MySQL)
        3. 生成向量并写入ES (异步)

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

            # 2. 写入长期记忆 (MySQL)
            record = await self.repository.create(
                user_id=user_id,
                session_id=session_id,
                role=role,
                content=content,
                memory_type=memory_type,
                metadata=metadata,
            )

            # 3. 写入向量存储 (ES)
            if self.vector_store and memory_type == "long_term":
                # TODO: 需要嵌入模型生成向量
                # embedding = await self._generate_embedding(content)
                # await self.vector_store.upsert(...)
                service_logger.debug(f"Vector storage pending for memory_id={record.id}")

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
            if not self.vector_store:
                return []

            # TODO: 需要嵌入模型生成查询向量
            # query_embedding = await self._generate_embedding(query)
            # results = await self.vector_store.search(...)
            return []

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

            # 软删除长期记忆
            await self.repository.batch_delete_by_session(session_id)

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
