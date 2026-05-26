"""FastAPI 应用装配入口。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.middleware.assembler import build_protocol_registry
from src.api.middleware.request_context import install_request_context
from src.api.routers import chat as chat_router
from src.api.routers import health as health_router
from src.api.routers import memory as memory_router
from src.api.routers import ui as ui_router
from src.core.logging import setup_logger
from src.harness.builder import build_harness
from src.infrastructure.http_client import close_http_client, configure_http_client
from src.infrastructure.kafka_producer import close_kafka_producer, init_kafka_producer
from src.infrastructure.redis_client import close_redis, init_redis

logger = setup_logger("api.app")


def create_app(settings) -> FastAPI:
    """创建已装配 Harness 与对外协议插件的应用实例。"""
    configure_http_client(settings)
    harness = build_harness(settings)
    protocol_registry = build_protocol_registry(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        initialized = {"redis": False, "kafka": False}
        try:
            if settings.redis_enabled:
                await init_redis(settings.redis_url, settings.redis_slave_url)
                initialized["redis"] = True

            if settings.kafka_enabled:
                await init_kafka_producer(
                    bootstrap_servers=settings.kafka_bootstrap_servers,
                    topic=settings.kafka_topic,
                    enabled=True,
                )
                initialized["kafka"] = True

            await harness.setup()
            await protocol_registry.setup_all()
            yield
        except Exception as exc:
            logger.error(f"application setup failed: {exc}", exc_info=True)
            raise
        finally:
            await protocol_registry.teardown_all()
            await harness.teardown()
            await close_http_client()
            if initialized["kafka"]:
                await close_kafka_producer()
            if initialized["redis"]:
                await close_redis()
            logger.info("Application shutdown complete")

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.harness = harness
    app.state.protocol_registry = protocol_registry

    protocol_registry.install_all(app)
    # 最后注册以成为 FastAPI LIFO middleware 栈的最外层。
    install_request_context(app)

    app.include_router(health_router.router)
    app.include_router(chat_router.router)
    app.include_router(memory_router.router)
    app.include_router(ui_router.router)
    return app
