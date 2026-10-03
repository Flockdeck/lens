"""Bring the database up to date. Called on every start, so there is no separate step."""

from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from session_lens.config import Settings

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def _config(settings: Settings) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.attributes["url"] = settings.database_url
    return cfg


def head_revision() -> str | None:
    return ScriptDirectory.from_config(_config(Settings())).get_current_head()


def upgrade(settings: Settings) -> None:
    """Blocking. From async code use `await upgrade_async(settings)`."""
    command.upgrade(_config(settings), "head")


async def upgrade_async(settings: Settings) -> None:
    # alembic's env runs its own event loop, so it needs a thread of its own.
    await asyncio.to_thread(upgrade, settings)
