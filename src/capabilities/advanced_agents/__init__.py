"""
高级 Agent 能力模块

包含:
- HITL (Human-in-the-Loop) 人工审批
- Checkpoint 检查点管理
- Handoff Agent 协作
"""

from .config import (
    HITLConfig,
    CheckpointConfig,
    HandoffConfig,
    AgentState,
)

from .hitl import (
    ApprovalManager,
    ApprovalRequest,
    ApprovalStatus,
)

from .checkpoint import (
    CheckpointManager,
    Checkpoint,
)

from .handoff import (
    HandoffManager,
)

from .capabilities import (
    CheckpointCapability,
    HandoffCapability,
    HITLCapability,
)

__all__ = [
    # Config
    "HITLConfig",
    "CheckpointConfig",
    "HandoffConfig",
    "AgentState",
    # HITL
    "ApprovalManager",
    "ApprovalRequest",
    "ApprovalStatus",
    # Checkpoint
    "CheckpointManager",
    "Checkpoint",
    # Handoff
    "HandoffManager",
    # Capability adapters
    "CheckpointCapability",
    "HandoffCapability",
    "HITLCapability",
]
