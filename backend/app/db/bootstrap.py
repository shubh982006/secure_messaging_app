"""Schema + seed bootstrap run once at application startup.

Alembic owns the schema (``alembic upgrade head``). For the hosted demo we also
run it programmatically on boot so a fresh container comes up with a usable
database and known logins, then seed idempotently if the DB is empty.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.db.base import Base
from app.db.session import SessionFactory, engine
from app.models import User

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


def _run_alembic_upgrade() -> None:
    from alembic import command
    from alembic.config import Config

    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(config, "head")


async def create_schema() -> None:
    if ALEMBIC_INI.exists():
        try:
            # Alembic is sync; keep the event loop free while it runs.
            await asyncio.to_thread(_run_alembic_upgrade)
            logger.info("schema: alembic upgrade head")
            return
        except Exception as exc:  # pragma: no cover - fall back, never block boot
            logger.warning("alembic upgrade failed (%s); falling back to create_all", exc)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    logger.info("schema: metadata.create_all")


async def prepare_database() -> None:
    await create_schema()

    if not settings.seed_on_startup:
        return

    async with SessionFactory() as db:
        already_seeded = await db.scalar(select(User).limit(1))
    if already_seeded is not None:
        logger.info("seed: database already populated, skipping")
        return

    from app.seed import seed_database

    await seed_database()
