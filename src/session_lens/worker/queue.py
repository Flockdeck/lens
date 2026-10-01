"""Queue helpers shared with the API: creating, retrying and cancelling batches, storing raw
recordings, and rolling item statuses up into the batch status."""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from session_lens.config import get_settings
from session_lens.db.models import (
    Batch,
    BatchItem,
    BatchStatus,
    ItemStatus,
    RawRecording,
    Session,
    utcnow,
)
from session_lens.storage.base import RecordingExpired, RecordingStore

log = logging.getLogger(__name__)


class BatchNotFound(LookupError):
    pass


def new_object_key(prefix: str) -> str:
    now = utcnow()
    return f"{prefix}{now:%Y/%m}/{uuid.uuid4()}.jsonl"


async def store_raw(session: AsyncSession, store: RecordingStore, data: bytes) -> RawRecording:
    """Hash `data`, put the file, then add the row (flushed, not committed). Putting first
    means a row never points at a missing file; a failure after the put leaves an orphan
    file, which is unreferenced and harmless."""
    key = new_object_key(get_settings().s3_prefix)
    await store.put(key, data)
    raw = RawRecording(
        content_hash=hashlib.sha256(data).hexdigest(), size_bytes=len(data), object_key=key
    )
    session.add(raw)
    await session.flush()
    return raw


async def read_raw(session: AsyncSession, store: RecordingStore, raw_id: int) -> bytes:
    """The recording's bytes. Raises RecordingExpired if the row is expired, missing, or its
    object is gone; in the last case `expired_at` is set (flushed; the caller should commit
    before re-raising if it wants that kept)."""
    raw = await session.get(RawRecording, raw_id)
    if raw is None or raw.expired_at is not None:
        raise RecordingExpired(raw_id)
    try:
        return await store.get(raw.object_key)
    except RecordingExpired:
        raw.expired_at = utcnow()
        await session.flush()
        raise


async def delete_raws_for_session(
    session: AsyncSession, store: RecordingStore, session_id: int
) -> int:
    """Delete every raw recording linked to a session (its own raw_id, and the raw_id of every
    batch item that produced it): the object (best effort), then the row. Call it before
    deleting the Session itself, since it finds the raws through that row. The foreign keys
    to raw_recordings are SET NULL, so the order is safe. Flushed, not committed. Returns the
    number of raw rows deleted."""
    raw_ids = set(
        (
            await session.execute(
                select(Session.raw_id).where(Session.id == session_id, Session.raw_id.is_not(None))
            )
        ).scalars()
    )
    raw_ids |= set(
        (
            await session.execute(
                select(BatchItem.raw_id).where(
                    BatchItem.session_id == session_id, BatchItem.raw_id.is_not(None)
                )
            )
        ).scalars()
    )
    if not raw_ids:
        return 0
    raws = (
        (await session.execute(select(RawRecording).where(RawRecording.id.in_(raw_ids))))
        .scalars()
        .all()
    )
    for raw in raws:
        try:
            await store.delete(raw.object_key)
        except Exception:
            log.warning("object delete failed", extra={"raw_id": raw.id, "key": raw.object_key})
        await session.delete(raw)
    await session.flush()
    return len(raws)


async def create_batch(
    session: AsyncSession, store: RecordingStore, files: Sequence[tuple[str, bytes | RawRecording]]
) -> Batch:
    """Create a batch with one queued item per `(filename, content)`. Content may be the bytes
    (stored here) or a RawRecording the caller already stored. Flushed, not committed."""
    batch = Batch(status=BatchStatus.queued)
    session.add(batch)
    await session.flush()
    for filename, content in files:
        raw = (
            content
            if isinstance(content, RawRecording)
            else await store_raw(session, store, content)
        )
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


async def _require_batch(session: AsyncSession, batch_id: int) -> None:
    if (await session.execute(select(Batch.id).where(Batch.id == batch_id))).first() is None:
        raise BatchNotFound(batch_id)


# Lock order everywhere: item rows first, then the batch row (claim_items and the item
# settle path do the same). Taking them in the other order can deadlock against a worker.
async def retry_failed(session: AsyncSession, batch_id: int) -> int:
    """Re-queue the failed items of a batch. Returns how many were re-queued."""
    await _require_batch(session, batch_id)
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
            updated_at=utcnow(),
        )
    )
    count: int = result.rowcount  # type: ignore[attr-defined]
    if count:
        batch = await _get_batch_locked(session, batch_id)
        batch.status = BatchStatus.running  # recomputed just below; clears a sticky cancelled
        await session.flush()
        await refresh_batch_status(session, batch_id)
    return count


async def cancel_batch(session: AsyncSession, batch_id: int) -> int:
    """Cancel the queued items of a batch; running items are left to finish. Marks the batch
    cancelled. Returns how many items were cancelled."""
    await _require_batch(session, batch_id)
    result = await session.execute(
        update(BatchItem)
        .where(BatchItem.batch_id == batch_id, BatchItem.status == ItemStatus.queued)
        .values(status=ItemStatus.cancelled, not_before=None, updated_at=utcnow())
    )
    batch = await _get_batch_locked(session, batch_id)
    batch.status = BatchStatus.cancelled
    await session.flush()
    count: int = result.rowcount  # type: ignore[attr-defined]
    return count
