"""
Short-Term Memory Store
短期记忆存储 - Redis增强版
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

try:
    import redis.asyncio as redis
except ImportError:  # pragma: no cover - optional when Redis capability is disabled
    redis = Any

from src.core.logging import service_logger


class ShortTermMemory:
    """短期记忆 - 基于Redis实现,支持TTL自动过期"""

    def __init__(self, redis_client: redis.Redis | None = None, ttl: int = 3600):
        """
        初始化短期记忆

        Args:
            redis_client: Redis客户端 (如果为None则使用内存存储)
            ttl: 记忆过期时间 (秒),默认3600秒(1小时)
        """
        self.redis = redis_client
        self.ttl = ttl
        self._memory: dict[str, list[dict]] = {}  # 内存存储 (降级方案)

    async def append(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict | None = None,
    ) -> bool:
        """
        添加记忆到短期存储

        Args:
            session_id: 会话ID
            role: 角色 (user/assistant/system)
            content: 记忆内容
            metadata: 扩展元数据

        Returns:
            bool: 是否成功
        """
        try:
            memory_item = {
                "role": role,
                "content": content,
                "timestamp": datetime.now().isoformat(),
                "metadata": metadata or {},
            }

            if self.redis:
                # Redis存储
                key = f"memory:short_term:{session_id}"
                await self.redis.rpush(key, json.dumps(memory_item, ensure_ascii=False))
                await self.redis.expire(key, self.ttl)
            else:
                # 内存存储
                self._memory.setdefault(session_id, []).append(memory_item)
                # 限制内存存储大小 (最多保留100条)
                if len(self._memory[session_id]) > 100:
                    self._memory[session_id] = self._memory[session_id][-100:]

            service_logger.debug(f"Short-term memory appended for session={session_id}")
            return True

        except Exception as e:
            service_logger.error(f"Failed to append short-term memory: {e}", exc_info=True)
            return False

    async def get_recent(self, session_id: str, max_turns: int = 6) -> list[dict]:
        """
        获取最近的记忆

        Args:
            session_id: 会话ID
            max_turns: 最大返回轮数 (默认6轮,即12条消息)

        Returns:
            list[dict]: 记忆列表
        """
        try:
            if self.redis:
                # Redis存储
                key = f"memory:short_term:{session_id}"
                # 获取最后 max_turns*2 条消息 (每轮2条: user + assistant)
                messages = await self.redis.lrange(key, -(max_turns * 2), -1)
                return [json.loads(msg) for msg in messages]
            else:
                # 内存存储
                memories = self._memory.get(session_id, [])
                return memories[-(max_turns * 2):] if memories else []

        except Exception as e:
            service_logger.error(f"Failed to get recent memories: {e}", exc_info=True)
            return []

    async def clear(self, session_id: str) -> bool:
        """
        清空会话的短期记忆

        Args:
            session_id: 会话ID

        Returns:
            bool: 是否成功
        """
        try:
            if self.redis:
                key = f"memory:short_term:{session_id}"
                await self.redis.delete(key)
            else:
                self._memory.pop(session_id, None)

            service_logger.info(f"Short-term memory cleared for session={session_id}")
            return True

        except Exception as e:
            service_logger.error(f"Failed to clear short-term memory: {e}", exc_info=True)
            return False

    async def get_ttl(self, session_id: str) -> int:
        """
        获取记忆剩余TTL

        Args:
            session_id: 会话ID

        Returns:
            int: 剩余秒数 (-1表示永不过期, -2表示不存在)
        """
        try:
            if self.redis:
                key = f"memory:short_term:{session_id}"
                return await self.redis.ttl(key)
            else:
                return -1 if session_id in self._memory else -2

        except Exception as e:
            service_logger.error(f"Failed to get TTL: {e}", exc_info=True)
            return -2

    async def get_all(self, session_id: str) -> list[dict]:
        """
        获取所有短期记忆

        Args:
            session_id: 会话ID

        Returns:
            list[dict]: 所有记忆列表
        """
        try:
            if self.redis:
                key = f"memory:short_term:{session_id}"
                messages = await self.redis.lrange(key, 0, -1)
                return [json.loads(msg) for msg in messages]
            else:
                return self._memory.get(session_id, [])

        except Exception as e:
            service_logger.error(f"Failed to get all memories: {e}", exc_info=True)
            return []


# 保持向后兼容的 MemoryStore (内存版)
class MemoryStore:
    """In-memory placeholder; can be replaced by Redis/vector store.
    
    向后兼容的旧版MemoryStore,建议使用ShortTermMemory替代
    """

    def __init__(self):
        self._memory: dict[str, list[dict[str, str]]] = {}

    def append(self, session_id: str, role: str, content: str) -> None:
        self._memory.setdefault(session_id, []).append({"role": role, "content": content})

    def get(self, session_id: str) -> list[dict[str, str]]:
        return self._memory.get(session_id, [])

    def clear(self, session_id: str) -> None:
        self._memory.pop(session_id, None)

    def stats(self) -> dict:
        return {
            "sessions": len(self._memory),
            "messages": sum(len(items) for items in self._memory.values()),
        }

    def render_context(self, session_id: str, max_turns: int = 6) -> str:
        turns = self.get(session_id)[-max_turns:]
        if not turns:
            return ""
        lines = [f"{item['role']}: {item['content']}" for item in turns]
        return "\n".join(lines)
