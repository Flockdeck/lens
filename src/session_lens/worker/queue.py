"""Queue helpers shared with the API: creating, retrying and cancelling batches, storing raw
recordings, and rolling item statuses up into the batch status."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

import zstandard
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from session_lens.db.models import Batch, BatchItem, BatchStatus, ItemStatus, RawRecording, _now


class BatchNotFound(LookupError):
    pass


def compress(data: bytes) -> bytes:
    return zstandard.ZstdCompressor(level=3).compress(data)


def decompress(blob: bytes) -> bytes:
    return zstandard.ZstdDecompressor().decompress(blob)


async def store_raw(session: AsyncSession, data: bytes) -> RawRecording:
    """Hash and zstd-compress `data` into a new raw_recordings row (flushed, not committed)."""
    raw = RawRecording(
        content_hash=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        data=compress(data),
    )
    session.add(raw)
    await session.flush()
    return raw


async def create_batch(
    session: AsyncSession, files: Sequence[tuple[str, bytes | RawRecording]]
) -> Batch:
    """Create a batch with one queued item per `(filename, content)`. Content may be the bytes
    (stored here) or a RawRecording the caller already stored. Flushed, not committed."""
    batch = Batch(status=BatchStatus.queued)
    session.add(batch)
    await session.flush()
    for filename, content in files:
        raw = content if isinstance(content, RawRecording) else await store_raw(session, content)
        session.add(BatchItem(batch_id=batch.id, filename=filename[:255], raw_id=raw.id))
    await session.flush()
    return batch


async def _get_batch_locked(session: AsyncSession, batch_id: int) -> Batch:
    batch = (
        await session.execute(select(Batch).where(Batch.id == batch_id).with_for_update())
    ).scalar_one_or_none()
    if batch is None:
        raise BatchNotFound(batch_id)
    return batch


async def item_counts(session: AsyncSession, batch_id: int) -> dict[str, int]:
    rows = await session.execute(
        select(BatchItem.status, func.count())
        .where(BatchItem.batch_id == batch_id)
        .group_by(BatchItem.status)
    )
    counts = {s.value: 0 for s in ItemStatus}
    for status, n in rows:
        counts[ItemStatus(status).value] = n
    return counts


async def refresh_batch_status(session: AsyncSession, batch_id: int) -> BatchStatus:
    """Roll item statuses up. `cancelled` is sticky; otherwise: nothing queued or running means
    done, only queued items means queued, anything else running."""
    batch = await _get_batch_locked(session, batch_id)
    if batch.status == BatchStatus.cancelled:
        return batch.status
    counts = await item_counts(session, batch_id)
    queued, running = counts["queued"], counts["running"]
    total = sum(counts.values())
    if queued == 0 and running == 0:
        status = BatchStatus.done
    elif running == 0 and queued == total:
        status = BatchStatus.queued
    else:
        status = BatchStatus.running
    batch.status = status
    await session.flush()
    return status


async def retry_failed(session: AsyncSession, batch_id: int) -> int:
    """Re-queue the failed items of a batch. Returns how many were re-queued."""
    batch = await _get_batch_locked(session, batch_id)
    result = await session.execute(
        update(BatchItem)
        .where(BatchItem.batch_id == batch_id, BatchItem.status == ItemStatus.failed)
        .values(
            status=ItemStatus.queued,
            attempts=0,
            not_before=None,
            locked_at=None,
            error=None,
            error_retryable=None,
            updated_at=_now(),
        )
    )
    count: int = result.rowcount  # type: ignore[attr-defined]
    if count:
        batch.status = BatchStatus.running  # recomputed just below
        await session.flush()
        await refresh_batch_status(session, batch_id)
    return count


async def cancel_batch(session: AsyncSession, batch_id: int) -> int:
    """Cancel the queued items of a batch; running items are left to finish. Marks the batch
    cancelled. Returns how many items were cancelled."""
    batch = await _get_batch_locked(session, batch_id)
    result = await session.execute(
        update(BatchItem)
        .where(BatchItem.batch_id == batch_id, BatchItem.status == ItemStatus.queued)
        .values(status=ItemStatus.cancelled, not_before=None, updated_at=_now())
    )
    batch.status = BatchStatus.cancelled
    await session.flush()
    count: int = result.rowcount  # type: ignore[attr-defined]
    return count
