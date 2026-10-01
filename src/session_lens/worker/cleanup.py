"""Raw recording retention. Sessions, metrics and enrichments are kept; only the blob goes."""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from session_lens.db.models import BatchItem, ItemStatus, RawRecording, utcnow

log = logging.getLogger(__name__)

CHUNK = 100  # blobs can be 16 MiB, so delete in small transactions


async def cleanup_raw(sm: async_sessionmaker[AsyncSession], retention_days: int) -> int:
    """Delete raw recordings older than `retention_days`, except those a queued or running item
    still needs. References from items and sessions are set to NULL by the foreign keys.
    Returns how many were deleted."""
    cutoff = utcnow() - timedelta(days=retention_days)
    in_use = select(BatchItem.raw_id).where(
        BatchItem.status.in_([ItemStatus.queued, ItemStatus.running]),
        BatchItem.raw_id.is_not(None),
    )
    deleted = 0
    while True:
        async with sm() as db:
            ids = (
                (
                    await db.execute(
                        select(RawRecording.id)
                        .where(RawRecording.created_at < cutoff, RawRecording.id.not_in(in_use))
                        .order_by(RawRecording.id)
                        .limit(CHUNK)
                    )
                )
                .scalars()
                .all()
            )
            if not ids:
                break
            await db.execute(delete(RawRecording).where(RawRecording.id.in_(ids)))
            await db.commit()
            deleted += len(ids)
    log.info("raw cleanup", extra={"deleted": deleted, "retention_days": retention_days})
    return deleted
