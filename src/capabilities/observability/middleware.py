"""FastAPI 中间件 - 请求级别的可观测性"""

import time
from typing import Callable

from fastapi import Request, Response
from opentelemetry import trace as otel_trace
from opentelemetry.trace import Status, StatusCode

from src.core.logging import get_rid, setup_logger

logger = setup_logger("observability.middleware")

tracer = otel_trace.get_tracer("openai-agent-sdk.api")


async def observability_middleware(request: Request, call_next: Callable) -> Response:
    """
    可观测性中间件: 为每个请求创建 Trace
    
    功能:
    - 创建请求级别的 Trace
    - 记录请求元数据 (方法/路径/客户端)
    - 记录响应状态和延迟
    - 关联 RID (Request ID)
    """
    
    # 提取请求信息
    method = request.method
    path = request.url.path
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    request_id = get_rid() or "unknown"
    
    # 创建 Span
    span_name = f"{method} {path}"
    
    with tracer.start_as_current_span(span_name) as span:
        # 记录请求属性
        span.set_attribute("http.method", method)
        span.set_attribute("http.url", str(request.url))
        span.set_attribute("http.client_ip", client_ip)
        span.set_attribute("http.user_agent", user_agent)
        span.set_attribute("http.request_id", request_id)
        
        # 记录查询参数 (脱敏)
        if request.query_params:
            span.set_attribute("http.query_params", str(request.query_params))
        
        start_time = time.time()
        
        try:
            # 处理请求
            response = await call_next(request)
            
            # 计算延迟
            duration_ms = (time.time() - start_time) * 1000
            
            # 记录响应属性
            span.set_attribute("http.status_code", response.status_code)
            span.set_attribute("http.duration_ms", duration_ms)
            
            # 添加响应头
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Trace-ID"] = str(span.get_span_context().trace_id)
            
            # 设置状态
            if 200 <= response.status_code < 400:
                span.set_status(Status(StatusCode.OK))
            else:
                span.set_status(Status(StatusCode.ERROR, f"HTTP {response.status_code}"))
            
            # 记录日志
            logger.info(
                f"{method} {path} {response.status_code} {duration_ms:.2f}ms [rid={request_id}]"
            )
            
            return response
            
        except Exception as e:
            # 计算延迟
            duration_ms = (time.time() - start_time) * 1000
            
            # 记录异常
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            span.set_attribute("http.duration_ms", duration_ms)
            
            # 记录错误日志
            logger.error(
                f"{method} {path} ERROR {duration_ms:.2f}ms [rid={request_id}]: {e}",
                exc_info=True,
            )
            
            raise
