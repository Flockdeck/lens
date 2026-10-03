"""Fixtures for worker tests. The throwaway SQLite database (`database_url`) comes from the shared
tests/conftest.py; stores are in-memory or on the filesystem (tmp_path)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from session_lens.storage.base import RecordingStore
from session_lens.storage.filesystem import FilesystemStore
from session_lens.storage.memory import InMemoryStore
from tests.dbutil import clear_tables, test_engine


@pytest_asyncio.fixture
async def sm(database_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = test_engine(database_url)
    await clear_tables(engine)
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


@pytest_asyncio.fixture
async def any_store(tmp_path: Path) -> AsyncIterator[RecordingStore]:
    """Every real store implementation (there is one: files on disk)."""
    yield FilesystemStore(tmp_path / "data")
