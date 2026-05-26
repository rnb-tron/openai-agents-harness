"""MemoryCapability: 把 MemoryStore + MemoryManager 适配为统一的 Capability

- 短期记忆 (MemoryStore) 始终启用, 由 ``before_run`` 注入对话上下文,
  ``after_run`` 写入用户输入与助手回复
- 长期记忆 (MemoryManager) 可选启用, 失败自动降级到短期记忆
"""

from __future__ import annotations

from src.capabilities.memory.manager import MemoryManager
from src.capabilities.memory.store import MemoryStore
from src.capabilities.plugin import Capability, RunContext
from src.core.logging import setup_logger
from src.harness.manifest import CapabilityKind, CapabilityManifest

logger = setup_logger("capabilities.memory.capability")


class MemoryCapability(Capability):
    """记忆能力适配器, 统一短期 / 长期记忆的注入与写入"""

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
        memory_manager: MemoryManager | None = None,
        long_term_enabled: bool = False,
    ) -> None:
        self._store = memory_store
        self._manager = memory_manager
        # 仅当外部启用且确实注入了 manager 时才走长期记忆
        self._long_term_enabled = long_term_enabled and memory_manager is not None

    def is_enabled(self) -> bool:
        # 短期记忆是基础能力, 始终启用; 长期是否启用由内部判断
        return True

    async def before_run(self, ctx: RunContext) -> None:
        """构建携带历史的 ``ctx.enriched_input``"""
        memory_context = ""
        if self._long_term_enabled and self._manager is not None:
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
                memory_context = self._store.render_context(ctx.session_id)
        else:
            memory_context = self._store.render_context(ctx.session_id)

        if memory_context:
            ctx.enriched_input = (
                "Conversation memory:\n"
                f"{memory_context}\n\n"
                "User:\n"
                f"{ctx.user_input}"
            )
        else:
            ctx.enriched_input = ctx.user_input

    async def after_run(self, ctx: RunContext) -> None:
        """写入短期记忆;如启用长期记忆也同步写入"""
        # 短期记忆 (同步, 内存级, 不会失败)
        self._store.append(ctx.session_id, "user", ctx.user_input)
        if ctx.final_output:
            self._store.append(ctx.session_id, "assistant", ctx.final_output)

        # 长期记忆 (异步, 失败不影响主流程)
        if self._long_term_enabled and self._manager is not None:
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
    """Marker capability for persistent long-term memory.

    Runtime reads/writes still happen inside ``MemoryCapability`` for now. This
    marker makes the capability graph explicit for scaffold generation without
    forcing a larger storage refactor in this step.
    """

    name = "long_term_memory"
    manifest = CapabilityManifest(
        name="long_term_memory",
        kind=CapabilityKind.RUNTIME,
        config_section="memory",
        depends_on=("database", "memory_manager"),
        provides=("long_term_memory",),
        install_order=21,
        tags=("marker",),
    )

    def __init__(self, enabled: bool) -> None:
        self._enabled = enabled

    def is_enabled(self) -> bool:
        return self._enabled


class VectorSearchCapability(Capability):
    """Marker capability for vector-backed memory search."""

    name = "vector_search"
    manifest = CapabilityManifest(
        name="vector_search",
        kind=CapabilityKind.RUNTIME,
        config_section="memory",
        depends_on=("long_term_memory", "embedding_provider"),
        provides=("vector_search",),
        install_order=22,
        tags=("marker",),
    )

    def __init__(self, enabled: bool) -> None:
        self._enabled = enabled

    def is_enabled(self) -> bool:
        return self._enabled
