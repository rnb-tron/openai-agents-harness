"""重试策略"""

import asyncio
import random
from typing import Any, Callable

from openai import (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
)

from src.capabilities.model_routing.config import RetryConfig
from src.core.logging import setup_logger

logger = setup_logger("model_routing.retry")


class MaxRetriesExceededError(Exception):
    """超过最大重试次数异常"""
    
    def __init__(self, message: str, attempts: int, last_error: Exception):
        super().__init__(message)
        self.attempts = attempts
        self.last_error = last_error


class RetryExecutor:
    """指数退避重试执行器"""
    
    def __init__(self, config: RetryConfig):
        self.config = config
    
    async def execute(
        self,
        func: Callable,
        **kwargs
    ) -> Any:
        """
        执行重试逻辑
        
        Args:
            func: 执行函数
            **kwargs: 传递给 func 的参数
            
        Returns:
            执行结果
            
        Raises:
            MaxRetriesExceededError: 超过最大重试次数时抛出
        """
        if not self.config.enabled:
            # 未启用重试,直接执行
            return await func(**kwargs)
        
        last_error: Exception | None = None
        delay = self.config.initial_delay
        
        for attempt in range(self.config.max_retries + 1):
            try:
                if attempt > 0:
                    logger.info(
                        "retry_attempt",
                        attempt=attempt,
                        max_retries=self.config.max_retries
                    )
                
                result = await func(**kwargs)
                
                if attempt > 0:
                    logger.info(
                        "retry_succeeded",
                        attempt=attempt
                    )
                
                return result
                
            except Exception as e:
                last_error = e
                
                # 检查是否应该重试
                if not self._should_retry(e):
                    logger.error(
                        "non_recoverable_error",
                        error_type=type(e).__name__,
                        error_message=str(e)
                    )
                    raise
                
                # 最后一次尝试,不再等待
                if attempt == self.config.max_retries:
                    break
                
                # 指数退避等待
                logger.warning(
                    "retry_attempt_failed",
                    attempt=attempt + 1,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    retry_delay=delay
                )
                await asyncio.sleep(delay)
                
                # 更新延迟 (指数增长 + 随机抖动)
                jitter = random.uniform(0, delay * 0.1)  # 10% 抖动
                delay = min(delay * self.config.exponential_base + jitter, self.config.max_delay)
        
        # 所有重试都失败
        error_msg = (
            f"Max retries ({self.config.max_retries}) exceeded. "
            f"Last error: {type(last_error).__name__}: {last_error}"
        )
        logger.error(
            "max_retries_exceeded",
            max_retries=self.config.max_retries,
            last_error_type=type(last_error).__name__,
            last_error_message=str(last_error)
        )
        
        raise MaxRetriesExceededError(error_msg, self.config.max_retries + 1, last_error)
    
    def _should_retry(self, error: Exception) -> bool:
        """检查是否应该重试"""
        error_type = type(error).__name__
        return error_type in self.config.retry_on
