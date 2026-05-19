from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from src.core.logging import service_logger

Base = declarative_base()
engine = None
async_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_database(database_url: str, echo: bool = False) -> None:
    global engine, async_session_factory
    engine = create_async_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
        pool_recycle=3600,
        pool_size=20,
        max_overflow=40,
    )
    async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    service_logger.info("Database initialized")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    if async_session_factory is None:
        raise RuntimeError("Database not initialized")
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_database() -> None:
    global engine
    if engine:
        await engine.dispose()
        service_logger.info("Database closed")
