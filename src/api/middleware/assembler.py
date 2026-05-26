"""按配置装配对外 HTTP 协议插件。"""

from src.api.middleware.auth.plugin import AuthPlugin
from src.api.middleware.rate_limit.plugin import RateLimitPlugin
from src.api.middleware.registry import ProtocolPluginRegistry
from src.capabilities.observability.plugin import ObservabilityPlugin


def build_protocol_registry(settings) -> ProtocolPluginRegistry:
    """构建 HTTP 接入链；Observability 仅在此贡献其请求追踪入口。"""
    registry = ProtocolPluginRegistry()
    for plugin in (
        ObservabilityPlugin.from_settings(settings),
        AuthPlugin.from_settings(settings),
        RateLimitPlugin.from_settings(settings),
    ):
        if plugin.is_enabled():
            registry.register(plugin)
    return registry
