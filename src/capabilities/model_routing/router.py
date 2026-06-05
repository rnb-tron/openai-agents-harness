"""模型路由器 - 支持简单路由和弹性调用"""

from typing import Any, Callable

from src.capabilities.model_routing.config import ResilienceConfig
from src.capabilities.model_routing.runner import ExecutionMetrics, ResilientModelRunner
from src.capabilities.model_routing.specs import get_input_budget


class ModelRouter:
    """模型路由器 - 支持弹性调用 (降级、重试、超时)"""

    def __init__(
        self,
        default_model: str = "gpt-4o-mini",
        reasoning_model: str = "gpt-4.1-mini",
        resilience_config: ResilienceConfig | None = None,
    ):
        self.default_model = default_model
        self.reasoning_model = reasoning_model
        self.resilience_config = resilience_config or ResilienceConfig()

        # 如果启用了弹性调用,创建运行器
        self._resilient_runner: ResilientModelRunner | None = None
        if self.resilience_config.enabled:
            self._resilient_runner = ResilientModelRunner(self.resilience_config)

    def select(self, task_type: str | None = None) -> str:
        """选择模型 (不带弹性)"""
        if task_type == "reasoning":
            return self.reasoning_model
        return self.default_model

    def get_input_budget(self, model: str | None = None, safety_ratio: float = 0.9) -> int:
        """获取输入 tokens 预算

        Args:
            model: 显式指定模型, 缺省时用 ``default_model``
            safety_ratio: 安全比例
        """
        return get_input_budget(model or self.default_model, safety_ratio)

    def infer_task_type(self, user_input: str) -> str | None:
        """推断任务类型"""
        lowered = user_input.lower()
        keywords = ("why", "analyze", "reason", "design", "tradeoff", "explain")
        if any(token in lowered for token in keywords):
            return "reasoning"
        return None

    async def run_with_resilience(self, agent_factory: Callable, task_type: str | None = None, **kwargs) -> Any:
        """
        弹性执行模型调用

        Args:
            agent_factory: Agent 工厂函数,接收 model 参数
            task_type: 任务类型 (用于选择初始模型)
            **kwargs: 传递给 agent_factory 的参数

        Returns:
            执行结果
        """
        if not self._resilient_runner:
            # 未启用弹性调用,降级到普通执行
            model = self.select(task_type)
            agent = await agent_factory(model=model)
            return await agent

        # 如果配置了降级链路,使用配置的;否则使用当前模型作为单模型
        if not self.resilience_config.fallback.models:
            # 自动构建降级链路
            initial_model = self.select(task_type)
            self.resilience_config.fallback.models = [initial_model]

        return await self._resilient_runner.run(agent_factory, **kwargs)

    @property
    def last_metrics(self) -> ExecutionMetrics | None:
        """获取最后一次执行的指标"""
        if self._resilient_runner:
            return self._resilient_runner.last_metrics
        return None
