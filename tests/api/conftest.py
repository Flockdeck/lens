"""API test fixtures: a throwaway database on the MySQL server named by DATABASE_URL."""

import asyncio
import secrets
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from session_lens.api.app import create_app
from session_lens.api.deps import get_queue
from session_lens.config import Settings, get_settings
from session_lens.db.models import Base
from tests.api.standins import FakeQueue, importable, install_stubs

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

install_stubs()


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """Create `<db>_test_<rand>` on the server, build the schema, drop it afterwards."""
    base = make_url(get_settings().database_url)
    name = f"{base.database}_test_{secrets.token_hex(4)}"
    test_url = base.set(database=name).render_as_string(hide_password=False)

    async def run(sql: str | None, url: str | None) -> None:
        engine = create_async_engine(
            base.set(database=None).render_as_string(hide_password=False)
            if sql
            else (url or test_url),
            isolation_level="AUTOCOMMIT" if sql else None,
        )
        async with engine.begin() as conn:
            if sql:
                await conn.execute(text(sql))
            else:
                await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(run(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4", None))
    asyncio.run(run(None, test_url))
    yield test_url
    asyncio.run(run(f"DROP DATABASE `{name}`", None))


@pytest_asyncio.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(database_url)
    async with eng.begin() as conn:
        await conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(text(f"TRUNCATE TABLE `{table.name}`"))
        await conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session


@pytest_asyncio.fixture
async def app_settings(database_url: str) -> Settings:
    return Settings(
        database_url=database_url,
        api_token=TOKEN,
        max_file_bytes=1024,
        max_files_per_batch=5,
        max_request_bytes=8192,
    )


@pytest_asyncio.fixture
async def client(engine: AsyncEngine, app_settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(app_settings)
    if not importable("session_lens.worker.queue"):
        app.dependency_overrides[get_queue] = lambda: FakeQueue()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", headers=AUTH
        ) as c:
            c.app = app  # type: ignore[attr-defined]
            yield c


def jsonl(*seqs: int) -> bytes:
    import json

    return b"".join(
        json.dumps({"v": 1, "seq": s, "type": "user_prompt", "text": f"line {s}"}).encode() + b"\n"
        for s in seqs
    )


@pytest.fixture
def make_jsonl() -> Any:
    return jsonl
