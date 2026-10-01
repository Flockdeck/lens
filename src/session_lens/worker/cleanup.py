"""Retention reconciliation. Raw objects are expired by the bucket's lifecycle rule; this only
brings the database in line (and trims old batches). Sessions, metrics and enrichments are kept.
It never deletes objects and never lists the bucket.

Runs under a MySQL named lock so two overlapping runs (e.g. a slow CronJob and the next one)
cannot collide."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, exists, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from session_lens.db.models import Batch, BatchItem, BatchStatus, ItemStatus, RawRecording, utcnow

log = logging.getLogger(__name__)

BATCH_RETENTION_DAYS = 90
CHUNK = 1000
LOCK_NAME = "session_lens_cleanup"


@dataclass(frozen=True)
class CleanupResult:
    raws_expired: int = 0
    batches_deleted: int = 0
    skipped: bool = False  # another cleanup run holds the lock


async def expire_raws(sm: async_sessionmaker[AsyncSession], retention_days: int) -> int:
    """Set expired_at on raw rows older than `retention_days`, CHUNK rows per statement."""
    now = utcnow()
    cutoff = now - timedelta(days=retention_days)
    total = 0
    while True:
        async with sm() as db:
            ids = (
                (
                    await db.execute(
                        select(RawRecording.id)
                        .where(RawRecording.expired_at.is_(None), RawRecording.created_at < cutoff)
                        .order_by(RawRecording.id)
                        .limit(CHUNK)
                    )
                )
                .scalars()
                .all()
            )
            if not ids:
                return total
            await db.execute(
                update(RawRecording).where(RawRecording.id.in_(ids)).values(expired_at=now)
            )
            await db.commit()
            total += len(ids)


async def delete_old_batches(
    sm: async_sessionmaker[AsyncSession], retention_days: int = BATCH_RETENTION_DAYS
) -> int:
    """Delete finished batches (done or cancelled, with nothing queued or running) older than
    `retention_days`; their items go with them by foreign-key cascade."""
    cutoff = utcnow() - timedelta(days=retention_days)
    has_active_item = exists().where(
        BatchItem.batch_id == Batch.id,
        BatchItem.status.in_([ItemStatus.queued, ItemStatus.running]),
    )
    deleted = 0
    while True:
        async with sm() as db:
            ids = (
                (
                    await db.execute(
                        select(Batch.id)
                        .where(
                            Batch.status.in_([BatchStatus.done, BatchStatus.cancelled]),
                            Batch.created_at < cutoff,
                            ~has_active_item,
                        )
                        .order_by(Batch.id)
                        .limit(CHUNK)
                    )
                )
                .scalars()
                .all()
            )
            if not ids:
                return deleted
            await db.execute(delete(Batch).where(Batch.id.in_(ids)))
            await db.commit()
            deleted += len(ids)


async def run_cleanup(sm: async_sessionmaker[AsyncSession], retention_days: int) -> CleanupResult:
    # GET_LOCK is held by a connection, so keep one session open (never committed) for the run.
    async with sm() as lock_db:
        got = (await lock_db.execute(text("SELECT GET_LOCK(:n, 0)"), {"n": LOCK_NAME})).scalar()
        if got != 1:
            log.info("cleanup skipped: another run holds the lock")
            return CleanupResult(skipped=True)
        try:
            result = CleanupResult(
                raws_expired=await expire_raws(sm, retention_days),
                batches_deleted=await delete_old_batches(sm),
            )
        finally:
            await lock_db.execute(text("SELECT RELEASE_LOCK(:n)"), {"n": LOCK_NAME})
    log.info(
        "cleanup",
        extra={"raws_expired": result.raws_expired, "batches_deleted": result.batches_deleted},
    )
    return result
