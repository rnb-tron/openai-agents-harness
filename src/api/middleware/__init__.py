"""Protocol-layer pluggable middleware: Auth / RateLimit / Session etc.

Coexists with `src.capabilities.plugin` (which acts on the Agent run lifecycle).
This module focuses on the HTTP request lifecycle.
"""

from src.api.middleware.base import MiddlewarePlugin
from src.api.middleware.registry import MiddlewareRegistry, middleware_registry

__all__ = ["MiddlewarePlugin", "MiddlewareRegistry", "middleware_registry"]
