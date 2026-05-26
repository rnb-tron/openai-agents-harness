"""
Memory Repository
关系数据库访问层 - 长期记忆 CRUD 操作
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select, update, delete, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.capabilities.memory.models import MemoryRecord
from src.core.logging import service_logger
from src.core.snowflake import generate_rid


class MemoryRepository:
    """记忆数据仓库 - SQLAlchemy 异步关系数据库操作。"""

    def __init__(self, db_session: AsyncSession):
        """
        初始化数据仓库

        Args:
            db_session: SQLAlchemy异步会话
        """
        self.db = db_session

    async def create(
        self,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        memory_type: str = "long_term",
        embedding_id: str | None = None,
        metadata: dict | None = None,
        importance_score: float = 0.5,
    ) -> MemoryRecord:
        """
        创建记忆记录

        Args:
            user_id: 用户ID
            session_id: 会话ID
            role: 角色 (user/assistant/system)
            content: 记忆内容
            memory_type: 记忆类型
            embedding_id: 向量存储中的关联 ID
            metadata: 扩展元数据
            importance_score: 重要性评分

        Returns:
            MemoryRecord: 创建的记忆记录
        """
        try:
            memory_id = int(generate_rid())
            
            record = MemoryRecord(
                id=memory_id,
                user_id=user_id,
                session_id=session_id,
                memory_type=memory_type,
                role=role,
                content=content,
                embedding_id=embedding_id,
                extra_metadata=metadata,
                importance_score=importance_score,
                access_count=0,
                is_deleted=0,
            )

            self.db.add(record)
            await self.db.flush()
            await self.db.refresh(record)

            service_logger.debug(f"Memory record created: id={memory_id}")
            return record

        except Exception as e:
            service_logger.error(f"Failed to create memory record: {e}", exc_info=True)
            await self.db.rollback()
            raise

    async def get_by_id(self, memory_id: int) -> MemoryRecord | None:
        """
        根据ID查询记忆

        Args:
            memory_id: 记忆ID

        Returns:
            MemoryRecord | None: 记忆记录或None
        """
        try:
            result = await self.db.execute(
                select(MemoryRecord).where(
                    and_(
                        MemoryRecord.id == memory_id,
                        MemoryRecord.is_deleted == 0,
                    )
                )
            )
            return result.scalar_one_or_none()

        except Exception as e:
            service_logger.error(f"Failed to get memory by id={memory_id}: {e}", exc_info=True)
            return None

    async def query_by_session(
        self,
        session_id: str,
        limit: int = 10,
        offset: int = 0,
        memory_type: str | None = None,
    ) -> list[MemoryRecord]:
        """
        按会话查询记忆

        Args:
            session_id: 会话ID
            limit: 返回数量限制
            offset: 偏移量
            memory_type: 记忆类型过滤 (可选)

        Returns:
            list[MemoryRecord]: 记忆记录列表
        """
        try:
            conditions = [
                MemoryRecord.session_id == session_id,
                MemoryRecord.is_deleted == 0,
            ]
            if memory_type:
                conditions.append(MemoryRecord.memory_type == memory_type)

            result = await self.db.execute(
                select(MemoryRecord)
                .where(and_(*conditions))
                .order_by(MemoryRecord.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return result.scalars().all()

        except Exception as e:
            service_logger.error(f"Failed to query session memories: {e}", exc_info=True)
            return []

    async def query_by_user(
        self,
        user_id: str,
        memory_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        """
        按用户查询记忆

        Args:
            user_id: 用户ID
            memory_type: 记忆类型过滤 (可选)
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            list[MemoryRecord]: 记忆记录列表
        """
        try:
            conditions = [
                MemoryRecord.user_id == user_id,
                MemoryRecord.is_deleted == 0,
            ]
            if memory_type:
                conditions.append(MemoryRecord.memory_type == memory_type)

            result = await self.db.execute(
                select(MemoryRecord)
                .where(and_(*conditions))
                .order_by(MemoryRecord.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return result.scalars().all()

        except Exception as e:
            service_logger.error(f"Failed to query user memories: {e}", exc_info=True)
            return []

    async def update_importance(self, memory_id: int, score: float) -> bool:
        """
        更新重要性评分

        Args:
            memory_id: 记忆ID
            score: 重要性评分

        Returns:
            bool: 是否成功
        """
        try:
            await self.db.execute(
                update(MemoryRecord)
                .where(MemoryRecord.id == memory_id)
                .values(
                    importance_score=score,
                    updated_at=datetime.now(),
                )
            )
            await self.db.flush()
            return True

        except Exception as e:
            service_logger.error(f"Failed to update importance for memory_id={memory_id}: {e}", exc_info=True)
            await self.db.rollback()
            return False

    async def increment_access(self, memory_id: int) -> bool:
        """
        增加访问计数

        Args:
            memory_id: 记忆ID

        Returns:
            bool: 是否成功
        """
        try:
            await self.db.execute(
                update(MemoryRecord)
                .where(MemoryRecord.id == memory_id)
                .values(
                    access_count=MemoryRecord.access_count + 1,
                    last_accessed_at=datetime.now(),
                    updated_at=datetime.now(),
                )
            )
            await self.db.flush()
            return True

        except Exception as e:
            service_logger.error(f"Failed to increment access for memory_id={memory_id}: {e}", exc_info=True)
            await self.db.rollback()
            return False

    async def soft_delete(self, memory_id: int) -> bool:
        """
        软删除记忆

        Args:
            memory_id: 记忆ID

        Returns:
            bool: 是否成功
        """
        try:
            await self.db.execute(
                update(MemoryRecord)
                .where(MemoryRecord.id == memory_id)
                .values(
                    is_deleted=1,
                    updated_at=datetime.now(),
                )
            )
            await self.db.flush()
            service_logger.info(f"Memory soft deleted: id={memory_id}")
            return True

        except Exception as e:
            service_logger.error(f"Failed to soft delete memory_id={memory_id}: {e}", exc_info=True)
            await self.db.rollback()
            return False

    async def batch_delete_by_session(self, session_id: str) -> int:
        """
        批量删除会话记忆

        Args:
            session_id: 会话ID

        Returns:
            int: 删除的记录数
        """
        try:
            result = await self.db.execute(
                update(MemoryRecord)
                .where(MemoryRecord.session_id == session_id)
                .values(
                    is_deleted=1,
                    updated_at=datetime.now(),
                )
            )
            await self.db.flush()
            deleted_count = result.rowcount
            service_logger.info(f"Batch deleted {deleted_count} memories for session={session_id}")
            return deleted_count

        except Exception as e:
            service_logger.error(f"Failed to batch delete session memories: {e}", exc_info=True)
            await self.db.rollback()
            return 0

    async def list_ids_by_session(self, session_id: str) -> list[int]:
        """返回会话内仍有效的记忆 ID，供关联资源清理使用。"""
        try:
            result = await self.db.execute(
                select(MemoryRecord.id).where(
                    and_(
                        MemoryRecord.session_id == session_id,
                        MemoryRecord.is_deleted == 0,
                    )
                )
            )
            return list(result.scalars().all())
        except Exception as e:
            service_logger.error(
                f"Failed to list memory ids for session={session_id}: {e}",
                exc_info=True,
            )
            return []

    async def get_important_memories(
        self,
        user_id: str,
        top_n: int = 10,
        min_score: float = 0.0,
    ) -> list[MemoryRecord]:
        """
        获取高重要性记忆

        Args:
            user_id: 用户ID
            top_n: 返回数量
            min_score: 最低重要性评分

        Returns:
            list[MemoryRecord]: 高重要性记忆列表
        """
        try:
            result = await self.db.execute(
                select(MemoryRecord)
                .where(
                    and_(
                        MemoryRecord.user_id == user_id,
                        MemoryRecord.is_deleted == 0,
                        MemoryRecord.importance_score >= min_score,
                    )
                )
                .order_by(MemoryRecord.importance_score.desc())
                .limit(top_n)
            )
            return result.scalars().all()

        except Exception as e:
            service_logger.error(f"Failed to get important memories: {e}", exc_info=True)
            return []

    async def get_stats(self, user_id: str | None = None) -> dict:
        """
        获取记忆统计信息

        Args:
            user_id: 用户ID (可选,不传则统计全部)

        Returns:
            dict: 统计信息
        """
        try:
            conditions = [MemoryRecord.is_deleted == 0]
            if user_id:
                conditions.append(MemoryRecord.user_id == user_id)

            # 总数量
            total_result = await self.db.execute(
                select(func.count(MemoryRecord.id)).where(and_(*conditions))
            )
            total_count = total_result.scalar() or 0

            # 按类型统计
            type_result = await self.db.execute(
                select(MemoryRecord.memory_type, func.count(MemoryRecord.id))
                .where(and_(*conditions))
                .group_by(MemoryRecord.memory_type)
            )
            type_stats = dict(type_result.all())

            return {
                "total_count": total_count,
                "by_type": type_stats,
            }

        except Exception as e:
            service_logger.error(f"Failed to get memory stats: {e}", exc_info=True)
            return {"total_count": 0, "by_type": {}}
