from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("SEED_ON_STARTUP", "false")

import httpx  # noqa: E402
from httpx import ASGITransport  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool, StaticPool  # noqa: E402

from app.api.deps import get_db  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.search_index import ensure_search_index  # noqa: E402
from app.main import app  # noqa: E402
from app.ws.manager import InMemoryConnectionManager  # noqa: E402


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# The suite runs against SQLite by default and against Postgres when asked, so
# "the domain code is database-agnostic" is something CI proves rather than
# something the README asserts:
#
#   TEST_DATABASE_URL=postgresql+asyncpg://user@localhost/signal_test pytest -q
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
async def engine():
    if TEST_DATABASE_URL:
        test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
        async with test_engine.begin() as connection:
            # Each test gets a pristine schema; Postgres has no in-memory mode.
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
            await connection.run_sync(ensure_search_index)
        yield test_engine
        async with test_engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await test_engine.dispose()
        return

    # One shared in-memory connection so every session sees the same schema.
    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(ensure_search_index)
    yield test_engine
    await test_engine.dispose()


@pytest.fixture
async def session_factory(engine):
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def db(session_factory) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(session_factory) -> AsyncIterator[httpx.AsyncClient]:
    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    # Fresh manager per test so presence from one test cannot leak into another.
    import app.services.serializers as serializers
    import app.services.presence_service as presence
    import app.ws.gateway as gateway
    import app.ws.manager as manager
    import app.services.message_service as message_service
    import app.services.conversation_service as conversation_service

    fresh = InMemoryConnectionManager()
    for module in (
        manager,
        serializers,
        presence,
        gateway,
        message_service,
        conversation_service,
    ):
        module.connection_manager = fresh

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as async_client:
        yield async_client

    app.dependency_overrides.clear()


async def register(client: httpx.AsyncClient, phone: str, name: str) -> dict:
    await client.post("/api/v1/auth/request-otp", json={"phone_number": phone})
    response = await client.post(
        "/api/v1/auth/verify-otp", json={"phone_number": phone, "code": "123456"}
    )
    data = response.json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    await client.patch("/api/v1/users/me", json={"display_name": name}, headers=headers)
    return {"id": data["user"]["id"], "headers": headers, "tokens": data}
