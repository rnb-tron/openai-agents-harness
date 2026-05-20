"""Langfuse + OpenTelemetry Trace 管理器"""

import logging
from typing import Optional, Any

from langfuse import get_client
# Langfuse 4.x 不再需要单独导入 Langfuse 类
from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor

from src.capabilities.observability.config import ObservabilityConfig
from src.core.logging import setup_logger

logger = setup_logger("observability.tracer")


class TracerManager:
    """Trace 管理器 - 负责初始化和管理 Langfuse + OpenTelemetry"""
    
    def __init__(self, config: ObservabilityConfig):
        self.config = config
        self._langfuse: Optional[Langfuse] = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """初始化 Langfuse 和 OpenTelemetry"""
        if not self.config.enabled:
            logger.info("Observability is disabled")
            return
        
        if self._initialized:
            logger.warning("Observability already initialized")
            return
        
        try:
            # 验证配置
            self.config.validate()
            
            # 初始化 Langfuse 客户端
            self._langfuse = get_client()
            
            # 验证连接
            if self._langfuse.auth_check():
                logger.info("Langfuse authentication successful")
            else:
                logger.error("Langfuse authentication failed")
                raise ValueError("Langfuse authentication failed. Please check your credentials.")
            
            # 初始化 OpenTelemetry 自动埋点
            if self.config.tracing_enabled:
                OpenAIAgentsInstrumentor().instrument()
                logger.info("OpenAI Agents instrumentation enabled")
            
            self._initialized = True
            logger.info("Observability system initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize observability: {e}", exc_info=True)
            raise
    
    async def shutdown(self) -> None:
        """关闭 Trace 管理器"""
        if not self._initialized:
            return
        
        try:
            if self._langfuse:
                # 刷新所有待上报的数据
                self._langfuse.flush()
                logger.info("Langfuse data flushed")
            
            # 关闭 OpenTelemetry
            if self.config.tracing_enabled:
                OpenAIAgentsInstrumentor().uninstrument()
                logger.info("OpenAI Agents instrumentation disabled")
            
            self._initialized = False
            logger.info("Observability system shutdown complete")
            
        except Exception as e:
            logger.error(f"Failed to shutdown observability: {e}", exc_info=True)
    
    @property
    def langfuse(self) -> Optional[Any]:
        """获取 Langfuse 客户端"""
        return self._langfuse
    
    @property
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized
    
    def get_trace_url(self, trace_id: str) -> str:
        """生成 Trace URL"""
        if not self._langfuse:
            return ""
        
        base_url = self.config.base_url.rstrip("/")
        return f"{base_url}/project/{self._langfuse.project_id}/traces/{trace_id}"
