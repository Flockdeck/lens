"""Fixtures for worker tests: a throwaway MySQL database per run, built by the real Alembic
migrations, plus stand-ins for the recording/enrich modules until those components land."""

from __future__ import annotations

import importlib
import sys
import types
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from session_lens.config import Settings, get_settings
from session_lens.db.models import Base
from session_lens.storage.base import RecordingStore, build_store
from session_lens.storage.memory import InMemoryStore


def _ensure_module(name: str, **attrs: object) -> None:
    """Register a minimal stand-in for `name` if the real module is not there (yet)."""
    try:
        importlib.import_module(name)
    except ImportError:
        module = types.ModuleType(name)
        module.__dict__.update(attrs)
        sys.modules[name] = module


class _UnsupportedVersion(Exception): ...


class _EmptyRecording(Exception): ...


class _EnrichmentError(Exception):
    def __init__(self, message: str = "", retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


def _unavailable(*_: object) -> None:
    raise NotImplementedError


_ensure_module("session_lens.recording.models", Analysis=object)
_ensure_module(
    "session_lens.recording.parser",
    UnsupportedVersion=_UnsupportedVersion,
    EmptyRecording=_EmptyRecording,
    parse=_unavailable,
    analyze=_unavailable,
)
_ensure_module(
    "session_lens.enrich.base",
    EnrichmentResult=object,
    EnrichmentError=_EnrichmentError,
    Enricher=object,
    build_enricher=_unavailable,
)

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


@pytest_asyncio.fixture
async def s3_store() -> AsyncIterator[RecordingStore]:
    """The real S3 path against the compose object store, under a prefix unique to the test."""
    patch = pytest.MonkeyPatch()
    patch.setattr(get_settings(), "s3_prefix", f"recordings/test-{uuid.uuid4().hex[:8]}/")
    s3 = build_store(Settings())
    yield s3
    await s3.aclose()
    patch.undo()
