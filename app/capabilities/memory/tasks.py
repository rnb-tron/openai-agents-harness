"""
Memory System Background Tasks
记忆系统后台定时任务
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.logging import service_logger


class MemoryTaskScheduler:
    """记忆系统定时任务调度器"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()

    async def start(self, memory_manager=None):
        """
        启动定时任务

        Args:
            memory_manager: MemoryManager实例
        """
        self.memory_manager = memory_manager

        # 1. 每日凌晨2点执行记忆维护 (遗忘策略、去重、归档)
        self.scheduler.add_job(
            self._run_maintenance,
            trigger=CronTrigger(hour=2, minute=0),
            id="memory_maintenance_daily",
            name="Daily Memory Maintenance",
            replace_existing=True,
        )

        # 2. 每小时清理过期短期记忆 (Redis TTL自动处理,这里只做统计)
        self.scheduler.add_job(
            self._check_memory_health,
            trigger=CronTrigger(minute=0),
            id="memory_health_check_hourly",
            name="Hourly Memory Health Check",
            replace_existing=True,
        )

        self.scheduler.start()
        service_logger.info("Memory task scheduler started")

    async def stop(self):
        """停止定时任务"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            service_logger.info("Memory task scheduler stopped")

    async def _run_maintenance(self):
        """执行记忆维护任务"""
        try:
            if not self.memory_manager:
                service_logger.warning("Memory manager not available, skipping maintenance")
                return

            service_logger.info("Starting daily memory maintenance...")
            result = await self.memory_manager.cleanup_old_memories()

            service_logger.info(
                f"Memory maintenance completed: "
                f"deleted={result.get('deleted_count', 0)}, "
                f"deduplicated={result.get('deduplicated_count', 0)}, "
                f"archived={result.get('archived_count', 0)}"
            )

        except Exception as e:
            service_logger.error(f"Memory maintenance failed: {e}", exc_info=True)

    async def _check_memory_health(self):
        """检查记忆系统健康状态"""
        try:
            if not self.memory_manager:
                return

            # 检查ES连接
            if self.memory_manager.vector_store:
                healthy = await self.memory_manager.vector_store.health_check()
                if not healthy:
                    service_logger.warning("Elasticsearch health check failed")

            # 获取统计信息
            stats = await self.memory_manager.get_stats()
            service_logger.debug(f"Memory system stats: {stats}")

        except Exception as e:
            service_logger.error(f"Memory health check failed: {e}", exc_info=True)


# 全局调度器实例
memory_scheduler = MemoryTaskScheduler()
