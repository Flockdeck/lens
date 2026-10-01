import hashlib
import re

import pytest
from sqlalchemy import select, update

from session_lens.db.models import BatchItem, BatchStatus, ItemStatus, RawRecording, Session, utcnow
from session_lens.storage.base import RecordingExpired
from session_lens.worker.queue import (
    BatchNotFound,
    cancel_batch,
    create_batch,
    delete_raws_for_session,
    item_counts,
    read_raw,
    refresh_batch_status,
    retry_failed,
    store_raw,
)
from tests.worker.helpers import get_batch, make_batch, recording


async def test_store_raw_puts_object_then_row(sm, store):
    data = recording(extra="x" * 5000)
    async with sm() as db:
        raw = await store_raw(db, store, data)
        await db.commit()
        row = await db.get(RawRecording, raw.id)
    assert row.content_hash == hashlib.sha256(data).hexdigest()
    assert row.size_bytes == len(data)
    assert row.expired_at is None
    assert re.fullmatch(r"recordings/\d{4}/\d{2}/[0-9a-f-]{36}\.jsonl", row.object_key)
    assert store.objects[row.object_key] == data


async def test_store_raw_failed_put_leaves_no_row(sm, store):
    store.fail_put = True
    async with sm() as db:
        with pytest.raises(OSError):
            await store_raw(db, store, recording())
        await db.rollback()
    async with sm() as db:
        assert (await db.execute(select(RawRecording))).first() is None


async def test_each_upload_gets_its_own_object(sm, store):
    async with sm() as db:
        a = await store_raw(db, store, recording())
        b = await store_raw(db, store, recording())
        await db.commit()
    assert a.object_key != b.object_key and len(store.objects) == 2


async def test_read_raw_roundtrip(sm, store):
    async with sm() as db:
        raw = await store_raw(db, store, recording("rt"))
        await db.commit()
        assert await read_raw(db, store, raw.id) == recording("rt")


async def test_read_raw_expired_row(sm, store):
    async with sm() as db:
        raw = await store_raw(db, store, recording())
        raw.expired_at = utcnow()
        await db.commit()
        with pytest.raises(RecordingExpired):
            await read_raw(db, store, raw.id)
        with pytest.raises(RecordingExpired):
            await read_raw(db, store, 99999)


async def test_read_raw_gone_object_sets_expired_at(sm, store):
    async with sm() as db:
        raw = await store_raw(db, store, recording())
        await db.commit()
        store.objects.clear()  # the lifecycle rule removed it
        with pytest.raises(RecordingExpired):
            await read_raw(db, store, raw.id)
        await db.commit()
        assert (await db.get(RawRecording, raw.id)).expired_at is not None


async def _session_with_raws(db, store):
    """A session whose raw is referenced by Session.raw_id and by two items, plus an
    unrelated raw. Returns (session, [session's raws], other raw)."""
    older = await store_raw(db, store, recording("s1"))
    newer = await store_raw(db, store, recording("s1", extra="longer"))
    other = await store_raw(db, store, recording("other"))
    session = Session(
        recording_session="s1",
        content_hash=newer.content_hash,
        completeness="clean",
        metrics={},
        raw_id=newer.id,
    )
    db.add(session)
    batch = await create_batch(db, store, [("a.jsonl", older), ("b.jsonl", newer)])
    await db.flush()
    await db.execute(
        update(BatchItem).where(BatchItem.batch_id == batch.id).values(session_id=session.id)
    )
    await db.commit()
    return session, [older, newer], other


async def test_delete_raws_for_session_before_deleting_the_session(sm, store):
    async with sm() as db:
        session, raws, other = await _session_with_raws(db, store)
        assert len(store.objects) == 3
        assert await delete_raws_for_session(db, store, session.id) == 2
        await db.delete(session)  # the API deletes the session next, in the same transaction
        await db.commit()
        remaining = (await db.execute(select(RawRecording))).scalars().all()
        assert [r.id for r in remaining] == [other.id]
        items = (await db.execute(select(BatchItem))).scalars().all()
        assert all(i.raw_id is None and i.session_id is None for i in items)  # SET NULL
    assert list(store.objects) == [other.object_key]


async def test_delete_raws_for_session_survives_object_delete_failure(sm, store):
    async with sm() as db:
        session, raws, _ = await _session_with_raws(db, store)

        async def boom(key):
            raise OSError("down")

        store.delete = boom
        assert await delete_raws_for_session(db, store, session.id) == 2  # rows still go
        await db.commit()


async def test_delete_raws_for_session_without_raws(sm, store):
    async with sm() as db:
        assert await delete_raws_for_session(db, store, 12345) == 0


async def test_create_batch_queues_one_item_per_file(sm, store):
    batch_id, item_ids = await make_batch(
        sm, store, [("a.jsonl", recording("a")), ("b.jsonl", recording("b"))]
    )
    assert len(item_ids) == 2
    async with sm() as db:
        items = (await db.execute(select(BatchItem).order_by(BatchItem.id))).scalars().all()
        assert [i.filename for i in items] == ["a.jsonl", "b.jsonl"]
        assert all(i.status == ItemStatus.queued and i.raw_id for i in items)
    assert (await get_batch(sm, batch_id)).status == BatchStatus.queued


async def test_create_batch_accepts_prestored_raw(sm, store):
    async with sm() as db:
        raw = await store_raw(db, store, recording())
        batch = await create_batch(db, store, [("a.jsonl", raw)])
        await db.commit()
        item = (
            await db.execute(select(BatchItem).where(BatchItem.batch_id == batch.id))
        ).scalar_one()
        assert item.raw_id == raw.id


async def _set(sm, item_id, status):
    async with sm() as db:
        await db.execute(update(BatchItem).where(BatchItem.id == item_id).values(status=status))
        await db.commit()


async def test_rollup(sm, store):
    batch_id, (a, b, c) = await make_batch(sm, store, [(f"{n}.jsonl", recording(n)) for n in "abc"])

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


async def test_retry_failed_requeues_only_failed(sm, store):
    batch_id, (a, b) = await make_batch(
        sm, store, [("a.jsonl", recording("a")), ("b.jsonl", recording("b"))]
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


async def test_cancel_batch_cancels_queued_leaves_running(sm, store):
    batch_id, (a, b, c) = await make_batch(sm, store, [(f"{n}.jsonl", recording(n)) for n in "abc"])
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


async def test_unknown_batch(sm, store):
    async with sm() as db:
        for fn in (retry_failed, cancel_batch):
            try:
                await fn(db, 999)
            except BatchNotFound:
                pass
            else:
                raise AssertionError
