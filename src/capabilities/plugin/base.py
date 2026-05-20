"""可插拔能力 (Capability) 统一抽象

设计目标:
- 所有可插拔能力 (Memory / HITL / Checkpoint / Handoff / Tracing 等)
  实现统一的 ``Capability`` 协议,由 ``CapabilityRegistry`` 集中调度
- 通过 ``is_enabled()`` 提供"未启用零开销"语义
- 提供生命周期钩子 (setup / teardown) 与运行期钩子
  (before_run / after_run / on_error),未实现的钩子默认 no-op

不替代各 capability 的内部实现,只是在 Orchestrator 与各 capability 之间
建立一个稳定的契约层,避免 ``agent_runtime`` 中堆积 ``if mgr is not None`` 分支。
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RunPhase(str, Enum):
    """Agent 一次执行内的钩子触发阶段"""

    BEFORE_RUN = "before_run"
    AFTER_RUN = "after_run"
    ON_ERROR = "on_error"


@dataclass
class RunContext:
    """一次 Agent run 的运行上下文,贯穿所有 capability 钩子

    各 capability 可读写 ``metadata`` 字段以传递自定义数据,
    避免相互修改对方私有状态。
    """

    session_id: str
    user_id: str | None = None
    user_input: str = ""
    # 经过 memory / 其它 capability 注入后实际送入模型的 prompt
    enriched_input: str = ""
    selected_model: str = ""
    final_output: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    # 各 capability 自由读写的共享上下文
    metadata: dict[str, Any] = field(default_factory=dict)


class Capability(ABC):
    """可插拔能力基类

    子类至少要覆盖 ``name``;其它钩子按需重写,默认全部 no-op。
    """

    #: 能力唯一名称,建议使用 snake_case,如 ``"memory"``、``"hitl"``
    name: str = "capability"

    def is_enabled(self) -> bool:
        """是否启用。返回 ``False`` 时 Registry 会跳过该能力的所有钩子。

        默认启用;子类可以根据自身 config 覆盖此方法,从而实现"配置驱动开关"。
        """
        return True

    # ---------- 生命周期钩子 ----------

    async def setup(self) -> None:
        """应用启动 / Orchestrator 初始化时调用,做一次性准备工作"""
        return None

    async def teardown(self) -> None:
        """应用关闭时调用,释放资源"""
        return None

    # ---------- 运行期钩子 ----------

    async def before_run(self, ctx: RunContext) -> None:
        """模型调用之前触发,可在此修改 ``ctx.enriched_input`` 等字段"""
        return None

    async def after_run(self, ctx: RunContext) -> None:
        """模型调用成功之后触发,可在此持久化结果、记录事件等"""
        return None

    async def on_error(self, ctx: RunContext, error: Exception) -> None:
        """模型调用抛出异常时触发,默认 no-op,不会吞异常"""
        return None
