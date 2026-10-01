import asyncio
import os

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from session_lens.db.models import Base


def test_migrations_match_models(database_url):
    async def diff():
        engine = create_async_engine(database_url)
        async with engine.connect() as conn:
            result = await conn.run_sync(
                lambda c: compare_metadata(
                    MigrationContext.configure(c, {"compare_type": True}), Base.metadata
                )
            )
            tables = (await conn.execute(text("SHOW TABLES"))).scalars().all()
        await engine.dispose()
        return result, set(tables)

    changes, tables = asyncio.run(diff())
    assert changes == []
    expected = {"batches", "batch_items", "sessions", "enrichments", "raw_recordings"}
    assert expected <= tables


def test_downgrade_and_upgrade_roundtrip(database_url):
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini"))
    cfg.attributes["url"] = database_url
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
