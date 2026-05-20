"""轻量级 Capability 工具

``HookCapability`` 允许用户不写子类, 仅通过传入函数即可注册一个能力,
适合做临时埋点、自定义业务钩子等场景。
"""

from __future__ import annotations

from typing import Awaitable, Callable

from .base import Capability, RunContext

HookFn = Callable[[RunContext], Awaitable[None]]
ErrorHookFn = Callable[[RunContext, Exception], Awaitable[None]]


class HookCapability(Capability):
    """通过函数构造一个最简 Capability

    用例::

        async def log_request(ctx: RunContext) -> None:
            logger.info("user_request", extra={"session_id": ctx.session_id})

        registry.register(HookCapability(name="user_request_log", before_run=log_request))
    """

    def __init__(
        self,
        name: str,
        *,
        enabled: bool = True,
        before_run: HookFn | None = None,
        after_run: HookFn | None = None,
        on_error: ErrorHookFn | None = None,
    ) -> None:
        self.name = name
        self._enabled = enabled
        self._before_run = before_run
        self._after_run = after_run
        self._on_error = on_error

    def is_enabled(self) -> bool:
        return self._enabled

    async def before_run(self, ctx: RunContext) -> None:
        if self._before_run is not None:
            await self._before_run(ctx)

    async def after_run(self, ctx: RunContext) -> None:
        if self._after_run is not None:
            await self._after_run(ctx)

    async def on_error(self, ctx: RunContext, error: Exception) -> None:
        if self._on_error is not None:
            await self._on_error(ctx, error)
