"""弹性模型运行器 - 组合降级、重试、超时策略"""

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from src.capabilities.model_routing.config import ResilienceConfig
from src.capabilities.model_routing.fallback import ModelFallback, ModelFallbackError
from src.capabilities.model_routing.retry import MaxRetriesExceededError, RetryExecutor
from src.capabilities.model_routing.timeout import TimeoutController
from src.core.logging import setup_logger

logger = setup_logger("model_routing.runner")


@dataclass
class ExecutionMetrics:
    """执行指标"""
    start_time: float = 0.0
    end_time: float = 0.0
    total_duration: float = 0.0
    models_tried: list[str] = field(default_factory=list)
    fallback_count: int = 0
    retry_count: int = 0
    success_model: str = ""
    error: str = ""


class ResilientModelRunner:
    """
    弹性模型运行器
    
    组合三层策略:
    - 外层: 超时控制
    - 中层: 模型降级
    - 内层: 重试机制
    
    使用示例:
        runner = ResilientModelRunner(config)
        result = await runner.run(
            agent_factory=create_agent,
            input=user_input
        )
    """
    
    def __init__(self, config: ResilienceConfig):
        self.config = config
        self.fallback = ModelFallback(config.fallback)
        self.retry = RetryExecutor(config.retry)
        self.timeout = TimeoutController(config.timeout)
        self.metrics = ExecutionMetrics()
    
    async def run(
        self,
        agent_factory: Callable,
        **kwargs
    ) -> Any:
        """
        执行弹性模型调用
        
        Args:
            agent_factory: Agent 工厂函数,接收 model 参数
            **kwargs: 传递给 Runner.run 的参数
            
        Returns:
            Runner.run 的结果
        """
        self.metrics = ExecutionMetrics()
        self.metrics.start_time = time.time()
        
        if not self.config.enabled:
            # 未启用弹性调用,直接执行
            logger.debug("Resilience not enabled, executing directly")
            model = self.config.fallback.models[0] if self.config.fallback.models else "gpt-4o-mini"
            agent = await agent_factory(model=model)
            result = await agent  # agent_factory 应该返回一个协程
            self.metrics.end_time = time.time()
            self.metrics.total_duration = self.metrics.end_time - self.metrics.start_time
            self.metrics.success_model = model
            return result
        
        try:
            # 外层: 超时控制
            async def with_timeout():
                # 中层: 降级策略
                async def with_fallback(model):
                    # 内层: 重试策略
                    async def with_retry():
                        self.metrics.models_tried.append(model)
                        
                        # 创建 Agent
                        agent = await agent_factory(model=model)
                        
                        # 运行 Agent
                        return await agent  # agent 应该是 Runner.run 的协程
                    
                    return await self.retry.execute(with_retry)
                
                return await self.fallback.execute(with_fallback)
            
            result = await self.timeout.execute(with_timeout)
            
            # 记录成功指标
            self.metrics.end_time = time.time()
            self.metrics.total_duration = self.metrics.end_time - self.metrics.start_time
            self.metrics.success_model = self.metrics.models_tried[-1] if self.metrics.models_tried else ""
            self.metrics.fallback_count = len(self.metrics.models_tried) - 1
            
            logger.info(
                "execution_succeeded",
                extra={
                    "model": self.metrics.success_model,
                    "duration_ms": int(self.metrics.total_duration * 1000),
                    "fallback_count": self.metrics.fallback_count,
                },
            )
            
            return result
            
        except Exception as e:
            # 记录失败指标
            self.metrics.end_time = time.time()
            self.metrics.total_duration = self.metrics.end_time - self.metrics.start_time
            self.metrics.error = f"{type(e).__name__}: {e}"
            
            logger.error(
                "execution_failed",
                extra={
                    "duration_ms": int(self.metrics.total_duration * 1000),
                    "error_type": type(e).__name__,
                    "error_message": self.metrics.error,
                },
            )
            raise
    
    @property
    def last_metrics(self) -> ExecutionMetrics:
        """获取最后一次执行的指标"""
        return self.metrics
