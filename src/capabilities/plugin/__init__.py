"""可插拔能力公共抽象 (Capability / Registry / RunContext)

这是 Agent Harness "可插拔" 设计的契约层:
- 所有 capability 实现 ``Capability`` 接口
- ``CapabilityRegistry`` 统一调度生命周期与运行期钩子
- ``RunContext`` 在一次 Agent run 中贯穿所有钩子

后续 ``agent_runtime`` 会替换为基于 Registry 的统一调度,
取代当前散落的 ``if mgr is not None`` 判断。
"""

from .base import Capability, RunContext, RunPhase
from .hooks import HookCapability
from .registry import CapabilityRegistry

__all__ = [
    "Capability",
    "RunContext",
    "RunPhase",
    "CapabilityRegistry",
    "HookCapability",
]
