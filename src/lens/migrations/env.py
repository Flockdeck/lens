"""Alembic environment. The URL comes from the caller (`lens.db.migrate`) or, for
development commands, from DATABASE_URL / the default data directory (lens.config)."""

import asyncio

from alembic import context
from sqlalchemy.engine import Connection

from lens.config import Settings, get_settings
from lens.db.models import Base
from lens.db.session import make_engine

target_metadata = Base.metadata


def _settings() -> Settings:
    url = context.config.attributes.get("url")
    return get_settings().model_copy(update={"database_url": str(url)}) if url else get_settings()


def _configure(connection: Connection | None, url: str | None = None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=True,  # SQLite cannot ALTER most things in place
        literal_binds=connection is None,
    )


def run_migrations_offline() -> None:
    _configure(None, _settings().database_url)
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = make_engine(_settings())
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
