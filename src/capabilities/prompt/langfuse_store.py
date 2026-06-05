"""LangfuseStore - Langfuse 远端后端

复用 ``observability/tracer.py`` 已经初始化的全局 client (``langfuse.get_client()``)。
Langfuse SDK 是同步的, 用 ``run_in_executor`` 包装为异步。

任何调用异常 (SDK / 网络 / 鉴权失败) → 抛 ``PromptFetchError``,
由 ``CompositeStore`` 接住后降级到本地 yaml。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from src.capabilities.prompt.base import PromptStore, PromptTemplate
from src.capabilities.prompt.errors import PromptFetchError
from src.core.logging import setup_logger

logger = setup_logger("capabilities.prompt.langfuse")


class LangfuseStore(PromptStore):
    """Langfuse 远端 prompt 后端"""

    name = "langfuse"

    def __init__(self, default_label: str = "prod", client: Any | None = None) -> None:
        self._default_label = default_label
        self._client = client

    async def fetch(
        self,
        name: str,
        *,
        version: str | int | None = None,
        label: str | None = None,
    ) -> PromptTemplate:
        client = self._get_client()

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
            raise PromptFetchError(f"langfuse get_prompt failed for '{name}': {exc}") from exc

        # langfuse PromptClient: .prompt can be text or chat messages.
        raw_prompt = getattr(prompt_obj, "prompt", None)
        text = self._coerce_prompt_text(raw_prompt)
        if text is None:
            raise PromptFetchError(
                f"langfuse prompt '{name}' returned unsupported payload: {type(raw_prompt).__name__}"
            )

        return PromptTemplate(
            name=getattr(prompt_obj, "name", name),
            template=text,
            version=getattr(prompt_obj, "version", None),
            label=eff_label,
            source=self.name,
            metadata={
                "langfuse_id": getattr(prompt_obj, "id", None),
                "langfuse_labels": getattr(prompt_obj, "labels", None),
                "langfuse_tags": getattr(prompt_obj, "tags", None),
                "langfuse_config": getattr(prompt_obj, "config", None),
                "langfuse_is_fallback": getattr(prompt_obj, "is_fallback", None),
                "langfuse_prompt_type": "chat" if isinstance(raw_prompt, list) else "text",
            },
        )

    @staticmethod
    def _coerce_prompt_text(prompt: Any) -> str | None:
        if isinstance(prompt, str):
            return prompt
        if not isinstance(prompt, list):
            return None

        lines: list[str] = []
        for item in prompt:
            if isinstance(item, dict):
                role = item.get("role") or "message"
                content = item.get("content")
                if isinstance(content, str):
                    lines.append(f"{role}: {content}")
                elif content is not None:
                    lines.append(f"{role}: {json.dumps(content, ensure_ascii=False)}")
            elif isinstance(item, str):
                lines.append(item)
        return "\n".join(lines) if lines else None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        try:
            from src.capabilities.observability import get_config, get_tracer_manager

            tracer_manager = get_tracer_manager()
            if tracer_manager is not None and tracer_manager.is_initialized and tracer_manager.langfuse is not None:
                return tracer_manager.langfuse

            config = get_config()
        except Exception:
            config = None

        try:
            from langfuse import get_client  # lazy import, 与 observability 解耦
        except Exception as exc:  # pragma: no cover
            raise PromptFetchError(f"langfuse not available: {exc}") from exc

        try:
            if config is not None and getattr(config, "public_key", None):
                return get_client(public_key=config.public_key)
            return get_client()
        except Exception as exc:
            raise PromptFetchError(f"langfuse client unavailable: {exc}") from exc
