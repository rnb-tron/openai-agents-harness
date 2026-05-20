"""模型规格表 - 用于上下文压缩按目标模型自适应预算

字段:
- ``context_window``: 模型总上下文窗口 (tokens)
- ``reserved_for_output``: 预留给模型输出的 tokens

输入预算 = (context_window - reserved_for_output) * safety_ratio
"""

from __future__ import annotations

from typing import TypedDict


class ModelSpec(TypedDict):
    context_window: int
    reserved_for_output: int


# 主流模型规格 (静态表, 后续可改为远端获取)
MODEL_SPECS: dict[str, ModelSpec] = {
    # OpenAI
    "gpt-4o": {"context_window": 128000, "reserved_for_output": 4096},
    "gpt-4o-mini": {"context_window": 128000, "reserved_for_output": 4096},
    "gpt-4.1": {"context_window": 128000, "reserved_for_output": 8192},
    "gpt-4.1-mini": {"context_window": 128000, "reserved_for_output": 8192},
    "gpt-4-turbo": {"context_window": 128000, "reserved_for_output": 4096},
    "gpt-4": {"context_window": 8192, "reserved_for_output": 1024},
    "gpt-3.5-turbo": {"context_window": 16385, "reserved_for_output": 1024},
}

# 未知模型的兜底规格 (偏保守)
DEFAULT_SPEC: ModelSpec = {"context_window": 8192, "reserved_for_output": 1024}


def get_input_budget(model: str, safety_ratio: float = 0.9) -> int:
    """计算给定模型的输入 tokens 预算

    Args:
        model: 模型名称
        safety_ratio: 安全比例 (0,1], 实际可用 = 理论可用 * ratio

    Returns:
        输入 tokens 预算 (向下取整)
    """
    spec = MODEL_SPECS.get(model, DEFAULT_SPEC)
    available = spec["context_window"] - spec["reserved_for_output"]
    return max(0, int(available * safety_ratio))
