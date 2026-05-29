"""FastAPI 应用装配入口。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.middleware.assembler import build_protocol_chain
from src.api.routers import advanced as advanced_router
from src.api.routers import chat as chat_router
from src.api.routers import health as health_router
from src.api.routers import memory as memory_router
from src.api.routers import ui as ui_router
from src.core.logging import setup_logger
from src.harness.builder import build_harness
from src.infrastructure.http_client import close_http_client, configure_http_client

logger = setup_logger("api.app")


def create_app(settings) -> FastAPI:
    """创建已装配 Harness 与对外协议插件的应用实例。"""
    configure_http_client(settings)
    harness = build_harness(settings)
    protocol_chain = build_protocol_chain(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            # Harness owns shared runtime resources; protocol plugins own HTTP adapters.
            await harness.setup()
            await protocol_chain.startup()
            yield
        except Exception as exc:
            logger.error(f"application setup failed: {exc}", exc_info=True)
            raise
        finally:
            await protocol_chain.shutdown()
            await harness.teardown()
            await close_http_client()
            logger.info("Application shutdown complete")

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.harness = harness
    app.state.protocol_chain = protocol_chain

    protocol_chain.install_on(app)

    app.include_router(health_router.router)
    app.include_router(chat_router.router)
    app.include_router(advanced_router.router)
    app.include_router(memory_router.router)
    app.include_router(ui_router.router)
    return app
