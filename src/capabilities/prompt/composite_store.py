"""CompositeStore - 主备组合后端

主流程:
    primary.fetch() 成功 → 直接返回
    primary 抛 PromptNotFoundError / PromptFetchError → 降级到 fallback
    主备都失败 → 继续向上抛

降级时 ``tpl.source`` 改写为 ``"composite:<原 source>"``,
用于日志 / metadata 区分降级路径。
"""

from __future__ import annotations

from src.capabilities.prompt.base import PromptStore, PromptTemplate
from src.capabilities.prompt.errors import PromptFetchError, PromptNotFoundError
from src.core.logging import setup_logger

logger = setup_logger("capabilities.prompt.composite")


class CompositeStore(PromptStore):
    """主备 PromptStore 组合"""

    name = "composite"

    def __init__(self, primary: PromptStore, fallback: PromptStore) -> None:
        self._primary = primary
        self._fallback = fallback

    async def fetch(
        self,
        name: str,
        *,
        version: str | int | None = None,
        label: str | None = None,
    ) -> PromptTemplate:
        try:
            return await self._primary.fetch(name, version=version, label=label)
        except (PromptNotFoundError, PromptFetchError) as exc:
            logger.warning(
                "prompt_primary_failed_falling_back",
                extra={
                    "prompt_name": name,
                    "primary": getattr(self._primary, "name", "?"),
                    "fallback": getattr(self._fallback, "name", "?"),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            tpl = await self._fallback.fetch(name, version=version, label=label)
            tpl.source = f"composite:{tpl.source}"
            return tpl
