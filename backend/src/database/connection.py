"""
Async database connection pool and session management.
Uses SQLAlchemy 2.0 with asyncpg.
"""
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""

    pass


def get_engine():
    """Create async engine with connection pool settings."""
    settings = get_settings()
    db_url = settings.database_url

    # Validate DATABASE_URL is properly set
    if not db_url or db_url == "postgresql+asyncpg://user:password@localhost:5432/jobmatch":
        error_msg = (
            "DATABASE_URL is not properly configured. "
            "In Railway, set: DATABASE_URL=${{Postgres.DATABASE_URL}} "
            f"(Current value: {db_url})"
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    logger.info(f"Connecting to database: {db_url.split('@')[1] if '@' in db_url else 'unknown'}")

    return create_async_engine(
        db_url,
        pool_size=10,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=settings.environment == "development",
    )


engine = get_engine()
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields a database session. Caller must not log session contents."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def transaction() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for explicit transaction. Commits on exit, rolls back on exception."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Transaction rolled back")
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Verify database connectivity. Does not create tables (use migrations)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database connection verified")


async def close_db() -> None:
    """Dispose of the connection pool."""
    await engine.dispose()
    logger.info("Database pool disposed")
