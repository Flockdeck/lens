"""Helpers for tests that use the database."""

from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine

from lens.config import Settings
from lens.db.models import Base
from lens.db.session import make_engine


def test_engine(database_url: str) -> AsyncEngine:
    """The app's own engine (WAL, foreign keys, BEGIN IMMEDIATE) on the test database."""
    return make_engine(Settings(database_url=database_url))


test_engine.__test__ = False  # type: ignore[attr-defined]  # not a test, whatever its name


async def clear_tables(engine: AsyncEngine) -> None:
    """Empty every table, children first."""
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(delete(table))
