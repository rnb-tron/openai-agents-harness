"""自定义装饰器 - 用于手动埋点"""

import functools
import time
from typing import Any, Callable, Optional

from opentelemetry import trace as otel_trace
from opentelemetry.trace import Status, StatusCode

from src.core.logging import setup_logger

logger = setup_logger("observability.decorators")

tracer = otel_trace.get_tracer("openai-agents-harness.custom")


def observe(
    name: Optional[str] = None,
    span_type: str = "DEFAULT",
    capture_input: bool = True,
    capture_output: bool = True,
    capture_exceptions: bool = True,
):
    """
    装饰器: 为函数添加可观测性埋点

    Args:
        name: Span 名称 (默认使用函数名)
        span_type: Span 类型 (DEFAULT, LLM, TOOL, AGENT, etc.)
        capture_input: 是否捕获输入参数
        capture_output: 是否捕获返回值
        capture_exceptions: 是否捕获异常

    Example:
        @observe(name="process_user_input", span_type="TOOL")
        async def process_user_input(user_input: str) -> str:
            # 业务逻辑
            return result
    """

    def decorator(func: Callable) -> Callable:
        span_name = name or f"{func.__module__}.{func.__qualname__}"

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute("span.type", span_type)
                span.set_attribute("function.name", func.__qualname__)

                # 记录输入
                if capture_input:
                    try:
                        input_data = {
                            "args": str(args)[:1000],  # 限制长度
                            "kwargs": str(kwargs)[:1000],
                        }
                        span.set_attribute("input.data", str(input_data))
                    except Exception as e:
                        logger.warning(f"Failed to capture input: {e}")

                start_time = time.time()

                try:
                    # 执行函数
                    result = await func(*args, **kwargs)

                    # 记录输出
                    if capture_output:
                        try:
                            span.set_attribute("output.data", str(result)[:1000])
                        except Exception as e:
                            logger.warning(f"Failed to capture output: {e}")

                    # 记录延迟
                    duration_ms = (time.time() - start_time) * 1000
                    span.set_attribute("duration.ms", duration_ms)

                    span.set_status(Status(StatusCode.OK))
                    return result

                except Exception as e:
                    # 记录异常
                    if capture_exceptions:
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                        span.record_exception(e)
                        logger.error(f"Exception in {span_name}: {e}", exc_info=True)
                    raise

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute("span.type", span_type)
                span.set_attribute("function.name", func.__qualname__)

                # 记录输入
                if capture_input:
                    try:
                        input_data = {
                            "args": str(args)[:1000],
                            "kwargs": str(kwargs)[:1000],
                        }
                        span.set_attribute("input.data", str(input_data))
                    except Exception as e:
                        logger.warning(f"Failed to capture input: {e}")

                start_time = time.time()

                try:
                    # 执行函数
                    result = func(*args, **kwargs)

                    # 记录输出
                    if capture_output:
                        try:
                            span.set_attribute("output.data", str(result)[:1000])
                        except Exception as e:
                            logger.warning(f"Failed to capture output: {e}")

                    # 记录延迟
                    duration_ms = (time.time() - start_time) * 1000
                    span.set_attribute("duration.ms", duration_ms)

                    span.set_status(Status(StatusCode.OK))
                    return result

                except Exception as e:
                    # 记录异常
                    if capture_exceptions:
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                        span.record_exception(e)
                        logger.error(f"Exception in {span_name}: {e}", exc_info=True)
                    raise

        # 根据函数类型返回对应的 wrapper
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def measure_time(name: str = "operation"):
    """
    装饰器: 测量函数执行时间

    Args:
        name: 操作名称

    Example:
        @measure_time("database_query")
        async def query_database():
            # 数据库查询
            pass
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration_ms = (time.time() - start_time) * 1000
                logger.info(f"{name} took {duration_ms:.2f}ms")

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration_ms = (time.time() - start_time) * 1000
                logger.info(f"{name} took {duration_ms:.2f}ms")

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator
