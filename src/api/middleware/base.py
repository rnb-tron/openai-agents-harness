"""ProtocolPlugin 协议与 HTTP 接入层共享类型。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from fastapi import FastAPI


@runtime_checkable
class ProtocolPlugin(Protocol):
    """对外协议层可插拔组件。

    Each plugin owns its installation strategy (HTTP middleware / Depends /
    router-level), so the registry stays agnostic about FastAPI hook flavor.
    """

    name: str

    def is_enabled(self) -> bool:
        ...

    def install(self, app: FastAPI) -> None:
        """Install hooks/handlers onto the FastAPI app.

        Called exactly once during application startup, BEFORE include_router
        for HTTP middlewares (FastAPI requires middleware registration before
        the app starts handling requests).
        """
        ...

    async def setup(self) -> None:
        """Optional async resource init (called inside lifespan startup)."""
        ...

    async def teardown(self) -> None:
        """Optional async resource cleanup (called inside lifespan shutdown)."""
        ...


# 兼容旧导入；具体插件实现仍可使用 FastAPI middleware。
MiddlewarePlugin = ProtocolPlugin
