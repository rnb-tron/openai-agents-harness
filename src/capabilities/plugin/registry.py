"""CapabilityRegistry: 集中管理所有可插拔能力的注册与调度"""

from __future__ import annotations

from typing import Iterable

from src.core.logging import setup_logger

from .base import Capability, RunContext, RunPhase

logger = setup_logger("capabilities.plugin.registry")


class CapabilityRegistry:
    """可插拔能力注册中心

    使用方式::

        registry = CapabilityRegistry()
        registry.register(MemoryCapability(...))
        registry.register(HITLCapability(...))

        await registry.setup_all()

        ctx = RunContext(session_id="...", user_input="...")
        await registry.dispatch(RunPhase.BEFORE_RUN, ctx)
        # ... 调用模型 ...
        await registry.dispatch(RunPhase.AFTER_RUN, ctx)

        await registry.teardown_all()

    单个 capability 的钩子异常默认不会中断主流程, 而是记录结构化日志后继续,
    与"未启用零开销, 启用后失败可降级"的设计原则一致。
    """

    def __init__(self) -> None:
        self._capabilities: list[Capability] = []

    # ---------- 注册管理 ----------

    def register(self, capability: Capability) -> None:
        """注册一个能力"""
        if not isinstance(capability, Capability):
            raise TypeError(
                f"capability must be a subclass of Capability, got {type(capability).__name__}"
            )
        self._capabilities.append(capability)
        logger.info(
            "capability_registered",
            extra={
                "capability": capability.name,
                "enabled": capability.is_enabled(),
            },
        )

    def register_all(self, capabilities: Iterable[Capability]) -> None:
        for cap in capabilities:
            self.register(cap)

    @property
    def all(self) -> list[Capability]:
        return list(self._capabilities)

    @property
    def enabled(self) -> list[Capability]:
        return [c for c in self._capabilities if c.is_enabled()]

    def get(self, name: str) -> Capability | None:
        for c in self._capabilities:
            if c.name == name:
                return c
        return None

    # ---------- 生命周期 ----------

    async def setup_all(self) -> None:
        """初始化所有已启用能力"""
        for cap in self.enabled:
            try:
                await cap.setup()
            except Exception as e:
                logger.error(
                    "capability_setup_failed",
                    extra={
                        "capability": cap.name,
                        "error_type": type(e).__name__,
                        "error": str(e),
                    },
                )
                raise

    async def teardown_all(self) -> None:
        """关闭所有已注册能力, 单个失败不影响其它能力的清理"""
        for cap in self._capabilities:
            try:
                await cap.teardown()
            except Exception as e:
                logger.warning(
                    "capability_teardown_failed",
                    extra={
                        "capability": cap.name,
                        "error_type": type(e).__name__,
                        "error": str(e),
                    },
                )

    # ---------- 运行期分发 ----------

    async def dispatch(
        self,
        phase: RunPhase,
        ctx: RunContext,
        error: Exception | None = None,
    ) -> None:
        """按阶段触发所有已启用能力的对应钩子

        单个 capability 的钩子异常会被捕获并记录日志, 不影响其它能力以及主流程。
        """
        for cap in self.enabled:
            try:
                if phase == RunPhase.BEFORE_RUN:
                    await cap.before_run(ctx)
                elif phase == RunPhase.AFTER_RUN:
                    await cap.after_run(ctx)
                elif phase == RunPhase.ON_ERROR:
                    if error is None:
                        raise ValueError("on_error phase requires error argument")
                    await cap.on_error(ctx, error)
            except Exception as e:
                logger.warning(
                    "capability_hook_failed",
                    extra={
                        "capability": cap.name,
                        "phase": phase.value,
                        "error_type": type(e).__name__,
                        "error": str(e),
                    },
                )
