"""Token 计数工具 - 复用 tiktoken, 失败兜底估算"""

from __future__ import annotations

try:
    import tiktoken  # type: ignore

    _ENC = tiktoken.get_encoding("cl100k_base")
except Exception:  # pragma: no cover - tiktoken 缺失或加载失败时兜底
    _ENC = None


def count_tokens(text: str) -> int:
    """计算文本 tokens 数

    优先使用 ``cl100k_base`` (GPT-3.5/4 通用); 失败时按 ``len/4`` 粗略估算。
    """
    if not text:
        return 0
    if _ENC is None:
        return max(1, len(text) // 4)
    try:
        return len(_ENC.encode(text))
    except Exception:
        return max(1, len(text) // 4)
