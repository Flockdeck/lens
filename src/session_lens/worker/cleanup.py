"""Retention reconciliation. Raw objects are expired by the bucket's lifecycle rule; this only
brings the database in line (and trims old batches). Sessions, metrics and enrichments are kept.
It never deletes objects and never lists the bucket."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from session_lens.db.models import Batch, BatchItem, BatchStatus, ItemStatus, RawRecording, utcnow

log = logging.getLogger(__name__)

BATCH_RETENTION_DAYS = 90
CHUNK = 500


@dataclass(frozen=True)
class CleanupResult:
    raws_expired: int
    batches_deleted: int


async def expire_raws(sm: async_sessionmaker[AsyncSession], retention_days: int) -> int:
    """Set expired_at on raw rows older than `retention_days`."""
    now = utcnow()
    async with sm() as db:
        result = await db.execute(
            update(RawRecording)
            .where(
                RawRecording.expired_at.is_(None),
                RawRecording.created_at < now - timedelta(days=retention_days),
            )
            .values(expired_at=now)
        )
        await db.commit()
        return int(result.rowcount)  # type: ignore[attr-defined]


async def delete_old_batches(
    sm: async_sessionmaker[AsyncSession], retention_days: int = BATCH_RETENTION_DAYS
) -> int:
    """Delete finished batches (done or cancelled, with nothing queued or running) older than
    `retention_days`; their items go with them by foreign-key cascade."""
    cutoff = utcnow() - timedelta(days=retention_days)
    active = select(BatchItem.batch_id).where(
        BatchItem.status.in_([ItemStatus.queued, ItemStatus.running])
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
                            Batch.id.not_in(active),
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
    result = CleanupResult(
        raws_expired=await expire_raws(sm, retention_days),
        batches_deleted=await delete_old_batches(sm),
    )
    log.info(
        "cleanup",
        extra={"raws_expired": result.raws_expired, "batches_deleted": result.batches_deleted},
    )
    return result
