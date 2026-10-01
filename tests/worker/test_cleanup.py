from datetime import timedelta

from sqlalchemy import select, update

from session_lens.db.models import BatchItem, Enrichment, ItemStatus, RawRecording, Session, utcnow
from session_lens.worker.cleanup import cleanup_raw
from session_lens.worker.loop import claim_items
from session_lens.worker.processor import ItemProcessor
from tests.worker.helpers import FakeEnricher, get_item, make_batch, recording


async def age_raws(sm, days):
    async with sm() as db:
        await db.execute(update(RawRecording).values(created_at=utcnow() - timedelta(days=days)))
        await db.commit()


async def test_old_raw_deleted_keeping_session_and_enrichment(sm):
    _, (a,) = await make_batch(sm, [("a.jsonl", recording())])
    (claim,) = await claim_items(sm, 1)
    await ItemProcessor(sm, FakeEnricher(), 3, 30).process(claim)
    await age_raws(sm, 31)
    assert await cleanup_raw(sm, 30) == 1
    item = await get_item(sm, a)
    assert item.raw_id is None and item.session_id is not None
    async with sm() as db:
        assert (await db.execute(select(RawRecording))).first() is None
        session = (await db.execute(select(Session))).scalar_one()
        assert session.raw_id is None
        assert (await db.execute(select(Enrichment))).scalar_one()


async def test_recent_raw_and_raw_still_needed_are_kept(sm):
    _, (a, b) = await make_batch(sm, [("a.jsonl", recording("a")), ("b.jsonl", recording("b"))])
    await age_raws(sm, 60)  # both old, but both items are still queued
    assert await cleanup_raw(sm, 30) == 0
    async with sm() as db:
        await db.execute(
            update(BatchItem).where(BatchItem.id == a).values(status=ItemStatus.failed)
        )
        await db.commit()
    assert await cleanup_raw(sm, 30) == 1  # a's raw goes, b's is still queued
    assert (await get_item(sm, a)).raw_id is None
    assert (await get_item(sm, b)).raw_id is not None
    await age_raws(sm, 1)
    assert await cleanup_raw(sm, 30) == 0
