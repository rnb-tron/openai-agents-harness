"""记忆能力：把 Mem0 manager 适配为运行时上下文能力。

- 按层启用短期、summary 或长期记忆后，由 memory manager 统一读取上下文；
- 未启用或 manager 失败时，不再写入进程内兜底，直接以无记忆上下文继续。
"""

from __future__ import annotations

from src.capabilities.memory.mem0_manager import Mem0MemoryManager
from src.capabilities.memory.store import MemoryStore
from src.capabilities.plugin import Capability, RunContext
from src.core.logging import setup_logger
from src.harness.manifest import CapabilityKind, CapabilityManifest

logger = setup_logger("capabilities.memory.capability")


class MemoryCapability(Capability):
    """记忆能力适配器。"""

    name = "memory_session"
    manifest = CapabilityManifest(
        name="memory_session",
        kind=CapabilityKind.RUNTIME,
        config_section="memory",
        provides=("conversation_context", "memory_session"),
        install_order=20,
        tags=("required",),
    )

    def __init__(
        self,
        memory_store: MemoryStore,
        memory_manager: Mem0MemoryManager | None = None,
        long_term_enabled: bool = False,
    ) -> None:
        self._store = memory_store
        self._manager = memory_manager
        self._memory_context_enabled = long_term_enabled and memory_manager is not None

    def is_enabled(self) -> bool:
        return True

    async def before_run(self, ctx: RunContext) -> None:
        """构建携带记忆上下文的 ``ctx.enriched_input``。"""
        memory_context = ""
        if self._memory_context_enabled:
            try:
                memory_context = await self._manager.get_context(
                    session_id=ctx.session_id,
                    user_id=ctx.user_id or "anonymous",
                    user_input=ctx.user_input,
                )
            except Exception as e:
                # 长期记忆失败 -> 降级到短期
                logger.warning(
                    "memory_get_context_failed",
                    extra={
                        "session_id": ctx.session_id,
                        "error_type": type(e).__name__,
                        "error": str(e),
                    },
                )

        if memory_context:
            ctx.enriched_input = f"Conversation memory:\n{memory_context}\n\nUser:\n{ctx.user_input}"
        else:
            ctx.enriched_input = ctx.user_input

    async def after_run(self, ctx: RunContext) -> None:
        """写入 Mem0 manager；失败时不做进程内兜底。"""
        if self._memory_context_enabled:
            try:
                await self._manager.add_memory(
                    session_id=ctx.session_id,
                    user_id=ctx.user_id or "anonymous",
                    role="user",
                    content=ctx.user_input,
                )
                if ctx.final_output:
                    await self._manager.add_memory(
                        session_id=ctx.session_id,
                        user_id=ctx.user_id or "anonymous",
                        role="assistant",
                        content=ctx.final_output,
                    )
                return
            except Exception as e:
                logger.warning(
                    "memory_add_failed",
                    extra={
                        "session_id": ctx.session_id,
                        "user_id": ctx.user_id or "anonymous",
                        "error_type": type(e).__name__,
                        "error": str(e),
                    },
                )

    @property
    def store(self) -> MemoryStore:
        """暴露底层 store, 供 Orchestrator 读取 memory_size 等指标"""
        return self._store


class LongTermMemoryCapability(Capability):
    """长期记忆的标记能力。

    当前读写仍由 ``MemoryCapability`` 统一完成；这个标记能力的价值是让
    capability catalog 能清楚表达“长期记忆依赖 memory_manager”，同时避免在
    这一轮引入更大的存储重构。
    """

    name = "long_term_memory"
    manifest = CapabilityManifest(
        name="long_term_memory",
        kind=CapabilityKind.RUNTIME,
        config_section="memory",
        depends_on=("memory_manager",),
        provides=("long_term_memory",),
        install_order=21,
        tags=("mem0",),
    )

    def __init__(self, enabled: bool) -> None:
        self._enabled = enabled

    def is_enabled(self) -> bool:
        return self._enabled


class VectorSearchCapability(Capability):
    """语义记忆检索的标记能力。"""

    name = "vector_search"
    manifest = CapabilityManifest(
        name="vector_search",
        kind=CapabilityKind.RUNTIME,
        config_section="memory",
        depends_on=("long_term_memory",),
        provides=("vector_search",),
        install_order=22,
        tags=("mem0",),
    )

    def __init__(self, enabled: bool) -> None:
        self._enabled = enabled

    def is_enabled(self) -> bool:
        return self._enabled
