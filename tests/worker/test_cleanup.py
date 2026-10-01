from datetime import timedelta

from sqlalchemy import select, update

from session_lens.db.models import (
    Batch,
    BatchItem,
    BatchStatus,
    Enrichment,
    ItemStatus,
    RawRecording,
    Session,
    utcnow,
)
from session_lens.worker.cleanup import run_cleanup
from session_lens.worker.loop import claim_items
from session_lens.worker.processor import ItemProcessor
from tests.worker.helpers import FakeEnricher, get_item, make_batch, recording


async def age_batches(sm, days):
    async with sm() as db:
        await db.execute(update(Batch).values(created_at=utcnow() - timedelta(days=days)))
        await db.commit()


async def _age_raw(sm, raw_id, days):
    async with sm() as db:
        await db.execute(
            update(RawRecording)
            .where(RawRecording.id == raw_id)
            .values(created_at=utcnow() - timedelta(days=days))
        )
        await db.commit()


async def _finish_items(sm):
    async with sm() as db:
        await db.execute(update(BatchItem).values(status=ItemStatus.done))
        await db.commit()


async def test_old_raws_have_their_file_deleted_and_row_expired(sm, store):
    files = [("a.jsonl", recording("a")), ("b.jsonl", recording("b"))]
    _, (a, b) = await make_batch(sm, store, files)
    await _finish_items(sm)
    async with sm() as db:
        raw_a = (await db.get(BatchItem, a)).raw_id
        raw_b = (await db.get(BatchItem, b)).raw_id
        key_a = (await db.get(RawRecording, raw_a)).object_key
        key_b = (await db.get(RawRecording, raw_b)).object_key
    await _age_raw(sm, raw_a, 31)  # only a is past retention
    result = await run_cleanup(sm, store, 30)
    assert (result.raws_expired, result.batches_deleted) == (1, 0)
    assert key_a not in store.objects and key_b in store.objects
    async with sm() as db:
        assert (await db.get(RawRecording, raw_a)).expired_at is not None
        assert (await db.get(RawRecording, raw_b)).expired_at is None
    assert (await run_cleanup(sm, store, 30)).raws_expired == 0  # idempotent


async def test_missing_file_is_fine_and_row_is_still_expired(sm, store):
    _, (a,) = await make_batch(sm, store, [("a.jsonl", recording())])
    await _finish_items(sm)
    store.objects.clear()
    async with sm() as db:
        raw = (await db.get(BatchItem, a)).raw_id
    await _age_raw(sm, raw, 40)
    assert (await run_cleanup(sm, store, 30)).raws_expired == 1


async def test_file_delete_failure_does_not_stop_cleanup(sm, store):
    _, (a,) = await make_batch(sm, store, [("a.jsonl", recording())])
    await _finish_items(sm)

    async def broken(key):
        raise OSError("disk error")

    store.delete = broken
    async with sm() as db:
        raw = (await db.get(BatchItem, a)).raw_id
    await _age_raw(sm, raw, 40)
    assert (await run_cleanup(sm, store, 30)).raws_expired == 1


async def test_retention_zero_keeps_files_forever(sm, store):
    _, (a,) = await make_batch(sm, store, [("a.jsonl", recording())])
    await _finish_items(sm)
    async with sm() as db:
        raw = (await db.get(BatchItem, a)).raw_id
    await _age_raw(sm, raw, 4000)
    assert (await run_cleanup(sm, store, 0)).raws_expired == 0
    assert len(store.objects) == 1


async def test_raw_needed_by_a_queued_or_running_item_is_skipped(sm, store):
    _, (a, b) = await make_batch(
        sm, store, [("a.jsonl", recording("a")), ("b.jsonl", recording("b"))]
    )
    async with sm() as db:
        await db.execute(
            update(BatchItem).where(BatchItem.id == b).values(status=ItemStatus.running)
        )
        await db.execute(
            update(BatchItem).where(BatchItem.id == a).values(status=ItemStatus.failed)
        )
        raws = [(await db.get(BatchItem, i)).raw_id for i in (a, b)]
        await db.commit()
    for raw in raws:
        await _age_raw(sm, raw, 60)
    assert (await run_cleanup(sm, store, 30)).raws_expired == 1  # a's only; b is still running
    async with sm() as db:
        assert (await db.get(RawRecording, raws[1])).expired_at is None


async def test_old_finished_batches_are_deleted_but_sessions_and_enrichments_stay(sm, store):
    batch_id, (a,) = await make_batch(sm, store, [("a.jsonl", recording())])
    (claim,) = await claim_items(sm, 1)
    await ItemProcessor(sm, store, FakeEnricher(), 3, 30).process(claim)
    await age_batches(sm, 91)
    assert (await run_cleanup(sm, store, 30)).batches_deleted == 1
    async with sm() as db:
        assert await db.get(Batch, batch_id) is None
        assert await db.get(BatchItem, a) is None
        assert (await db.execute(select(Session))).scalar_one()
        assert (await db.execute(select(Enrichment))).scalar_one()


async def test_recent_and_unfinished_batches_are_kept(sm, store):
    recent, _ = await make_batch(sm, store, [("a.jsonl", recording("a"))])
    old, (item,) = await make_batch(sm, store, [("b.jsonl", recording("b"))])
    await age_batches(sm, 100)
    async with sm() as db:
        await db.execute(update(Batch).where(Batch.id == recent).values(created_at=utcnow()))
        # old and marked done, but an item is still running: must not be deleted
        await db.execute(update(Batch).where(Batch.id == old).values(status=BatchStatus.done))
        await db.execute(
            update(BatchItem).where(BatchItem.id == item).values(status=ItemStatus.running)
        )
        await db.commit()
    assert (await run_cleanup(sm, store, 30)).batches_deleted == 0
    assert (await get_item(sm, item)).status == ItemStatus.running
