"""
高级 Agent 能力配置模型

包含:
- HITL (Human-in-the-Loop) 配置
- Checkpoint (检查点) 配置
- Handoff (Agent 协作) 配置
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HITLConfig:
    """Human-in-the-Loop 配置"""

    enabled: bool = False
    approval_timeout: float = 300.0  # 审批超时 (秒)
    approval_storage: str = "memory"  # 存储后端: memory, redis, database
    auto_approve_tools: list[str] = field(default_factory=list)  # 自动审批的工具
    require_approval_tools: list[str] = field(default_factory=list)  # 需要审批的工具

    @classmethod
    def from_settings(cls, settings: Any) -> "HITLConfig":
        """从 Harness settings 投影出 SDK 原生人工审批配置。"""
        return cls(
            enabled=getattr(settings, "hitl_enabled", False),
            approval_timeout=getattr(settings, "hitl_approval_timeout", 300.0),
            auto_approve_tools=list(getattr(settings, "hitl_auto_approve_tools", []) or []),
            require_approval_tools=list(getattr(settings, "hitl_require_approval_tools", []) or []),
        )


@dataclass
class CheckpointConfig:
    """Checkpoint 检查点配置"""

    enabled: bool = False
    storage_backend: str = "memory"  # 当前实现仅支持进程内存
    max_checkpoints: int = 10  # 最大检查点数量
    auto_save: bool = False  # 自动保存
    save_on_tool_call: bool = True  # 工具调用后保存
    save_interval: int = 60  # 定期保存间隔 (秒)

    @classmethod
    def from_settings(cls, settings: Any) -> "CheckpointConfig":
        """从 settings 投影运行前/后快照配置；当前保持内存实现。"""
        return cls(
            enabled=getattr(settings, "checkpoint_enabled", False),
            storage_backend="memory",
            max_checkpoints=getattr(settings, "checkpoint_max_checkpoints", 10),
            auto_save=getattr(settings, "checkpoint_auto_save", True),
        )


@dataclass
class HandoffConfig:
    """Handoff Agent 协作配置"""

    enabled: bool = False
    agents: dict[str, dict] = field(default_factory=dict)  # Agent 注册表
    default_agent: str = ""  # 默认 Agent
    max_handoffs: int = 5  # 最大 Handoff 次数

    @classmethod
    def from_settings(cls, settings: Any) -> "HandoffConfig":
        """从 settings 投影 SDK 原生静态 handoff 目标配置。"""
        return cls(
            enabled=getattr(settings, "handoff_enabled", False),
            agents=dict(getattr(settings, "handoff_agents", {}) or {}),
        )


@dataclass
class AgentState:
    """Agent 状态"""

    session_id: str
    conversation_history: list[dict[str, Any]]
    current_model: str
    tool_calls: list[dict[str, Any]]
    context: dict[str, Any]
