"""模型弹性调用配置"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FallbackConfig:
    """模型降级配置"""
    enabled: bool = False                          # 是否启用降级
    models: list[str] = field(default_factory=list)  # 降级链路 (按优先级排序)
    fallback_on: Optional[list[str]] = None        # 触发降级的异常类型名称
    
    def __post_init__(self):
        if self.fallback_on is None:
            # 默认对以下异常触发降级
            self.fallback_on = [
                "APIConnectionError",
                "APITimeoutError", 
                "RateLimitError",
                "InternalServerError"
            ]


@dataclass
class RetryConfig:
    """重试配置"""
    enabled: bool = False                          # 是否启用重试
    max_retries: int = 2                           # 最大重试次数
    initial_delay: float = 1.0                     # 初始延迟 (秒)
    max_delay: float = 10.0                        # 最大延迟 (秒)
    exponential_base: float = 2.0                  # 指数退避基数
    retry_on: Optional[list[str]] = None           # 触发重试的异常类型名称
    
    def __post_init__(self):
        if self.retry_on is None:
            # 默认对以下异常触发重试
            self.retry_on = [
                "APIConnectionError",
                "APITimeoutError",
                "RateLimitError"
            ]


@dataclass
class TimeoutConfig:
    """超时配置"""
    enabled: bool = False                          # 是否启用超时控制
    total_timeout: float = 30.0                    # 总超时时间 (秒)
    per_request_timeout: float = 10.0              # 单次请求超时 (秒)


@dataclass
class ResilienceConfig:
    """弹性调用总配置"""
    enabled: bool = False                          # 是否启用弹性调用
    fallback: FallbackConfig = field(default_factory=FallbackConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    timeout: TimeoutConfig = field(default_factory=TimeoutConfig)
    
    @classmethod
    def from_env(cls) -> "ResilienceConfig":
        """从环境变量创建配置"""
        import os
        
        # 解析降级模型列表
        fallback_chain_str = os.getenv("MODEL_FALLBACK_CHAIN", "")
        fallback_models = [m.strip() for m in fallback_chain_str.split(",") if m.strip()] if fallback_chain_str else []
        
        return cls(
            enabled=os.getenv("MODEL_RESILIENCE_ENABLED", "false").lower() == "true",
            fallback=FallbackConfig(
                enabled=os.getenv("MODEL_FALLBACK_ENABLED", "false").lower() == "true",
                models=fallback_models,
            ),
            retry=RetryConfig(
                enabled=os.getenv("MODEL_RETRY_ENABLED", "false").lower() == "true",
                max_retries=int(os.getenv("MODEL_MAX_RETRIES", "2")),
                initial_delay=float(os.getenv("MODEL_RETRY_DELAY", "1.0")),
                max_delay=float(os.getenv("MODEL_RETRY_MAX_DELAY", "10.0")),
            ),
            timeout=TimeoutConfig(
                enabled=os.getenv("MODEL_TIMEOUT_ENABLED", "false").lower() == "true",
                total_timeout=float(os.getenv("MODEL_TOTAL_TIMEOUT", "30.0")),
                per_request_timeout=float(os.getenv("MODEL_PER_REQUEST_TIMEOUT", "10.0")),
            ),
        )
