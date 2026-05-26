"""
Context Manager
上下文管理器 - 短期记忆 + 长期记忆检索 + Token裁剪
"""

import tiktoken

from src.capabilities.memory.store import ShortTermMemory
from src.capabilities.memory.repository import MemoryRepository
from src.capabilities.memory.embeddings import EmbeddingProvider
from src.capabilities.memory.vector_store import VectorStore
from src.core.logging import service_logger


class ContextManager:
    """上下文管理器 - 构建Agent上下文"""

    def __init__(
        self,
        short_term: ShortTermMemory,
        repository: MemoryRepository,
        vector_store: VectorStore | None = None,
        max_tokens: int = 4000,
        embedding_provider: EmbeddingProvider | None = None,
    ):
        """
        初始化上下文管理器

        Args:
            short_term: 短期记忆存储
            repository: 长期记忆关系数据仓库
            vector_store: 可配置向量存储 (可选)
            max_tokens: 最大Token数
            embedding_provider: 嵌入生成器 (用于向量检索)
        """
        self.short_term = short_term
        self.repository = repository
        self.vector_store = vector_store
        self.max_tokens = max_tokens
        self.embedding_provider = embedding_provider

        # 初始化tokenizer (使用cl100k_base,对应GPT-4)
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self.tokenizer = None
            service_logger.warning("Failed to load tiktoken, token counting disabled")

    async def build_context(
        self,
        session_id: str,
        user_id: str,
        user_input: str,
        max_turns: int = 6,
        enable_retrieval: bool = True,
        retrieval_top_k: int = 3,
    ) -> str:
        """
        构建完整上下文

        流程:
        1. 获取短期记忆 (最近N轮对话)
        2. 向量检索相关长期记忆 (如果启用)
        3. 合并并格式化上下文
        4. Token计数和裁剪

        Args:
            session_id: 会话ID
            user_id: 用户ID
            user_input: 当前用户输入
            max_turns: 最大对话轮数
            enable_retrieval: 是否启用长期记忆检索
            retrieval_top_k: 检索返回数量

        Returns:
            str: 格式化后的上下文字符串
        """
        try:
            # 1. 获取短期记忆
            short_memories = await self.short_term.get_recent(session_id, max_turns)

            # 2. 向量检索长期记忆 (如果启用且有向量存储)
            long_memories = []
            if enable_retrieval and self.vector_store and self.embedding_provider:
                try:
                    # 生成查询向量
                    query_embedding = await self.embedding_provider.embed(user_input)

                    # 向量检索
                    candidates = await self.vector_store.search(
                        query_embedding=query_embedding,
                        top_k=retrieval_top_k,
                        user_id=user_id,
                    )

                    # 关系存储是有效状态的事实源，软删除的残留向量不可进入上下文。
                    for memory in candidates:
                        memory_id = int(memory["memory_id"])
                        if await self.repository.get_by_id(memory_id):
                            long_memories.append(memory)
                            await self.repository.increment_access(memory_id)

                except Exception as e:
                    service_logger.error(f"Long-term memory retrieval failed: {e}", exc_info=True)

            # 3. 合并并格式化
            context = self._format_context(short_memories, long_memories, user_input)

            # 4. Token计数和裁剪
            if self.tokenizer:
                token_count = self._count_tokens(context)
                if token_count > self.max_tokens:
                    service_logger.warning(
                        f"Context exceeds max tokens: {token_count} > {self.max_tokens}, truncating..."
                    )
                    context = self._truncate_context(context, max_turns // 2)

            service_logger.debug(
                f"Context built: short_term={len(short_memories)}, "
                f"long_term={len(long_memories)}, tokens={self._count_tokens(context)}"
            )

            return context

        except Exception as e:
            service_logger.error(f"Failed to build context: {e}", exc_info=True)
            # 降级方案:只返回用户输入
            return f"User: {user_input}"

    def _format_context(
        self,
        short_memories: list[dict],
        long_memories: list[dict],
        current_input: str,
    ) -> str:
        """
        格式化上下文

        Args:
            short_memories: 短期记忆列表
            long_memories: 长期记忆列表 (向量检索结果)
            current_input: 当前用户输入

        Returns:
            str: 格式化后的上下文
        """
        context_parts = []

        # 添加长期记忆 (相关历史)
        if long_memories:
            context_parts.append("=== Relevant Long-Term Memories ===")
            for idx, memory in enumerate(long_memories, 1):
                metadata = memory.get("metadata", {})
                role = memory.get("role", "user")
                content = metadata.get("content", "")
                if content:
                    context_parts.append(f"[{idx}] {role}: {content}")
            context_parts.append("")

        # 添加短期记忆 (最近对话)
        if short_memories:
            context_parts.append("=== Recent Conversation ===")
            for memory in short_memories:
                role = memory.get("role", "user")
                content = memory.get("content", "")
                context_parts.append(f"{role}: {content}")
            context_parts.append("")

        # 添加当前输入
        context_parts.append(f"user: {current_input}")

        return "\n".join(context_parts)

    def _count_tokens(self, text: str) -> int:
        """
        计算Token数量

        Args:
            text: 文本内容

        Returns:
            int: Token数量
        """
        if not self.tokenizer:
            return len(text) // 4  # 粗略估算 (1 token ≈ 4 characters)

        try:
            return len(self.tokenizer.encode(text))
        except Exception:
            return len(text) // 4

    def _truncate_context(self, context: str, reduced_turns: int = 3) -> str:
        """
        裁剪上下文 (保留最重要的部分)

        策略:
        1. 保留长期记忆
        2. 减少短期记忆轮数
        3. 保留当前输入

        Args:
            context: 原始上下文
            reduced_turns: 减少后的轮数

        Returns:
            str: 裁剪后的上下文
        """
        lines = context.split("\n")
        truncated_lines = []

        in_long_term = False
        in_recent = False
        recent_count = 0

        for line in lines:
            if "=== Relevant Long-Term Memories ===" in line:
                in_long_term = True
                in_recent = False
                truncated_lines.append(line)
            elif "=== Recent Conversation ===" in line:
                in_long_term = False
                in_recent = True
                truncated_lines.append(line)
                recent_count = 0
            elif in_long_term:
                # 保留所有长期记忆
                truncated_lines.append(line)
            elif in_recent:
                # 限制短期记忆数量
                if line.strip():  # 非空行
                    recent_count += 1
                    if recent_count <= reduced_turns * 2:  # 每轮2条消息
                        truncated_lines.append(line)
                else:
                    truncated_lines.append(line)
            else:
                # 保留其他部分 (如当前输入)
                truncated_lines.append(line)

        return "\n".join(truncated_lines)

    async def get_context_stats(
        self,
        session_id: str,
        user_id: str,
    ) -> dict:
        """
        获取上下文统计信息

        Args:
            session_id: 会话ID
            user_id: 用户ID

        Returns:
            dict: 统计信息
        """
        try:
            # 短期记忆统计
            short_memories = await self.short_term.get_all(session_id)
            short_ttl = await self.short_term.get_ttl(session_id)

            # 长期记忆统计
            long_stats = await self.repository.get_stats(user_id)

            return {
                "short_term": {
                    "count": len(short_memories),
                    "ttl_seconds": short_ttl,
                },
                "long_term": long_stats,
                "max_tokens": self.max_tokens,
            }

        except Exception as e:
            service_logger.error(f"Failed to get context stats: {e}", exc_info=True)
            return {"error": str(e)}
