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


async def test_old_raw_rows_are_marked_expired_and_objects_untouched(sm, store):
    files = [("a.jsonl", recording("a")), ("b.jsonl", recording("b"))]
    _, (a, _b) = await make_batch(sm, store, files)
    async with sm() as db:  # only a's raw is old
        raw_a = (await db.get(BatchItem, a)).raw_id
        await db.execute(
            update(RawRecording)
            .where(RawRecording.id == raw_a)
            .values(created_at=utcnow() - timedelta(days=31))
        )
        await db.commit()
    objects_before = dict(store.objects)
    result = await run_cleanup(sm, 30)
    assert (result.raws_expired, result.batches_deleted) == (1, 0)
    async with sm() as db:
        rows = {r.id: r for r in (await db.execute(select(RawRecording))).scalars()}
    assert rows[raw_a].expired_at is not None
    assert sum(r.expired_at is None for r in rows.values()) == 1
    assert store.objects == objects_before  # cleanup never deletes objects
    assert (await run_cleanup(sm, 30)).raws_expired == 0  # idempotent


async def test_old_finished_batches_are_deleted_but_sessions_and_enrichments_stay(sm, store):
    batch_id, (a,) = await make_batch(sm, store, [("a.jsonl", recording())])
    (claim,) = await claim_items(sm, 1)
    await ItemProcessor(sm, store, FakeEnricher(), 3, 30).process(claim)
    await age_batches(sm, 91)
    assert (await run_cleanup(sm, 30)).batches_deleted == 1
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
    assert (await run_cleanup(sm, 30)).batches_deleted == 0
    assert (await get_item(sm, item)).status == ItemStatus.running
