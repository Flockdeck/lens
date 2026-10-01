"""Fixtures for worker tests. The throwaway MySQL database (`database_url`) comes from the shared
tests/conftest.py; stores are in-memory, filesystem (tmp_path) or, when S3_ENDPOINT_URL is set
and reachable, the optional S3 store."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from session_lens.config import Settings, get_settings
from session_lens.db.models import Base
from session_lens.storage.base import RecordingStore, build_store
from session_lens.storage.filesystem import FilesystemStore
from session_lens.storage.memory import InMemoryStore


@pytest_asyncio.fixture
async def sm(database_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(database_url)
    async with engine.begin() as conn:
        await conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(text(f"TRUNCATE TABLE `{table.name}`"))
        await conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture(autouse=True)
def fake_recording(monkeypatch: pytest.MonkeyPatch) -> None:
    from session_lens.worker import processor
    from tests.worker.helpers import fake_analyze, fake_parse

    monkeypatch.setattr(processor, "parse", fake_parse)
    monkeypatch.setattr(processor, "analyze", fake_analyze)


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def fs_store(tmp_path: Path) -> FilesystemStore:
    return FilesystemStore(tmp_path / "data")


async def _open_s3() -> AsyncIterator[RecordingStore]:
    """The optional S3 store against a local S3-compatible server (`docker compose --profile s3
    up`), under a prefix unique to the test. Skipped unless S3_ENDPOINT_URL is set and the
    bucket is reachable."""
    if not os.environ.get("S3_ENDPOINT_URL"):
        pytest.skip("S3_ENDPOINT_URL not set")
    pytest.importorskip("aioboto3")
    patch = pytest.MonkeyPatch()
    patch.setattr(get_settings(), "s3_prefix", f"recordings/test-{uuid.uuid4().hex[:8]}/")
    s3 = build_store(Settings(storage="s3"))
    try:
        await s3.ping()
    except Exception:
        await s3.aclose()
        patch.undo()
        pytest.skip("S3 store not reachable")
    try:
        yield s3
    finally:
        await s3.aclose()
        patch.undo()


@pytest_asyncio.fixture
async def s3_store() -> AsyncIterator[RecordingStore]:
    async for s3 in _open_s3():
        yield s3


@pytest_asyncio.fixture(params=["filesystem", "s3"])
async def any_store(
    request: pytest.FixtureRequest, tmp_path: Path
) -> AsyncIterator[RecordingStore]:
    """Every real store implementation (s3 is skipped when not configured)."""
    if request.param == "filesystem":
        yield FilesystemStore(tmp_path / "data")
    else:
        async for s3 in _open_s3():
            yield s3


@pytest.fixture
def s3_store_sync() -> None:
    """For sync tests (the CLI): skip unless the optional S3 server is configured and reachable."""
    if not os.environ.get("S3_ENDPOINT_URL"):
        pytest.skip("S3_ENDPOINT_URL not set")
    pytest.importorskip("aioboto3")

    async def reachable() -> None:
        store = build_store(Settings(storage="s3"))
        try:
            await store.ping()
        finally:
            await store.aclose()

    try:
        asyncio.run(reachable())
    except Exception:
        pytest.skip("S3 store not reachable")
