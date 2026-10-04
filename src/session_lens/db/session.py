"""Async engine and session factory, built from settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from session_lens.config import Settings, get_settings

BUSY_TIMEOUT_SECONDS = 30


def make_engine(settings: Settings | None = None) -> AsyncEngine:
    """The one way an engine is made, so the API, the worker and the tests all get the same
    SQLite behaviour.

    * WAL, so readers do not block the writer and the other way round.
    * Foreign keys on (SQLite ignores them, and so ON DELETE CASCADE, unless asked).
    * Transactions start with BEGIN IMMEDIATE. A deferred transaction that reads and then
      writes can fail at once with "database is locked" when another writer got in between,
      whatever the busy timeout; taking the write lock up front makes writers queue instead.
      Transactions here are short (the slow work, the LLM call, happens outside them).
    * Except for sessions made with `read_sessionmaker`, which begin deferred: a read must not
      hold the one write lock (WAL lets it read while a writer works).
    """
    settings = settings or get_settings()
    url = make_url(settings.database_url)
    if url.get_backend_name() != "sqlite":
        raise ValueError("DATABASE_URL must be a SQLite URL (sqlite+aiosqlite:///path)")
    if url.database and url.database != ":memory:" and not url.database.startswith("file:"):
        Path(url.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(url, connect_args={"timeout": BUSY_TIMEOUT_SECONDS})

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_connection: Any, _: Any) -> None:
        dbapi_connection.isolation_level = None  # we say when a transaction begins
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_SECONDS * 1000}")
        cursor.close()

    @event.listens_for(engine.sync_engine, "begin")
    def _on_begin(connection: Any) -> None:
        deferred = connection.get_execution_options().get("deferred")
        connection.exec_driver_sql("BEGIN" if deferred else "BEGIN IMMEDIATE")

    return engine


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def read_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """For code that only reads (GET requests): sessions that never take the write lock."""
    return async_sessionmaker(engine.execution_options(deferred=True), expire_on_commit=False)


@lru_cache
def get_engine() -> AsyncEngine:
    return make_engine()


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return make_sessionmaker(get_engine())


async def dispose_engine() -> None:
    if get_engine.cache_info().currsize:
        await get_engine().dispose()
        get_sessionmaker.cache_clear()
        get_engine.cache_clear()
