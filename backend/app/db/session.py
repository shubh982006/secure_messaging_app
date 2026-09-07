"""Async engine + session factory.

SQLite is put into WAL mode on every connection: concurrent readers alongside a
single writer, which is exactly the shape of a chat workload (read heavy, short
writes). See SYSTEM_DESIGN.md section 2.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

_connect_args = {"check_same_thread": False} if settings.is_sqlite else {}

def _engine_kwargs() -> dict:
    kwargs: dict = {
        "echo": False,
        "future": True,
        "pool_pre_ping": settings.db_pool_pre_ping,
        "connect_args": _connect_args,
    }
    if not settings.is_sqlite:
        # SQLite serialises writers anyway, so a bigger pool buys nothing there;
        # on Postgres it is the difference between 15 concurrent transactions
        # and 50.
        kwargs.update(
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_recycle=settings.db_pool_recycle_seconds,
        )
    return kwargs


engine = create_async_engine(settings.database_url, **_engine_kwargs())

if settings.is_sqlite:

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _record) -> None:  # pragma: no cover
        cursor = dbapi_connection.cursor()
        # WAL: readers never block the writer.
        cursor.execute("PRAGMA journal_mode=WAL")
        # NORMAL is the documented-safe pairing with WAL.
        cursor.execute("PRAGMA synchronous=NORMAL")
        # Wait instead of instantly raising "database is locked" under contention.
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency - one session per request, always closed."""
    async with SessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    await engine.dispose()
