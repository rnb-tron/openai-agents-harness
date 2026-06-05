"""短期记忆缓存。

短期原文记忆只使用 Redis 承载；会话记录的权威存储是 MySQL，由
``SessionStore`` 回源。这里不提供进程内降级，避免线上多会话场景中内存
不可控增长。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

try:
    import redis.asyncio as redis
except ImportError:  # pragma: no cover - Redis 能力关闭时可不安装
    redis = Any

from src.core.logging import service_logger


class ShortTermMemory:
    """短期记忆缓存 - 基于 Redis 实现，支持 TTL 自动过期。"""

    def __init__(self, redis_client: redis.Redis | None = None, ttl: int = 3600):
        """
        初始化短期记忆

        Args:
            redis_client: Redis 客户端；为空时表示短期缓存不可用。
            ttl: 记忆过期时间，单位秒。
        """
        self.redis = redis_client
        self.ttl = ttl

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

            if not self.redis:
                service_logger.debug(f"Short-term Redis unavailable, skip cache append: session={session_id}")
                return True

            key = f"memory:short_term:{session_id}"
            await self.redis.rpush(key, json.dumps(memory_item, ensure_ascii=False))
            await self.redis.expire(key, self.ttl)

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
            if not self.redis:
                return []

            key = f"memory:short_term:{session_id}"
            messages = await self.redis.lrange(key, -(max_turns * 2), -1)
            return [json.loads(msg) for msg in messages]

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
                summary_key = f"memory:short_summary:{session_id}"
                await self.redis.delete(key, summary_key)

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
            if not self.redis:
                return -2

            key = f"memory:short_term:{session_id}"
            return await self.redis.ttl(key)

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
            if not self.redis:
                return []

            key = f"memory:short_term:{session_id}"
            messages = await self.redis.lrange(key, 0, -1)
            return [json.loads(msg) for msg in messages]

        except Exception as e:
            service_logger.error(f"Failed to get all memories: {e}", exc_info=True)
            return []

    async def save_summary(
        self,
        session_id: str,
        summary: dict[str, Any],
        ttl: int | None = None,
    ) -> bool:
        """保存会话摘要缓存。MySQL 是权威存储，Redis 只做快速读取。"""
        try:
            if not self.redis:
                return True

            key = f"memory:short_summary:{session_id}"
            encoded = json.dumps(summary, ensure_ascii=False)
            cache_ttl = self.ttl if ttl is None else ttl
            if cache_ttl > 0:
                await self.redis.set(key, encoded, ex=cache_ttl)
            else:
                await self.redis.set(key, encoded)
            return True
        except Exception as e:
            service_logger.error(f"Failed to save session summary: {e}", exc_info=True)
            return False

    async def get_summary(self, session_id: str) -> dict[str, Any] | None:
        """读取会话摘要缓存。"""
        try:
            if not self.redis:
                return None

            key = f"memory:short_summary:{session_id}"
            value = await self.redis.get(key)
            if not value:
                return None
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            return json.loads(value)
        except Exception as e:
            service_logger.error(f"Failed to get session summary: {e}", exc_info=True)
            return None


class MemoryStore:
    """兼容旧构造参数的空记忆存储。

    生产链路不再使用进程内会话记忆兜底；完整会话记录由 MySQL 保存，短期
    缓存由 Redis 保存。这个类只保留旧测试和构造函数需要的方法签名。
    """

    def __init__(self):
        pass

    def append(self, session_id: str, role: str, content: str) -> None:
        return None

    def get(self, session_id: str) -> list[dict[str, str]]:
        return []

    def clear(self, session_id: str) -> None:
        return None

    def stats(self) -> dict:
        return {
            "sessions": 0,
            "messages": 0,
            "backend": "disabled",
        }

    def render_context(self, session_id: str, max_turns: int = 6) -> str:
        turns = self.get(session_id)[-max_turns:]
        if not turns:
            return ""
        lines = [f"{item['role']}: {item['content']}" for item in turns]
        return "\n".join(lines)
