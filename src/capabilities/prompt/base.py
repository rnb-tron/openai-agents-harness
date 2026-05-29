"""Prompt 管理核心抽象 (Protocol + DataClass)

- PromptTemplate: 后端返回的原始模板对象 (含 template / version / source 等元信息)
- RenderedPrompt: 经过变量插值后的最终结果, 提供 to_metadata() 注入 ctx.metadata["prompt"]
- PromptStore: 后端 Protocol, 三个内置后端 (LocalYamlStore / LangfuseStore / CompositeStore) 都遵循此协议
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class PromptTemplate:
    """后端返回的原始模板对象 (未渲染)

    各后端必须填充 ``name`` / ``template`` / ``source``,
    其余字段按需填充 (Langfuse 一般会填 version/label, Yaml 视文件而定)。
    """

    name: str
    template: str
    version: str | int | None = None
    label: str | None = None
    source: str = "unknown"  # yaml / langfuse / composite:yaml / ...
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RenderedPrompt:
    """经过变量插值后的渲染结果, PromptManager.get() 返回此对象"""

    name: str
    text: str
    version: str | int | None = None
    label: str | None = None
    source: str = "unknown"
    rendered_vars: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    cache_hit: bool = False
    duration_ms: int = 0

    def to_metadata(self) -> dict[str, Any]:
        """转成 ctx.metadata["prompt"] 注入用的字典 (不含 text 大字段)"""
        return {
            "name": self.name,
            "version": self.version,
            "label": self.label,
            "source": self.source,
            "cache_hit": self.cache_hit,
            "duration_ms": self.duration_ms,
            "rendered_vars": dict(self.rendered_vars),
            **dict(self.metadata),
        }


@runtime_checkable
class PromptStore(Protocol):
    """Prompt 后端 Protocol

    所有后端必须有 ``name`` 类属性 + async ``fetch(name, *, version, label)`` 方法。
    """

    name: str

    async def fetch(
        self,
        name: str,
        *,
        version: str | int | None = None,
        label: str | None = None,
    ) -> PromptTemplate:
        ...
