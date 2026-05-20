"""超时控制"""

import asyncio
from typing import Any, Callable

from src.capabilities.model_routing.config import TimeoutConfig
from src.core.logging import setup_logger

logger = setup_logger("model_routing.timeout")


class TimeoutError(Exception):
    """超时异常"""
    pass


class TimeoutController:
    """超时预算控制器"""
    
    def __init__(self, config: TimeoutConfig):
        self.config = config
    
    async def execute(
        self,
        func: Callable,
        **kwargs
    ) -> Any:
        """
        带超时控制的执行
        
        Args:
            func: 执行函数
            **kwargs: 传递给 func 的参数
            
        Returns:
            执行结果
            
        Raises:
            TimeoutError: 超时时抛出
        """
        if not self.config.enabled:
            # 未启用超时控制,直接执行
            return await func(**kwargs)
        
        try:
            logger.debug(
                f"Executing with timeout budget: {self.config.total_timeout}s"
            )
            
            result = await asyncio.wait_for(
                func(**kwargs),
                timeout=self.config.total_timeout
            )
            
            return result
            
        except asyncio.TimeoutError:
            error_msg = f"Total timeout {self.config.total_timeout}s exceeded"
            logger.error(error_msg)
            raise TimeoutError(error_msg)
