"""Retention, enforced by the app. Raw recordings older than `raw_retention_days` have their
stored file deleted and their row marked expired (`expired_at`); finished batches older than 90
days are deleted. Sessions, metrics and enrichments are kept.

One run at a time: a manual run during the periodic one is skipped."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lens.db.models import Batch, BatchItem, BatchStatus, ItemStatus, RawRecording, utcnow
from lens.storage.base import RecordingStore

log = logging.getLogger(__name__)

BATCH_RETENTION_DAYS = 90
CHUNK = 1000


@dataclass(frozen=True)
class CleanupResult:
    raws_expired: int = 0
    batches_deleted: int = 0
    skipped: bool = False  # another cleanup run holds the lock


async def expire_raws(
    sm: async_sessionmaker[AsyncSession], store: RecordingStore, retention_days: int
) -> int:
    """For raw rows older than `retention_days` (0 = keep forever): delete the stored file
    (best effort; a missing file is fine), then set expired_at. CHUNK rows at a time. A raw
    that a queued or running item still needs is left alone until that item finishes."""
    if retention_days <= 0:
        return 0
    cutoff = utcnow() - timedelta(days=retention_days)
    needed = exists().where(
        BatchItem.raw_id == RawRecording.id,
        BatchItem.status.in_([ItemStatus.queued, ItemStatus.running]),
    )
    total = 0
    last_id = 0
    while True:
        async with sm() as db:
            rows = (
                await db.execute(
                    select(RawRecording.id, RawRecording.object_key)
                    .where(
                        RawRecording.id > last_id,
                        RawRecording.expired_at.is_(None),
                        RawRecording.created_at < cutoff,
                        ~needed,
                    )
                    .order_by(RawRecording.id)
                    .limit(CHUNK)
                )
            ).all()
            if not rows:
                return total
            last_id = rows[-1].id
            for row in rows:
                try:
                    await store.delete(row.object_key)
                except Exception:
                    log.warning("file delete failed", extra={"raw_id": row.id})
            await db.execute(
                update(RawRecording)
                .where(RawRecording.id.in_([r.id for r in rows]))
                .values(expired_at=utcnow())
            )
            await db.commit()
            total += len(rows)


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


_running = asyncio.Lock()


async def run_cleanup(
    sm: async_sessionmaker[AsyncSession], store: RecordingStore, retention_days: int
) -> CleanupResult:
    if _running.locked():  # the timer and a manual run, or two overlapping timers
        log.info("cleanup skipped: another run is in progress")
        return CleanupResult(skipped=True)
    async with _running:
        result = CleanupResult(
            raws_expired=await expire_raws(sm, store, retention_days),
            batches_deleted=await delete_old_batches(sm),
        )
    log.info(
        "cleanup",
        extra={"raws_expired": result.raws_expired, "batches_deleted": result.batches_deleted},
    )
    return result
