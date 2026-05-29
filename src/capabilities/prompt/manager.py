"""PromptManager - prompt 渲染层 (含进程内 LRU + TTL 缓存)

职责:
- 通过 PromptStore 拉取原始模板, 内存缓存 (TTL 默认 300s)
- 用 ``str.format_map(_DefaultDict)`` 做变量插值, 缺失变量保留 ``{var}`` 不抛错
- 暴露 ``warmup(names)`` 启动期预热接口, 失败仅 warning 不阻塞 lifespan
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from src.capabilities.prompt.base import PromptStore, PromptTemplate, RenderedPrompt
from src.capabilities.prompt.errors import PromptError
from src.core.logging import setup_logger

logger = setup_logger("capabilities.prompt.manager")

# 用于检测渲染后仍残留的占位符。
# Langfuse Prompt Management 使用 {{var}}; 本地 YAML 兼容既有 {var} 写法。
_LANGFUSE_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
_PLACEHOLDER_RE = re.compile(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})")


class _DefaultDict(dict):
    """``str.format_map`` 用: 缺失键时保留原占位符 ``{key}``, 不抛 KeyError"""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class PromptManager:
    """Prompt 中央管理器, 负责拉取 + 缓存 + 渲染

    缓存 key = (name, version, label), TTL 由构造参数控制 (默认 300s)。
    并发场景下用 asyncio.Lock 防止同一 key 被多次 fetch。
    """

    def __init__(
        self,
        store: PromptStore,
        *,
        cache_ttl_sec: int = 300,
        default_label: str = "prod",
    ) -> None:
        self._store = store
        self._cache_ttl = max(0, int(cache_ttl_sec))
        self._default_label = default_label
        # cache: key -> (expires_at_epoch, PromptTemplate)
        self._cache: dict[tuple[str, Any, Any], tuple[float, PromptTemplate]] = {}
        self._lock = asyncio.Lock()

    # ---------- 公共 API ----------

    async def get(
        self,
        name: str,
        *,
        version: str | int | None = None,
        label: str | None = None,
        **vars: Any,
    ) -> RenderedPrompt:
        """获取并渲染 prompt

        Args:
            name: prompt 唯一名称
            version: 可选, 指定 prompt 版本 (Langfuse 后端有效)
            label: 可选, 指定 label (默认走 ``default_label``)
            **vars: 变量插值, 缺失变量保留 ``{var}`` 占位符

        Returns:
            RenderedPrompt 含渲染后文本 + 元信息
        """
        start = time.perf_counter()
        eff_label = label or self._default_label
        cache_key = (name, version, eff_label)

        cache_hit, tpl = await self._fetch_with_cache(cache_key, name, version, eff_label)

        text = self._render_template(tpl.template, vars)

        # 检测渲染后仍残留的占位符 (排除字面 {{ }})
        leftovers = _LANGFUSE_PLACEHOLDER_RE.findall(text) + _PLACEHOLDER_RE.findall(text)
        if leftovers:
            logger.warning(
                "prompt_unresolved_placeholders",
                extra={
                    "prompt_name": name,
                    "missing": sorted(set(leftovers)),
                    "provided": sorted(vars.keys()),
                },
            )

        duration_ms = int((time.perf_counter() - start) * 1000)
        return RenderedPrompt(
            name=tpl.name,
            text=text,
            version=tpl.version,
            label=tpl.label,
            source=tpl.source,
            rendered_vars=dict(vars),
            metadata=dict(tpl.metadata),
            cache_hit=cache_hit,
            duration_ms=duration_ms,
        )

    async def warmup(self, names: list[str]) -> None:
        """启动期批量预热 cache, 单个失败仅 warning, 不阻塞"""
        if not names:
            return
        ok = 0
        fail = 0
        for n in names:
            try:
                await self.get(n)
                ok += 1
            except PromptError as exc:
                logger.warning(
                    "prompt_warmup_failed",
                    extra={"prompt_name": n, "error_type": type(exc).__name__, "error": str(exc)},
                )
                fail += 1
            except Exception as exc:
                logger.warning(
                    "prompt_warmup_unexpected_error",
                    extra={"prompt_name": n, "error_type": type(exc).__name__, "error": str(exc)},
                )
                fail += 1
        logger.info("prompt_warmup_done", extra={"ok": ok, "fail": fail, "total": len(names)})

    def clear_cache(self) -> None:
        """清空缓存 (单测 / 热更场景用)"""
        self._cache.clear()

    # ---------- 内部 ----------

    async def _fetch_with_cache(
        self,
        cache_key: tuple[str, Any, Any],
        name: str,
        version: str | int | None,
        label: str | None,
    ) -> tuple[bool, PromptTemplate]:
        """返回 (cache_hit, PromptTemplate)"""
        now = time.time()
        # 1) 无锁快路径
        cached = self._cache.get(cache_key)
        if cached is not None:
            expires_at, tpl = cached
            if self._cache_ttl == 0 or expires_at > now:
                return True, tpl

        # 2) 加锁慢路径 (防止并发同 key 重复 fetch)
        async with self._lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                expires_at, tpl = cached
                if self._cache_ttl == 0 or expires_at > time.time():
                    return True, tpl
            # 真正去后端拉
            tpl = await self._store.fetch(name, version=version, label=label)
            if self._cache_ttl > 0:
                self._cache[cache_key] = (time.time() + self._cache_ttl, tpl)
            return False, tpl

    def _render_template(self, template: str, vars: dict[str, Any]) -> str:
        """Render Langfuse ``{{var}}`` and local YAML ``{var}`` placeholders."""

        def _replace_langfuse(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in vars:
                return match.group(0)
            return str(vars[key])

        rendered = _LANGFUSE_PLACEHOLDER_RE.sub(_replace_langfuse, template)
        return rendered.format_map(_DefaultDict(vars))
