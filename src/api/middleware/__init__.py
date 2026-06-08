"""Protocol-layer pluggable middleware: Auth / RateLimit / Session etc.

Coexists with `src.capabilities.plugin` (which acts on the Agent run lifecycle).
This module focuses on the HTTP request lifecycle.
"""

from src.api.middleware.base import ProtocolPlugin
from src.api.middleware.capabilities import AuthCapability, RateLimitCapability
from src.api.middleware.chain import ProtocolRequestChain

__all__ = [
    "AuthCapability",
    "RateLimitCapability",
    "ProtocolPlugin",
    "ProtocolRequestChain",
]
