import asyncio

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text

from lens.config import Settings
from lens.db.migrate import head_revision, upgrade
from lens.db.models import Base
from tests.dbutil import test_engine


def test_migrations_match_models(database_url):
    async def diff():
        engine = test_engine(database_url)
        async with engine.connect() as conn:
            result = await conn.run_sync(
                lambda c: compare_metadata(
                    MigrationContext.configure(c, {"compare_type": True}), Base.metadata
                )
            )
            tables = (
                (await conn.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'")))
                .scalars()
                .all()
            )
            version = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar()
        await engine.dispose()
        return result, set(tables), version

    changes, tables, version = asyncio.run(diff())
    assert changes == []
    expected = {
        "batches",
        "batch_items",
        "sessions",
        "enrichments",
        "raw_recordings",
        "app_settings",
    }
    assert expected <= tables
    assert version == head_revision()


def test_a_second_upgrade_changes_nothing(database_url):
    """`serve` migrates on every start."""
    upgrade(Settings(database_url=database_url))
    upgrade(Settings(database_url=database_url))
