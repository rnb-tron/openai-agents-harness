"""ProtocolPlugin 基类与 HTTP 接入层共享类型。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from fastapi import FastAPI


class ProtocolPlugin(ABC):
    """对外协议层可插拔组件。

    ProtocolPlugin 是 HTTP 请求链的显式扩展点；RequestContextPlugin、
    AuthPlugin、RateLimitPlugin 都继承它并安装自己的 FastAPI middleware。
    它和 ``src.capabilities.plugin.Capability`` 不同：Capability 描述 Agent
    run 生命周期能力，ProtocolPlugin 描述 HTTP 入口层能力。
    """

    name: str

    @abstractmethod
    def is_enabled(self) -> bool:
        """Whether this plugin should be included in the request chain."""
        raise NotImplementedError

    @abstractmethod
    def install(self, app: FastAPI) -> None:
        """Install hooks/handlers onto the FastAPI app.

        Called exactly once during application startup, BEFORE include_router
        for HTTP middlewares (FastAPI requires middleware registration before
        the app starts handling requests).
        """
        raise NotImplementedError

    async def setup(self) -> None:
        """Optional async resource init (called inside lifespan startup)."""
        return None

    async def teardown(self) -> None:
        """Optional async resource cleanup (called inside lifespan shutdown)."""
        return None
