"""按配置装配对外 HTTP 协议插件。"""

from src.api.middleware.auth.plugin import AuthPlugin
from src.api.middleware.rate_limit.plugin import RateLimitPlugin
from src.api.middleware.chain import ProtocolRequestChain
from src.api.middleware.request_context import RequestContextPlugin


def build_protocol_chain(settings) -> ProtocolRequestChain:
    """构建 HTTP 接入链。

    请求执行顺序为 ``RequestContext -> Auth -> RateLimit``：
    RequestContext 创建请求关联 ID；
    RateLimit 位于 Auth 之后，使用认证产生的 principal 作为用户维度限流键。
    """
    declared_request_order = (
        RequestContextPlugin(),
        AuthPlugin.from_settings(settings),
        RateLimitPlugin.from_settings(settings),
    )
    enabled_request_order = tuple(plugin for plugin in declared_request_order if plugin.is_enabled())
    return ProtocolRequestChain(enabled_request_order)
