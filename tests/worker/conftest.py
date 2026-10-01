"""Fixtures for worker tests: a throwaway MySQL database per run, built by the real Alembic
migrations, plus stand-ins for the recording/enrich modules until those components land."""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
import types
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alembic import command
from session_lens.config import Settings
from session_lens.db.models import Base


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

BASE_URL = os.environ.get(
    "DATABASE_URL",
    Settings().database_url,
)


def _admin_url() -> str:
    explicit = os.environ.get("MYSQL_ADMIN_URL")
    if explicit:
        return explicit
    return (
        make_url(BASE_URL)
        .set(username="root", password="root", database="mysql")
        .render_as_string(hide_password=False)
    )


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """A fresh database for this run, created from the Alembic migrations and dropped after."""
    name = f"session_lens_test_{uuid.uuid4().hex[:8]}"

    async def _admin(sql: str) -> None:
        engine = create_async_engine(_admin_url(), isolation_level="AUTOCOMMIT")
        async with engine.connect() as conn:
            await conn.execute(text(sql))
        await engine.dispose()

    asyncio.run(_admin(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4"))
    app_user = make_url(BASE_URL).username
    if app_user and app_user != "root":
        asyncio.run(_admin(f"GRANT ALL ON `{name}`.* TO '{app_user}'@'%'"))
    url = make_url(BASE_URL).set(database=name).render_as_string(hide_password=False)
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini"))
    cfg.attributes["url"] = url
    try:
        command.upgrade(cfg, "head")
        yield url
    finally:
        asyncio.run(_admin(f"DROP DATABASE IF EXISTS `{name}`"))


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
