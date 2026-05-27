"""Langfuse 可观测能力配置"""

import os
from dataclasses import dataclass, field
from typing import Optional

DEFAULT_LANGFUSE_BASE_URL = "http://agent-otel-test.ke.com"


@dataclass
class ObservabilityConfig:
    """Langfuse 可观测性配置"""
    
    # Langfuse 认证
    public_key: str = ""
    secret_key: str = ""
    base_url: str = DEFAULT_LANGFUSE_BASE_URL
    
    # 功能开关
    enabled: bool = False
    tracing_enabled: bool = True
    metrics_enabled: bool = True
    
    # 性能优化
    async_enabled: bool = True
    batch_size: int = 100
    flush_interval: float = 5.0  # 秒
    
    # 采样策略 (0.0 - 1.0)
    sampling_rate: float = 1.0
    
    # 隐私保护
    mask_pii: bool = True
    
    # 超时配置
    request_timeout: int = 30  # 秒
    
    # 重试配置
    max_retries: int = 3
    retry_delay: float = 1.0  # 秒
    
    # 自定义标签
    environment: str = "development"
    application: str = "openai-agent-sdk"
    version: str = "0.1.0"
    
    @classmethod
    def from_env(cls) -> "ObservabilityConfig":
        """从环境变量加载配置"""
        return cls(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
            base_url=os.getenv("LANGFUSE_BASE_URL", DEFAULT_LANGFUSE_BASE_URL),
            enabled=os.getenv("LANGFUSE_ENABLED", "false").lower() == "true",
            tracing_enabled=os.getenv("LANGFUSE_TRACING_ENABLED", "true").lower() == "true",
            metrics_enabled=os.getenv("LANGFUSE_METRICS_ENABLED", "true").lower() == "true",
            sampling_rate=float(os.getenv("LANGFUSE_SAMPLING_RATE", "1.0")),
            mask_pii=os.getenv("LANGFUSE_MASK_PII", "true").lower() == "true",
            environment=os.getenv("APP_PROFILE", "development"),
        )
    
    def validate(self) -> bool:
        """验证配置是否有效"""
        if not self.enabled:
            return True
        
        if not self.public_key or not self.secret_key:
            raise ValueError(
                "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are required when observability is enabled"
            )
        
        if not 0.0 <= self.sampling_rate <= 1.0:
            raise ValueError("LANGFUSE_SAMPLING_RATE must be between 0.0 and 1.0")
        
        return True
