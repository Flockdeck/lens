"""Shared fixtures: one throwaway MySQL database per test run, built by the real Alembic
migrations (so the migrations are exercised by every suite that touches the database).

The server comes from DATABASE_URL (docker compose: `docker compose up -d --wait mysql`).
Creating a database needs more rights than the app user has, so the admin connection is
MYSQL_ADMIN_URL, or root/root on the same host when that is not set.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Iterator

import pytest
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from session_lens.config import Settings

ALEMBIC_INI = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")


def _base_url() -> str:
    return os.environ.get("DATABASE_URL", Settings().database_url)


def _admin_url() -> str:
    explicit = os.environ.get("MYSQL_ADMIN_URL")
    if explicit:
        return explicit
    return (
        make_url(_base_url())
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
    app_user = make_url(_base_url()).username
    if app_user and app_user != "root":
        asyncio.run(_admin(f"GRANT ALL ON `{name}`.* TO '{app_user}'@'%'"))
    url = make_url(_base_url()).set(database=name).render_as_string(hide_password=False)
    cfg = Config(ALEMBIC_INI)
    cfg.attributes["url"] = url
    try:
        command.upgrade(cfg, "head")
        yield url
    finally:
        asyncio.run(_admin(f"DROP DATABASE IF EXISTS `{name}`"))
