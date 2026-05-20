"""Prompt 管理 Capability 异常类层级

- PromptError: 基类
- PromptNotFoundError: 指定 name 在所选后端找不到
- PromptFetchError: 后端调用本身失败 (网络/鉴权/SDK 异常)
"""

from __future__ import annotations


class PromptError(RuntimeError):
    """Prompt 管理基础异常"""


class PromptNotFoundError(PromptError):
    """指定 name 在后端不存在"""


class PromptFetchError(PromptError):
    """后端调用失败 (network / auth / SDK 异常)"""
