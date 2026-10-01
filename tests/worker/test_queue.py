import hashlib

import zstandard
from sqlalchemy import select, update

from session_lens.db.models import BatchItem, BatchStatus, ItemStatus, RawRecording
from session_lens.worker.queue import (
    BatchNotFound,
    cancel_batch,
    create_batch,
    item_counts,
    refresh_batch_status,
    retry_failed,
    store_raw,
)
from tests.worker.helpers import get_batch, make_batch, recording


async def test_store_raw_hashes_and_compresses(sm):
    data = recording(extra="x" * 5000)
    async with sm() as db:
        raw = await store_raw(db, data)
        await db.commit()
        row = await db.get(RawRecording, raw.id)
    assert row.content_hash == hashlib.sha256(data).hexdigest()
    assert row.size_bytes == len(data)
    assert len(row.data) < len(data)
    assert zstandard.ZstdDecompressor().decompress(row.data) == data


async def test_create_batch_queues_one_item_per_file(sm):
    batch_id, item_ids = await make_batch(
        sm, [("a.jsonl", recording("a")), ("b.jsonl", recording("b"))]
    )
    assert len(item_ids) == 2
    async with sm() as db:
        items = (await db.execute(select(BatchItem).order_by(BatchItem.id))).scalars().all()
        assert [i.filename for i in items] == ["a.jsonl", "b.jsonl"]
        assert all(i.status == ItemStatus.queued and i.raw_id for i in items)
    assert (await get_batch(sm, batch_id)).status == BatchStatus.queued


async def test_create_batch_accepts_prestored_raw(sm):
    async with sm() as db:
        raw = await store_raw(db, recording())
        batch = await create_batch(db, [("a.jsonl", raw)])
        await db.commit()
        item = (
            await db.execute(select(BatchItem).where(BatchItem.batch_id == batch.id))
        ).scalar_one()
        assert item.raw_id == raw.id


async def _set(sm, item_id, status):
    async with sm() as db:
        await db.execute(update(BatchItem).where(BatchItem.id == item_id).values(status=status))
        await db.commit()


async def test_rollup(sm):
    batch_id, (a, b, c) = await make_batch(sm, [(f"{n}.jsonl", recording(n)) for n in "abc"])

    async def status():
        async with sm() as db:
            s = await refresh_batch_status(db, batch_id)
            await db.commit()
            return s

    assert await status() == BatchStatus.queued
    await _set(sm, a, ItemStatus.running)
    assert await status() == BatchStatus.running
    await _set(sm, a, ItemStatus.done)  # one done, two queued: still in progress
    assert await status() == BatchStatus.running
    await _set(sm, b, ItemStatus.failed)
    await _set(sm, c, ItemStatus.done)
    assert await status() == BatchStatus.done  # failures do not keep a batch open


async def test_retry_failed_requeues_only_failed(sm):
    batch_id, (a, b) = await make_batch(
        sm, [("a.jsonl", recording("a")), ("b.jsonl", recording("b"))]
    )
    await _set(sm, a, ItemStatus.done)
    async with sm() as db:
        await db.execute(
            update(BatchItem)
            .where(BatchItem.id == b)
            .values(status=ItemStatus.failed, attempts=4, error="boom", error_retryable=False)
        )
        await db.commit()
    async with sm() as db:
        await refresh_batch_status(db, batch_id)
        await db.commit()
    assert (await get_batch(sm, batch_id)).status == BatchStatus.done
    async with sm() as db:
        assert await retry_failed(db, batch_id) == 1
        await db.commit()
        item = await db.get(BatchItem, b)
        assert (item.status, item.attempts, item.error) == (ItemStatus.queued, 0, None)
        assert (await db.get(BatchItem, a)).status == ItemStatus.done
    assert (await get_batch(sm, batch_id)).status == BatchStatus.running


async def test_cancel_batch_cancels_queued_leaves_running(sm):
    batch_id, (a, b, c) = await make_batch(sm, [(f"{n}.jsonl", recording(n)) for n in "abc"])
    await _set(sm, a, ItemStatus.running)
    async with sm() as db:
        assert await cancel_batch(db, batch_id) == 2
        await db.commit()
        counts = await item_counts(db, batch_id)
    assert counts["cancelled"] == 2 and counts["running"] == 1
    assert (await get_batch(sm, batch_id)).status == BatchStatus.cancelled
    await _set(sm, a, ItemStatus.done)
    async with sm() as db:  # sticky once the running item finishes
        assert await refresh_batch_status(db, batch_id) == BatchStatus.cancelled


async def test_unknown_batch(sm):
    async with sm() as db:
        for fn in (retry_failed, cancel_batch):
            try:
                await fn(db, 999)
            except BatchNotFound:
                pass
            else:
                raise AssertionError
