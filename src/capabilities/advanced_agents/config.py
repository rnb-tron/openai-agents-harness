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


@dataclass
class CheckpointConfig:
    """Checkpoint 检查点配置"""
    enabled: bool = False
    storage_backend: str = "memory"  # 存储后端: memory, redis, database
    max_checkpoints: int = 10  # 最大检查点数量
    auto_save: bool = False  # 自动保存
    save_on_tool_call: bool = True  # 工具调用后保存
    save_interval: int = 60  # 定期保存间隔 (秒)


@dataclass
class HandoffConfig:
    """Handoff Agent 协作配置"""
    enabled: bool = False
    agents: dict[str, dict] = field(default_factory=dict)  # Agent 注册表
    default_agent: str = ""  # 默认 Agent
    max_handoffs: int = 5  # 最大 Handoff 次数


@dataclass
class AgentState:
    """Agent 状态"""
    session_id: str
    conversation_history: list[dict[str, Any]]
    current_model: str
    tool_calls: list[dict[str, Any]]
    context: dict[str, Any]
