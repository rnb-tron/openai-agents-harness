"""LocalYamlStore - 本地 YAML 文件后端

启动期扫描 ``<base_dir>/**/*.yaml``, 载入到内存 dict 中。
作为 Langfuse 不可用时的兜底, 也可作为离线/单测主用。

YAML 格式约定:
    name: agents.main_system_chat # 必填
    template: |                   # 必填
      You are a concise assistant...
    version: "1.0.0"              # 可选
    label: prod                   # 可选
    metadata:                     # 可选
      description: "..."
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.capabilities.prompt.base import PromptStore, PromptTemplate
from src.capabilities.prompt.errors import PromptNotFoundError
from src.core.logging import setup_logger

logger = setup_logger("capabilities.prompt.local_yaml")


class LocalYamlStore(PromptStore):
    """本地 YAML 后端 (启动期一次性加载, 内存查表)"""

    name = "yaml"

    def __init__(self, base_dir: str | Path) -> None:
        self._base_dir = Path(base_dir).resolve()
        self._templates: dict[str, PromptTemplate] = {}
        self._load_all()

    # ---------- 内部加载 ----------

    def _load_all(self) -> None:
        if not self._base_dir.exists() or not self._base_dir.is_dir():
            logger.warning(
                "prompt_yaml_dir_not_exist",
                extra={"dir": str(self._base_dir)},
            )
            return

        loaded = 0
        for yml in self._base_dir.rglob("*.yaml"):
            try:
                tpl = self._load_one(yml)
            except Exception as exc:
                logger.warning(
                    "prompt_yaml_load_failed",
                    extra={"file": str(yml), "error": str(exc)},
                )
                continue
            if tpl is None:
                continue
            if tpl.name in self._templates:
                logger.warning(
                    "prompt_yaml_duplicate_name",
                    extra={"prompt_name": tpl.name, "file": str(yml)},
                )
            self._templates[tpl.name] = tpl
            loaded += 1
        logger.info(
            "prompt_yaml_store_loaded",
            extra={"count": loaded, "dir": str(self._base_dir)},
        )

    def _load_one(self, path: Path) -> PromptTemplate | None:
        with path.open("r", encoding="utf-8") as f:
            data: Any = yaml.safe_load(f)
        if not isinstance(data, dict):
            return None
        name = data.get("name")
        template = data.get("template")
        if not name or not isinstance(name, str):
            logger.warning("prompt_yaml_missing_name", extra={"file": str(path)})
            return None
        if not template or not isinstance(template, str):
            logger.warning("prompt_yaml_missing_template", extra={"file": str(path)})
            return None
        return PromptTemplate(
            name=name,
            template=template,
            version=data.get("version"),
            label=data.get("label"),
            source=self.name,
            metadata=data.get("metadata") or {},
        )

    # ---------- PromptStore 协议实现 ----------

    async def fetch(
        self,
        name: str,
        *,
        version: str | int | None = None,
        label: str | None = None,
    ) -> PromptTemplate:
        tpl = self._templates.get(name)
        if tpl is None:
            raise PromptNotFoundError(f"prompt '{name}' not found in {self._base_dir}")
        # 简单语义: yaml 后端一般只有一份, version/label 仅做匹配检查 (不强制)
        if version is not None and tpl.version is not None and tpl.version != version:
            logger.debug(
                "prompt_yaml_version_mismatch",
                extra={"prompt_name": name, "asked": version, "actual": tpl.version},
            )
        return tpl

    # ---------- 工具方法 (单测用) ----------

    def list_names(self) -> list[str]:
        return list(self._templates.keys())
