"""PromptManager 全局工厂 (lazy 单例)

设计模式与 ``infrastructure/redis_client.py`` 的 ``get_redis_client()`` 一致,
避免在 ``chat.py`` 模块级实例化 ``_orchestrator`` 时与 ``Settings`` 加载顺序耦合。

使用方:
    from src.capabilities.prompt.factory import get_prompt_manager
    mgr = get_prompt_manager()
    if mgr is not None:
        rendered = await mgr.get("agents.main_chat", task_type=task_type)

单测:
    reset_prompt_manager()  # 清空单例, 在 setUp/tearDown 中调用
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.config import current_settings as _runtime_settings
from src.core.logging import setup_logger

if TYPE_CHECKING:
    from src.capabilities.prompt.manager import PromptManager

logger = setup_logger("capabilities.prompt.factory")

_prompt_manager: "PromptManager | None" = None


def get_prompt_manager() -> "PromptManager | None":
    """返回已初始化的 PromptManager 单例;未启用 (``prompt_enabled=False``) 时返回 None"""
    global _prompt_manager
    if _prompt_manager is not None:
        return _prompt_manager

    settings = _runtime_settings
    if not getattr(settings, "prompt_enabled", False):
        return None

    try:
        _prompt_manager = _build_from_settings(settings)
        logger.info(
            "prompt_manager_initialized",
            extra={
                "backend": getattr(settings, "prompt_backend", "composite"),
                "local_dir": getattr(settings, "prompt_local_dir", "prompts"),
                "cache_ttl_sec": getattr(settings, "prompt_cache_ttl_sec", 300),
            },
        )
    except Exception as exc:
        logger.error(
            "prompt_manager_init_failed",
            extra={"error_type": type(exc).__name__, "error": str(exc)},
        )
        _prompt_manager = None
    return _prompt_manager


def reset_prompt_manager() -> None:
    """重置全局单例 (单测用)"""
    global _prompt_manager
    _prompt_manager = None


def _build_from_settings(settings) -> "PromptManager":
    """根据 settings.prompt_backend 构造对应 store 与 manager"""
    # lazy import 避免循环依赖
    from src.capabilities.prompt.composite_store import CompositeStore
    from src.capabilities.prompt.langfuse_store import LangfuseStore
    from src.capabilities.prompt.local_yaml_store import LocalYamlStore
    from src.capabilities.prompt.manager import PromptManager

    backend = (settings.prompt_backend or "composite").lower()
    local_dir = settings.prompt_local_dir or "prompts"
    default_label = settings.prompt_default_label or "prod"

    if backend == "langfuse":
        store = LangfuseStore(default_label=default_label)
    elif backend == "yaml":
        store = LocalYamlStore(base_dir=local_dir)
    else:
        # composite (默认): Langfuse 主, LocalYaml 兜底
        store = CompositeStore(
            primary=LangfuseStore(default_label=default_label),
            fallback=LocalYamlStore(base_dir=local_dir),
        )

    return PromptManager(
        store=store,
        cache_ttl_sec=int(getattr(settings, "prompt_cache_ttl_sec", 300)),
        default_label=default_label,
    )
