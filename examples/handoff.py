"""本地展示配置驱动的 OpenAI Agents SDK 原生 Handoff 目标装配。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import AsyncOpenAI, OpenAIChatCompletionsModel

from src.capabilities.advanced_agents import HandoffConfig, HandoffManager


def build_demo_model() -> OpenAIChatCompletionsModel:
    """构造 SDK 模型对象；本示例不会实际发起模型请求。"""
    client = AsyncOpenAI(api_key="example-not-used")
    return OpenAIChatCompletionsModel(model="example-model", openai_client=client)


def main() -> None:
    config = HandoffConfig(
        enabled=True,
        agents={
            "billing": {
                "description": "处理账单与退款问题",
                "instructions": "你是账单专家，只处理账单相关请求。",
            },
            "technical_support": {
                "description": "处理技术支持问题",
                "instructions": "你是技术支持专家，聚焦故障排查。",
            },
            "disabled_target": {
                "enabled": False,
                "instructions": "该目标不会被装配。",
            },
        },
    )
    manager = HandoffManager(config)

    targets = manager.build_configured_handoffs(build_demo_model())

    print("配置驱动生成的 handoff 目标：")
    for target in targets:
        print(f"- {target.name}: {target.handoff_description}")
    print("\nRuntime 会将这些目标传入主 Agent 的 `handoffs` 参数。")


if __name__ == "__main__":
    main()
