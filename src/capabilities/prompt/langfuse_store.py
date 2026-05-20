"""LangfuseStore - Langfuse 远端后端

复用 ``observability/tracer.py`` 已经初始化的全局 client (``langfuse.get_client()``)。
Langfuse SDK 是同步的, 用 ``run_in_executor`` 包装为异步。

任何调用异常 (SDK / 网络 / 鉴权失败) → 抛 ``PromptFetchError``,
由 ``CompositeStore`` 接住后降级到本地 yaml。
"""

from __future__ import annotations

import asyncio

from src.capabilities.prompt.base import PromptStore, PromptTemplate
from src.capabilities.prompt.errors import PromptFetchError
from src.core.logging import setup_logger

logger = setup_logger("capabilities.prompt.langfuse")


class LangfuseStore(PromptStore):
    """Langfuse 远端 prompt 后端"""

    name = "langfuse"

    def __init__(self, default_label: str = "prod") -> None:
        self._default_label = default_label

    async def fetch(
        self,
        name: str,
        *,
        version: str | int | None = None,
        label: str | None = None,
    ) -> PromptTemplate:
        try:
            from langfuse import get_client  # lazy import, 与 observability 解耦
        except Exception as exc:  # pragma: no cover
            raise PromptFetchError(f"langfuse not available: {exc}") from exc

        try:
            client = get_client()
        except Exception as exc:
            raise PromptFetchError(f"langfuse client unavailable: {exc}") from exc

        eff_label = label or self._default_label
        loop = asyncio.get_running_loop()

        def _call_sdk():
            # langfuse 4.x SDK: client.get_prompt(name, version=..., label=...)
            kwargs: dict = {}
            if version is not None:
                kwargs["version"] = version
            if eff_label:
                kwargs["label"] = eff_label
            return client.get_prompt(name, **kwargs)

        try:
            prompt_obj = await loop.run_in_executor(None, _call_sdk)
        except Exception as exc:
            raise PromptFetchError(
                f"langfuse get_prompt failed for '{name}': {exc}"
            ) from exc

        # langfuse PromptClient: .prompt (str) / .version / .name
        text = getattr(prompt_obj, "prompt", None)
        if text is None or not isinstance(text, str):
            raise PromptFetchError(
                f"langfuse prompt '{name}' returned non-text payload: {type(text).__name__}"
            )

        return PromptTemplate(
            name=name,
            template=text,
            version=getattr(prompt_obj, "version", None),
            label=eff_label,
            source=self.name,
            metadata={"langfuse_id": getattr(prompt_obj, "id", None)},
        )
