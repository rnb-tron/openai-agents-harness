"""PromptCapability - Capability 协议接入点

职责 (轻量):
- ``setup()``: 启动期跑 ``PromptManager.warmup(prompt_warmup_names)``
- ``before_run()``: 仅向 ctx.metadata 注入 ``prompt_manager_ready=True`` 标记
- ``teardown()``: 清空 manager 缓存

注意: 实际 prompt 渲染由调用方 (agent_runtime / rolling_summary) 主动调
``PromptManager.get(...)`` 触发, Capability 不强行修改 ``enriched_input``。
"""

from __future__ import annotations

from src.capabilities.plugin import Capability, RunContext
from src.core.logging import setup_logger
from src.harness.manifest import CapabilityKind, CapabilityManifest

logger = setup_logger("capabilities.prompt.capability")


class PromptCapability(Capability):
    """Prompt 管理 Capability (轻量生命周期挂钩)"""

    name = "prompt"
    manifest = CapabilityManifest(
        name="prompt",
        kind=CapabilityKind.RUNTIME,
        config_section="prompt",
        provides=("prompt_manager", "prompt_rendering"),
        install_order=10,
    )

    def __init__(
        self,
        manager,  # PromptManager | None
        warmup_names: list[str],
        enabled: bool = True,
    ) -> None:
        self._manager = manager
        self._warmup_names = warmup_names
        self._enabled = enabled

    @classmethod
    def from_settings(cls, settings) -> "PromptCapability":
        """从 settings 构造, 通过 lazy 工厂拿单例 PromptManager"""
        from src.capabilities.prompt.factory import get_prompt_manager

        mgr = get_prompt_manager()
        if mgr is None:
            return cls(manager=None, warmup_names=[], enabled=False)
        names = [n.strip() for n in (getattr(settings, "prompt_warmup_names", "") or "").split(",") if n.strip()]
        return cls(manager=mgr, warmup_names=names, enabled=True)

    # ---------- Capability 协议 ----------

    def is_enabled(self) -> bool:
        return self._enabled

    async def setup(self) -> None:
        if not self._enabled or self._manager is None:
            return
        if self._warmup_names:
            await self._manager.warmup(self._warmup_names)

    async def teardown(self) -> None:
        if self._manager is not None:
            self._manager.clear_cache()

    async def before_run(self, ctx: RunContext) -> None:
        if self._enabled:
            ctx.metadata["prompt_manager_ready"] = True
