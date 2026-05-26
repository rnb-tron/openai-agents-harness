"""所有 HTTP 请求默认具备的请求标识与日志上下文。"""

from fastapi import FastAPI, Request

from src.core.logging import (
    bind_log_context,
    get_rid,
    reset_log_context,
    reset_rid,
    set_rid,
)


def install_request_context(app: FastAPI) -> None:
    """安装基础请求上下文；该能力始终启用，不进入可选能力列表。"""

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        rid_token = set_rid(request.headers.get("X-Request-ID"))
        context_token = bind_log_context(
            method=request.method,
            path=request.url.path,
            client=request.client.host if request.client else None,
        )
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = get_rid() or ""
            return response
        finally:
            reset_log_context(context_token)
            reset_rid(rid_token)
