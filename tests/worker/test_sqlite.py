"""How the SQLite database is set up and what that buys: concurrent writers queue instead of
failing, readers never hold the write lock, and foreign keys cascade."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lens.config import Settings
from lens.db.models import AppSetting, Enrichment, Session
from lens.db.session import make_engine, make_sessionmaker, read_sessionmaker
from tests.dbutil import clear_tables, test_engine


def test_the_database_defaults_to_a_file_in_the_data_directory(tmp_path: Path) -> None:
    settings = Settings(data_dir=str(tmp_path / "my data"), database_url="")
    assert settings.database_url.startswith("sqlite+aiosqlite:///")
    assert settings.database_url.endswith("my data/lens.db")  # spaces are fine


def test_the_default_data_directory_is_the_users_own() -> None:
    from platformdirs import user_data_dir

    assert Settings().data_dir == user_data_dir("lens", appauthor=False)


def test_an_explicit_database_url_wins(tmp_path: Path) -> None:
    url = f"sqlite+aiosqlite:///{(tmp_path / 'x.db').as_posix()}"
    assert Settings(data_dir=str(tmp_path), database_url=url).database_url == url


def test_only_sqlite_is_accepted() -> None:
    with pytest.raises(ValueError, match="SQLite"):
        make_engine(Settings(database_url="mysql+asyncmy://u:p@localhost/db"))


async def test_the_database_folder_is_created(tmp_path: Path) -> None:
    settings = Settings(data_dir=str(tmp_path / "a" / "b"), database_url="")
    engine = make_engine(settings)
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    await engine.dispose()
    assert (tmp_path / "a" / "b" / "lens.db").exists()


async def test_pragmas(database_url: str) -> None:
    engine = test_engine(database_url)
    async with engine.connect() as conn:
        assert (await conn.execute(text("PRAGMA journal_mode"))).scalar() == "wal"
        assert (await conn.execute(text("PRAGMA foreign_keys"))).scalar() == 1
        assert (await conn.execute(text("PRAGMA busy_timeout"))).scalar() == 30_000
    await engine.dispose()


async def test_deleting_a_session_cascades_to_its_enrichment(
    sm: async_sessionmaker[AsyncSession],
) -> None:
    from datetime import datetime

    async with sm() as db:
        row = Session(
            recording_session="s",
            content_hash="h",
            completeness="clean",
            metrics={},
        )
        db.add(row)
        await db.flush()
        db.add(
            Enrichment(
                session_id=row.id,
                prompt_version="v",
                model="m",
                summary="s",
                category="other",
                outcome="done",
                frustration=0.0,
                created_at=datetime(2026, 1, 1),
            )
        )
        await db.commit()
        await db.delete(row)
        await db.commit()
        assert await db.scalar(select(func.count()).select_from(Enrichment)) == 0


async def test_concurrent_read_then_write_transactions_queue_instead_of_failing(
    sm: async_sessionmaker[AsyncSession],
) -> None:
    """The lost-update pattern: read a value, then write it back plus one. Run 25 at once. A
    deferred transaction would fail some of these at once with 'database is locked'."""
    async with sm() as db:
        db.add(AppSetting(key="ollama_model", value="0"))
        await db.commit()

    async def bump() -> None:
        async with sm() as db:
            row = await db.get(AppSetting, "ollama_model")
            assert row is not None
            await asyncio.sleep(0.005)  # others are queued behind this transaction's lock
            row.value = str(int(row.value) + 1)
            await db.commit()

    await asyncio.gather(*(bump() for _ in range(25)))
    async with sm() as db:
        row = await db.get(AppSetting, "ollama_model")
        assert row is not None and row.value == "25"  # no update was lost


async def test_a_reader_does_not_hold_up_a_writer(database_url: str) -> None:
    engine = test_engine(database_url)
    await clear_tables(engine)
    write, read = make_sessionmaker(engine), read_sessionmaker(engine)
    async with read() as reader:
        await reader.execute(select(AppSetting))  # a transaction, left open
        started = time.monotonic()
        async with write() as writer:
            writer.add(AppSetting(key="ollama_model", value="x"))
            await writer.commit()
        assert time.monotonic() - started < 2
        # and the reader still sees its own consistent snapshot, not the new row
        assert (await reader.execute(select(AppSetting))).scalars().all() == []
    await engine.dispose()


async def test_a_writer_does_not_hold_up_a_reader(database_url: str) -> None:
    engine = test_engine(database_url)
    await clear_tables(engine)
    write, read = make_sessionmaker(engine), read_sessionmaker(engine)
    async with write() as writer:
        writer.add(AppSetting(key="ollama_model", value="x"))
        await writer.flush()  # the write lock is held and uncommitted
        started = time.monotonic()
        async with read() as reader:
            assert (await reader.execute(select(AppSetting))).scalars().all() == []
        assert time.monotonic() - started < 2
        await writer.rollback()
    await engine.dispose()


async def test_a_write_transaction_really_holds_the_write_lock(database_url: str) -> None:
    """If it did not, the queueing above would only be luck."""
    import sqlite3

    engine = make_engine(Settings(database_url=database_url))
    holder = make_sessionmaker(engine)()
    await holder.execute(select(AppSetting))  # BEGIN IMMEDIATE, and it never finishes
    path = database_url.split(":///", 1)[1]
    other = sqlite3.connect(path, timeout=0.2, isolation_level=None)
    with pytest.raises(sqlite3.OperationalError, match="locked"):
        other.execute("BEGIN IMMEDIATE")
    other.close()
    await holder.rollback()
    await holder.close()
    await engine.dispose()
