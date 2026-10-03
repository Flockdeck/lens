"""API test fixtures: a throwaway SQLite database (see tests/conftest.py)."""

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
)

from session_lens.api.app import create_app
from session_lens.api.deps import get_store_provider
from session_lens.config import Settings
from session_lens.db.session import read_sessionmaker
from session_lens.storage.memory import InMemoryStore
from tests.dbutil import clear_tables, test_engine


@pytest_asyncio.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    eng = test_engine(database_url)
    await clear_tables(eng)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    # Deferred, like a GET: a test that reads must not hold the write lock against the app.
    async with read_sessionmaker(engine)() as session:
        yield session


@pytest_asyncio.fixture
async def app_settings(database_url: str) -> Settings:
    return Settings(
        database_url=database_url,
        allowed_hosts=["test"],
        max_file_bytes=1024,
        max_files_per_batch=5,
        max_request_bytes=8192,
    )


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest_asyncio.fixture
async def client(
    engine: AsyncEngine, app_settings: Settings, store: InMemoryStore
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(app_settings)
    app.dependency_overrides[get_store_provider] = lambda: lambda: store
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            c.app = app  # type: ignore[attr-defined]
            yield c


def jsonl(*seqs: int) -> bytes:
    """A small valid v1 recording with one user_prompt event per given seq."""
    import json

    return b"".join(
        json.dumps(
            {
                "v": 1,
                "seq": seq,
                "time": f"2026-01-05T10:00:{seq % 60:02d}Z",
                "session": "sess-1",
                "pane": "pane-1",
                "project": "proj",
                "agent": "claude",
                "model": "m1",
                "type": "user_prompt",
                "text": f"prompt {seq}",
            }
        ).encode()
        + b"\n"
        for seq in seqs
    )


@pytest.fixture
def make_jsonl() -> Any:
    return jsonl
