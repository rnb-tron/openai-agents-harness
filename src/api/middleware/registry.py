"""对外协议插件的集中注册与生命周期管理。"""

from __future__ import annotations

from typing import List

from fastapi import FastAPI

from src.api.middleware.base import ProtocolPlugin
from src.core.logging import setup_logger

logger = setup_logger("api.middleware.registry")


class ProtocolPluginRegistry:
    """持有对外协议插件，并分派安装和生命周期调用。

    Note on FastAPI middleware ordering:
        FastAPI builds the middleware stack in LIFO order (last registered
        runs first). To make registration order intuitive (the FIRST plugin
        registered runs FIRST at request time), `install_all` iterates the
        list in REVERSE when calling each plugin's `install`.

        Recommended registration order: Auth -> RateLimit (Auth runs first,
        so RateLimit can see `request.state.principal`).
    """

    def __init__(self) -> None:
        self._plugins: List[ProtocolPlugin] = []
        self._installed: bool = False

    def register(self, plugin: ProtocolPlugin) -> None:
        if self._installed:
            raise RuntimeError("protocol registry already installed; cannot register more plugins")
        self._plugins.append(plugin)
        logger.info(
            "protocol_plugin_registered",
            extra={"plugin": plugin.name, "enabled": plugin.is_enabled()},
        )

    @property
    def plugins(self) -> List[ProtocolPlugin]:
        return list(self._plugins)

    @property
    def enabled(self) -> List[ProtocolPlugin]:
        return [p for p in self._plugins if p.is_enabled()]

    def install_all(self, app: FastAPI) -> None:
        """Install all enabled plugins onto the FastAPI app.

        Iterates in reverse so the first-registered plugin runs first at
        request time (FastAPI middleware stack is LIFO).
        """
        if self._installed:
            return
        for plugin in reversed(self.enabled):
            plugin.install(app)
            logger.info("protocol_plugin_installed", extra={"plugin": plugin.name})
        self._installed = True

    async def setup_all(self) -> None:
        for plugin in self.enabled:
            try:
                await plugin.setup()
            except Exception as e:
                logger.error(
                    "protocol_plugin_setup_failed",
                    extra={"plugin": plugin.name, "error": str(e)},
                    exc_info=True,
                )
                raise

    async def teardown_all(self) -> None:
        for plugin in reversed(self.enabled):
            try:
                await plugin.teardown()
            except Exception as e:
                logger.warning(
                    "protocol_plugin_teardown_failed",
                    extra={"plugin": plugin.name, "error": str(e)},
                )

    def reset(self) -> None:
        """Test-only helper. Clears state so tests can re-register fresh plugins."""
        self._plugins.clear()
        self._installed = False


# 兼容旧导入；新 app factory 为每个应用创建独立 registry。
MiddlewareRegistry = ProtocolPluginRegistry
middleware_registry = ProtocolPluginRegistry()
