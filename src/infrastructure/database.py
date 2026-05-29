"""共享数据库资源与会话工厂。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from src.core.logging import service_logger

Base = declarative_base()


@dataclass(frozen=True)
class DatabaseConfig:
    """SQLAlchemy 异步连接池配置。"""

    url: str
    echo: bool = False
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout_seconds: float = 30.0
    pool_recycle_seconds: int = 1800
    pool_pre_ping: bool = True

    @classmethod
    def from_settings(cls, settings: Any) -> "DatabaseConfig":
        return cls(
            url=settings.database_url,
            echo=bool(getattr(settings, "debug", False)),
            pool_size=int(getattr(settings, "database_pool_size", 10)),
            max_overflow=int(getattr(settings, "database_max_overflow", 20)),
            pool_timeout_seconds=float(
                getattr(settings, "database_pool_timeout_seconds", 30.0)
            ),
            pool_recycle_seconds=int(
                getattr(settings, "database_pool_recycle_seconds", 1800)
            ),
            pool_pre_ping=bool(getattr(settings, "database_pool_pre_ping", True)),
        )


class DatabaseResource:
    """由 Harness 持有的一套共享 engine 与 session factory。"""

    def __init__(self, config: DatabaseConfig) -> None:
        if not config.url:
            raise ValueError("DATABASE_URL is required to initialize database resource")
        self.config = config
        pool_pre_ping = config.pool_pre_ping
        if config.url.startswith("mysql+aiomysql"):
            # SQLAlchemy 的 aiomysql 适配器在 pre_ping 时会调用 PyMySQL 风格
            # ping()，而 aiomysql 需要 reconnect 参数；关闭 pre_ping 可避免
            # 连接复用阶段触发 TypeError。
            pool_pre_ping = False

        connect_args: dict[str, Any] = {
            "echo": config.echo,
            "pool_pre_ping": pool_pre_ping,
        }
        if not config.url.startswith("sqlite"):
            connect_args.update(
                {
                    "pool_recycle": config.pool_recycle_seconds,
                    "pool_size": config.pool_size,
                    "max_overflow": config.max_overflow,
                    "pool_timeout": config.pool_timeout_seconds,
                }
            )
        self.engine: AsyncEngine = create_async_engine(
            config.url,
            **connect_args,
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    def session(self) -> AsyncSession:
        return self.session_factory()

    async def create_all(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self.engine.dispose()
        service_logger.info("Database resource closed")


_database_resource: DatabaseResource | None = None


async def init_database(
    database_url: str,
    echo: bool = False,
    *,
    pool_size: int = 10,
    max_overflow: int = 20,
    pool_timeout_seconds: float = 30.0,
    pool_recycle_seconds: int = 1800,
    pool_pre_ping: bool = True,
) -> DatabaseResource:
    """兼容入口；新装配路径优先由 HarnessBuilder 创建资源。"""
    global _database_resource
    _database_resource = DatabaseResource(
        DatabaseConfig(
            url=database_url,
            echo=echo,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout_seconds=pool_timeout_seconds,
            pool_recycle_seconds=pool_recycle_seconds,
            pool_pre_ping=pool_pre_ping,
        )
    )
    service_logger.info("Database initialized")
    return _database_resource


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    if _database_resource is None:
        raise RuntimeError("Database not initialized")
    async with _database_resource.session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_database() -> None:
    global _database_resource
    if _database_resource is not None:
        await _database_resource.close()
        _database_resource = None
