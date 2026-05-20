from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from src.api.middleware import middleware_registry
from src.api.middleware.auth.plugin import AuthPlugin
from src.api.middleware.rate_limit.plugin import RateLimitPlugin
from src.api.routers import chat as chat_router
from src.api.routers import health as health_router
from src.api.routers import memory as memory_router
from src.core.logging import bind_log_context, get_rid, reset_log_context, reset_rid, set_rid, setup_logger
from src.core.config import current_settings
from src.infrastructure.database import close_database, init_database
from src.infrastructure.http_client import close_http_client, get_http_client
from src.infrastructure.kafka_producer import close_kafka_producer, init_kafka_producer
from src.infrastructure.redis_client import close_redis, init_redis

logger = setup_logger("src.main")


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialized = {"http": False, "redis": False, "kafka": False, "database": False, "memory": False, "observability": False}

    # Initialize Observability System (if enabled)
    if current_settings.observability_enabled:
        try:
            from src.capabilities.observability import init_observability
            
            await init_observability()
            initialized["observability"] = True
            logger.info("Observability system initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize observability system: {e}", exc_info=True)
            # 可观测系统初始化失败不影响主流程

    if current_settings.database_enabled and current_settings.database_url:
        await init_database(current_settings.database_url, echo=current_settings.debug)
        initialized["database"] = True

    if current_settings.redis_enabled:
        await init_redis(current_settings.redis_url, current_settings.redis_slave_url)
        initialized["redis"] = True

    if current_settings.kafka_enabled:
        await init_kafka_producer(
            bootstrap_servers=current_settings.kafka_bootstrap_servers,
            topic=current_settings.kafka_topic,
            enabled=True,
        )
        initialized["kafka"] = True

    if current_settings.http_client_enabled:
        await get_http_client()
        initialized["http"] = True

    # Initialize Memory System (if enabled)
    if current_settings.memory_enabled:
        try:
            from src.capabilities.memory.manager import MemoryManager
            from src.capabilities.memory.tasks import memory_scheduler
            from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
            
            # 创建专用数据库会话 (用于Memory系统)
            memory_engine = create_async_engine(
                current_settings.database_url,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
            )
            memory_session_factory = async_sessionmaker(memory_engine, expire_on_commit=False)
            
            async with memory_session_factory() as memory_session:
                memory_manager = MemoryManager(current_settings, memory_session)
                await memory_manager.init()
                app.state.memory_manager = memory_manager
                initialized["memory"] = True
                logger.info("Memory system initialized successfully")
                
                # 启动定时任务
                await memory_scheduler.start(memory_manager)
                logger.info("Memory task scheduler started")
                
        except Exception as e:
            logger.error(f"Failed to initialize memory system: {e}", exc_info=True)
            # Memory系统初始化失败不影响主流程

    # Setup protocol-layer middleware plugins (Auth/RateLimit)
    try:
        await middleware_registry.setup_all()
    except Exception as e:
        logger.error(f"middleware setup failed: {e}", exc_info=True)

    yield

    try:
        await middleware_registry.teardown_all()
    except Exception as e:
        logger.error(f"middleware teardown failed: {e}", exc_info=True)

    if initialized["observability"]:
        try:
            from src.capabilities.observability import shutdown_observability
            await shutdown_observability()
            logger.info("Observability system shutdown complete")
        except Exception as e:
            logger.error(f"Failed to shutdown observability system: {e}", exc_info=True)
    
    if initialized["memory"]:
        try:
            from src.capabilities.memory.tasks import memory_scheduler
            await memory_scheduler.stop()
            await app.state.memory_manager.close()
        except Exception as e:
            logger.error(f"Failed to close memory system: {e}", exc_info=True)
    
    if initialized["http"]:
        await close_http_client()
    if initialized["kafka"]:
        await close_kafka_producer()
    if initialized["redis"]:
        await close_redis()
    if initialized["database"]:
        await close_database()

    logger.info("Application shutdown complete")


app = FastAPI(title=current_settings.app_name, lifespan=lifespan)

# Register protocol-layer plugins.
# Order matters: Auth first so RateLimit can read request.state.principal.
# (MiddlewareRegistry handles FastAPI's LIFO stack internally.)
_auth_plugin = AuthPlugin.from_settings(current_settings)
if _auth_plugin.is_enabled():
    middleware_registry.register(_auth_plugin)
_rl_plugin = RateLimitPlugin.from_settings(current_settings)
if _rl_plugin.is_enabled():
    middleware_registry.register(_rl_plugin)
middleware_registry.install_all(app)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
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


app.include_router(health_router.router)
app.include_router(chat_router.router)
app.include_router(memory_router.router)
