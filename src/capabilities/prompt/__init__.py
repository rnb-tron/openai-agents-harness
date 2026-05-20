"""Prompt 管理 Capability 公共导出

外部使用:
    from src.capabilities.prompt import (
        PromptCapability,
        PromptManager,
        get_prompt_manager,
        PromptTemplate,
        RenderedPrompt,
        PromptStore,
        PromptError, PromptNotFoundError, PromptFetchError,
    )
"""

from __future__ import annotations

from src.capabilities.prompt.base import PromptStore, PromptTemplate, RenderedPrompt
from src.capabilities.prompt.capability import PromptCapability
from src.capabilities.prompt.composite_store import CompositeStore
from src.capabilities.prompt.errors import (
    PromptError,
    PromptFetchError,
    PromptNotFoundError,
)
from src.capabilities.prompt.factory import get_prompt_manager, reset_prompt_manager
from src.capabilities.prompt.langfuse_store import LangfuseStore
from src.capabilities.prompt.local_yaml_store import LocalYamlStore
from src.capabilities.prompt.manager import PromptManager

__all__ = [
    # Capability + Manager
    "PromptCapability",
    "PromptManager",
    "get_prompt_manager",
    "reset_prompt_manager",
    # Stores
    "PromptStore",
    "LocalYamlStore",
    "LangfuseStore",
    "CompositeStore",
    # Data classes
    "PromptTemplate",
    "RenderedPrompt",
    # Errors
    "PromptError",
    "PromptNotFoundError",
    "PromptFetchError",
]
