"""可观测能力 - 统一入口"""

from src.capabilities.observability.config import ObservabilityConfig
from src.capabilities.observability.capability import ObservabilityCapability
from src.capabilities.observability.decorators import measure_time, observe
from src.capabilities.observability.middleware import observability_middleware
from src.capabilities.observability.plugin import ObservabilityPlugin
from src.capabilities.observability.tracer import TracerManager

# 全局实例
_observability_config: ObservabilityConfig | None = None
_tracer_manager: TracerManager | None = None


async def init_observability(config: ObservabilityConfig | None = None) -> TracerManager:
    """
    初始化可观测系统
    
    Args:
        config: 可观测性配置 (如果为 None,则从环境变量加载)
    
    Returns:
        TracerManager 实例
    
    Example:
        from src.capabilities.observability import init_observability
        
        # 在应用启动时调用
        tracer = await init_observability()
    """
    global _observability_config, _tracer_manager
    
    # 加载配置
    if config is None:
        config = ObservabilityConfig.from_env()
    
    _observability_config = config
    
    # 创建并初始化 Trace 管理器
    _tracer_manager = TracerManager(config)
    await _tracer_manager.initialize()
    
    return _tracer_manager


async def shutdown_observability() -> None:
    """
    关闭可观测系统
    
    Example:
        from src.capabilities.observability import shutdown_observability
        
        # 在应用关闭时调用
        await shutdown_observability()
    """
    global _tracer_manager
    
    if _tracer_manager:
        await _tracer_manager.shutdown()
        _tracer_manager = None


def get_tracer_manager() -> TracerManager | None:
    """
    获取 Trace 管理器实例
    
    Returns:
        TracerManager 实例或 None
    """
    return _tracer_manager


def get_config() -> ObservabilityConfig | None:
    """
    获取当前配置
    
    Returns:
        ObservabilityConfig 实例或 None
    """
    return _observability_config


__all__ = [
    "ObservabilityConfig",
    "ObservabilityCapability",
    "ObservabilityPlugin",
    "TracerManager",
    "init_observability",
    "shutdown_observability",
    "get_tracer_manager",
    "get_config",
    "observe",
    "measure_time",
    "observability_middleware",
]
