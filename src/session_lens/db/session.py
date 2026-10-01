"""Async engine and session factory, built from settings."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from session_lens.config import Settings, get_settings


def make_engine(settings: Settings | None = None) -> AsyncEngine:
    settings = settings or get_settings()
    return create_async_engine(settings.database_url, pool_pre_ping=True, pool_recycle=1800)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@lru_cache
def get_engine() -> AsyncEngine:
    return make_engine()


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return make_sessionmaker(get_engine())


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """One session, committed on success and rolled back on error."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: a session per request. The caller commits."""
    async with get_sessionmaker()() as session:
        yield session


async def dispose_engine() -> None:
    if get_engine.cache_info().currsize:
        await get_engine().dispose()
        get_sessionmaker.cache_clear()
        get_engine.cache_clear()
