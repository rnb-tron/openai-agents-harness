"""
Memory Lifecycle Manager
记忆生命周期管理 - 重要性评分、遗忘策略、去重、归档
"""

from datetime import datetime, timedelta

from sqlalchemy import select, and_

from src.capabilities.memory.models import MemoryRecord
from src.capabilities.memory.repository import MemoryRepository
from src.core.logging import service_logger


class MemoryLifecycleManager:
    """记忆生命周期管理器"""

    def __init__(
        self,
        repository: MemoryRepository,
        importance_threshold: float = 0.3,
        max_memories_per_user: int = 100,
    ):
        """
        初始化生命周期管理器

        Args:
            repository: 记忆数据仓库
            importance_threshold: 重要性阈值 (低于此值可能被遗忘)
            max_memories_per_user: 每个用户最大记忆数量
        """
        self.repository = repository
        self.importance_threshold = importance_threshold
        self.max_memories_per_user = max_memories_per_user

    async def calculate_importance(
        self,
        memory: MemoryRecord,
        access_weight: float = 0.4,
        recency_weight: float = 0.3,
        content_weight: float = 0.3,
    ) -> float:
        """
        计算记忆重要性评分

        评分因子:
        - 访问频率 (40%): 访问次数越多越重要
        - 新鲜度 (30%): 最近访问的记忆更重要
        - 内容长度 (30%): 内容越长可能越重要

        Args:
            memory: 记忆记录
            access_weight: 访问频率权重
            recency_weight: 新鲜度权重
            content_weight: 内容长度权重

        Returns:
            float: 重要性评分 (0-1)
        """
        try:
            # 1. 访问频率得分 (归一化到0-1)
            access_score = min(memory.access_count / 10.0, 1.0)

            # 2. 新鲜度得分 (基于最后访问时间)
            if memory.last_accessed_at:
                days_since_access = (datetime.now() - memory.last_accessed_at).days
                recency_score = max(0.0, 1.0 - (days_since_access / 30.0))  # 30天衰减到0
            else:
                recency_score = 0.5  # 默认中等

            # 3. 内容长度得分 (归一化)
            content_length = len(memory.content)
            content_score = min(content_length / 500.0, 1.0)  # 500字符满分

            # 4. 加权计算
            importance = access_weight * access_score + recency_weight * recency_score + content_weight * content_score

            return min(max(importance, 0.0), 1.0)  # 限制在0-1范围

        except Exception as e:
            service_logger.error(f"Failed to calculate importance: {e}", exc_info=True)
            return 0.5  # 失败时返回默认值

    async def apply_forgetting_policy(self, user_id: str, batch_size: int = 50) -> int:
        """
        应用遗忘策略 - 清理低重要性记忆

        策略:
        1. 删除重要性评分低于阈值的记忆
        2. 如果记忆数量超过上限,删除最不重要的记忆

        Args:
            user_id: 用户ID
            batch_size: 批量处理数量

        Returns:
            int: 删除的记忆数量
        """
        try:
            deleted_count = 0

            # 1. 删除低重要性记忆
            low_importance_result = await self.repository.db.execute(
                select(MemoryRecord.id)
                .where(
                    and_(
                        MemoryRecord.user_id == user_id,
                        MemoryRecord.is_deleted == 0,
                        MemoryRecord.importance_score < self.importance_threshold,
                    )
                )
                .limit(batch_size)
            )
            low_importance_ids = [row[0] for row in low_importance_result.all()]

            for memory_id in low_importance_ids:
                if await self.repository.soft_delete(memory_id):
                    deleted_count += 1

            service_logger.info(
                f"Forgetting policy applied: deleted {deleted_count} low-importance memories for user={user_id}"
            )

            # 2. 检查是否超过最大数量限制
            stats = await self.repository.get_stats(user_id)
            if stats["total_count"] > self.max_memories_per_user:
                excess_count = stats["total_count"] - self.max_memories_per_user

                # 获取最不重要的记忆
                excess_result = await self.repository.db.execute(
                    select(MemoryRecord.id)
                    .where(
                        and_(
                            MemoryRecord.user_id == user_id,
                            MemoryRecord.is_deleted == 0,
                        )
                    )
                    .order_by(MemoryRecord.importance_score.asc())
                    .limit(excess_count)
                )
                excess_ids = [row[0] for row in excess_result.all()]

                for memory_id in excess_ids:
                    if await self.repository.soft_delete(memory_id):
                        deleted_count += 1

                service_logger.info(
                    f"Memory limit enforced: deleted {len(excess_ids)} excess memories for user={user_id}"
                )

            return deleted_count

        except Exception as e:
            service_logger.error(f"Failed to apply forgetting policy: {e}", exc_info=True)
            return 0

    async def deduplicate_similar_memories(
        self,
        user_id: str,
        time_window_hours: int = 24,
    ) -> int:
        """
        相似记忆去重

        策略:
        1. 查找同一用户、短时间窗口内的重复内容
        2. 保留最新或重要性更高的记忆

        Args:
            user_id: 用户ID
            time_window_hours: 时间窗口 (小时)

        Returns:
            int: 去重的记忆数量
        """
        try:
            # 查询时间窗口内的记忆
            time_threshold = datetime.now() - timedelta(hours=time_window_hours)

            recent_memories = await self.repository.db.execute(
                select(MemoryRecord)
                .where(
                    and_(
                        MemoryRecord.user_id == user_id,
                        MemoryRecord.is_deleted == 0,
                        MemoryRecord.created_at >= time_threshold,
                    )
                )
                .order_by(MemoryRecord.created_at.desc())
            )
            memories = recent_memories.scalars().all()

            # 使用内容哈希去重
            content_hash_map: dict[str, list[MemoryRecord]] = {}
            for memory in memories:
                # 简化的内容哈希 (可以改为更复杂的相似度计算)
                content_hash = hash(memory.content.strip())
                if content_hash not in content_hash_map:
                    content_hash_map[content_hash] = []
                content_hash_map[content_hash].append(memory)

            # 删除重复的记忆 (保留重要性最高的)
            deleted_count = 0
            for content_hash, memory_list in content_hash_map.items():
                if len(memory_list) > 1:
                    # 按重要性评分排序
                    memory_list.sort(key=lambda m: m.importance_score, reverse=True)

                    # 保留第一个,删除其余
                    for memory in memory_list[1:]:
                        if await self.repository.soft_delete(memory.id):
                            deleted_count += 1

            if deleted_count > 0:
                service_logger.info(f"Deduplication completed: removed {deleted_count} duplicate memories")

            return deleted_count

        except Exception as e:
            service_logger.error(f"Failed to deduplicate memories: {e}", exc_info=True)
            return 0

    async def archive_old_memories(
        self,
        user_id: str,
        days_threshold: int = 90,
    ) -> int:
        """
        归档过期记忆

        策略:
        1. 超过指定天数的记忆标记为归档状态
        2. 归档记忆可以降低存储成本或迁移到冷存储

        Args:
            user_id: 用户ID
            days_threshold: 归档阈值 (天)

        Returns:
            int: 归档的记忆数量
        """
        try:
            archive_threshold = datetime.now() - timedelta(days=days_threshold)

            # 查询过期记忆
            old_memories = await self.repository.db.execute(
                select(MemoryRecord.id).where(
                    and_(
                        MemoryRecord.user_id == user_id,
                        MemoryRecord.is_deleted == 0,
                        MemoryRecord.created_at < archive_threshold,
                        MemoryRecord.memory_type == "long_term",
                    )
                )
            )
            old_memory_ids = [row[0] for row in old_memories.all()]

            # 标记为归档 (这里使用metadata字段标记)
            archived_count = 0
            for memory_id in old_memory_ids:
                memory = await self.repository.get_by_id(memory_id)
                if memory:
                    metadata = memory.metadata or {}
                    metadata["archived"] = True
                    metadata["archived_at"] = datetime.now().isoformat()

                    # 更新元数据
                    from sqlalchemy import update

                    await self.repository.db.execute(
                        update(MemoryRecord)
                        .where(MemoryRecord.id == memory_id)
                        .values(
                            metadata=metadata,
                            updated_at=datetime.now(),
                        )
                    )
                    archived_count += 1

            await self.repository.db.flush()

            if archived_count > 0:
                service_logger.info(f"Archived {archived_count} old memories for user={user_id}")

            return archived_count

        except Exception as e:
            service_logger.error(f"Failed to archive old memories: {e}", exc_info=True)
            return 0

    async def run_maintenance(self, user_id: str | None = None) -> dict:
        """
        运行记忆维护任务

        包括:
        - 遗忘策略
        - 去重
        - 归档

        Args:
            user_id: 用户ID (可选,不传则处理所有用户)

        Returns:
            dict: 维护统计
        """
        try:
            if user_id:
                users = [user_id]
            else:
                # 获取所有有记忆的用户
                result = await self.repository.db.execute(select(MemoryRecord.user_id).distinct())
                users = [row[0] for row in result.all()]

            total_deleted = 0
            total_deduplicated = 0
            total_archived = 0

            for uid in users:
                # 遗忘策略
                deleted = await self.apply_forgetting_policy(uid)
                total_deleted += deleted

                # 去重
                deduplicated = await self.deduplicate_similar_memories(uid)
                total_deduplicated += deduplicated

                # 归档
                archived = await self.archive_old_memories(uid)
                total_archived += archived

            service_logger.info(
                f"Maintenance completed: deleted={total_deleted}, "
                f"deduplicated={total_deduplicated}, archived={total_archived}"
            )

            return {
                "deleted_count": total_deleted,
                "deduplicated_count": total_deduplicated,
                "archived_count": total_archived,
                "processed_users": len(users),
            }

        except Exception as e:
            service_logger.error(f"Failed to run maintenance: {e}", exc_info=True)
            return {"error": str(e)}
