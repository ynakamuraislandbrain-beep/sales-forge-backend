"""Database connection management for Neon PostgreSQL."""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

import structlog
from app.config import get_settings

logger = structlog.get_logger(__name__)

_engine = None
async_session_factory = None


def get_session_factory() -> async_sessionmaker:
    """Get the database session factory."""
    if async_session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return async_session_factory


async def init_db() -> None:
    """Initialize database connection pool."""
    global _engine, async_session_factory
    import ssl

    settings = get_settings()
    
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    _engine = create_async_engine(
        settings.database_url,
        echo=False, 
        poolclass=NullPool,  
        connect_args={
            "ssl": ssl_context,
            "server_settings": {
                "application_name": "sales-teaching-assistant",
            },
        },
    )

    async_session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


async def close_db() -> None:
    """Close database connections."""
    global _engine
    if _engine:
        await _engine.dispose()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session dependency for FastAPI routes."""
    if async_session_factory is None:
        await init_db()

    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def test_connection() -> bool:
    """Test database connection."""
    if _engine is None:
        await init_db()

    try:
        async with _engine.connect() as conn:
            await conn.execute("SELECT 1")
        logger.info("Database connection successful")
        return True
    except Exception as e:
        logger.error("Database connection failed", error=str(e))
        return False