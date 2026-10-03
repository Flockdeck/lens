import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import func, select, update

from session_lens.db.models import (
    BatchItem,
    BatchStatus,
    Enrichment,
    ItemStatus,
    RawRecording,
    Session,
    utcnow,
)
from session_lens.worker.loop import claim_items
from session_lens.worker.processor import ItemProcessor
from tests.worker.helpers import (
    FakeEnricher,
    get_batch,
    get_item,
    make_batch,
    permanent,
    recording,
    retryable,
)


def processor(sm, store, enricher, max_attempts=3, timeout=30):
    return ItemProcessor(sm, store, enricher, max_attempts, timeout)


async def count(sm, model):
    async with sm() as db:
        return (await db.execute(select(func.count()).select_from(model))).scalar_one()


async def run_one(sm, store, enricher, files, **kw):
    batch_id, ids = await make_batch(sm, store, files)
    claims = await claim_items(sm, len(ids))
    p = processor(sm, store, enricher, **kw)
    for c in claims:
        await p.process(c)
    return batch_id, ids


async def test_success_stores_session_and_enrichment(sm, store):
    batch_id, (a,) = await run_one(sm, store, FakeEnricher(), [("a.jsonl", recording("s1"))])
    item = await get_item(sm, a)
    assert item.status == ItemStatus.done and item.locked_at is None and item.error is None
    async with sm() as db:
        s = await db.get(Session, item.session_id)
        assert (s.recording_session, s.project, s.completeness) == ("s1", "proj", "clean")
        assert s.metrics == {"turns": 2, "tool_calls": 3}
        assert s.risky_actions[0]["severity"] == "high"
        assert s.raw_id == item.raw_id
        e = (await db.execute(select(Enrichment))).scalar_one()
        assert (e.session_id, e.category, e.input_tokens, e.model) == (s.id, "bugfix", 100, "mock")
        assert e.stuck_points == [{"description": "x", "approx_seq": 3}]
    assert (await get_batch(sm, batch_id)).status == BatchStatus.done


async def test_resubmitting_same_content_is_free(sm, store):
    enricher = FakeEnricher()
    await run_one(sm, store, enricher, [("a.jsonl", recording("s1"))])
    await run_one(sm, store, enricher, [("again.jsonl", recording("s1"))])
    assert enricher.calls == 1
    assert await count(sm, Session) == 1 and await count(sm, Enrichment) == 1


async def test_longer_upload_supersedes_the_session_in_place(sm, store):
    enricher = FakeEnricher()
    await run_one(sm, store, enricher, [("a.jsonl", recording("s1"))])
    async with sm() as db:
        first = (await db.execute(select(Session))).scalar_one()
        first_id, first_hash, first_raw = first.id, first.content_hash, first.raw_id
        first_enrichment = (await db.execute(select(Enrichment))).scalar_one().id
    await run_one(sm, store, enricher, [("b.jsonl", recording("s1", extra="grown"))])
    assert enricher.calls == 2  # re-enriched
    async with sm() as db:
        sessions = (await db.execute(select(Session))).scalars().all()
        assert [s.id for s in sessions] == [first_id]  # one row per recording_session
        assert sessions[0].content_hash != first_hash
        assert sessions[0].raw_id != first_raw  # points at the newer upload
        enrichments = (await db.execute(select(Enrichment))).scalars().all()
        assert [(e.id, e.session_id) for e in enrichments] == [(first_enrichment, first_id)]


async def test_same_content_is_skipped_even_after_a_supersede_cycle(sm, store):
    enricher = FakeEnricher()
    await run_one(sm, store, enricher, [("a.jsonl", recording("s1", extra="v2"))])
    await run_one(sm, store, enricher, [("b.jsonl", recording("s1", extra="v2"))])
    assert enricher.calls == 1


async def test_session_without_enrichment_is_enriched_on_resubmit(sm, store):
    enricher = FakeEnricher([retryable()])
    await run_one(sm, store, enricher, [("a.jsonl", recording("s1"))])  # enrichment failed
    assert await count(sm, Enrichment) == 0
    await run_one(sm, store, enricher, [("b.jsonl", recording("s1"))])  # same content
    assert await count(sm, Session) == 1 and await count(sm, Enrichment) == 1


async def test_two_files_of_the_same_session_processed_together_make_one_session(sm, store):
    """Both runs are in flight at once; the second waits for the first's write lock and then
    updates its row instead of inserting a duplicate."""
    files = [("a.jsonl", recording("race")), ("b.jsonl", recording("race", extra="longer"))]
    _, ids = await make_batch(sm, store, files)
    claims = await claim_items(sm, 2)
    p = processor(sm, store, FakeEnricher())
    await asyncio.gather(*(p.process(c) for c in claims))
    assert await count(sm, Session) == 1
    for i in ids:
        assert (await get_item(sm, i)).status == ItemStatus.done


@pytest.mark.parametrize("data", [recording("s1", v=2), b""])
async def test_permanent_parse_failure_fails_without_retry(sm, store, data):
    enricher = FakeEnricher()
    batch_id, (a,) = await run_one(sm, store, enricher, [("a.jsonl", data)])
    item = await get_item(sm, a)
    assert item.status == ItemStatus.failed and item.error_retryable is False
    assert item.not_before is None and enricher.calls == 0
    assert (await get_batch(sm, batch_id)).status == BatchStatus.done


async def test_one_bad_item_does_not_fail_the_batch(sm, store):
    _, (bad, good) = await run_one(
        sm,
        store,
        FakeEnricher(),
        [("bad.jsonl", recording("x", v=9)), ("good.jsonl", recording("y"))],
    )
    assert (await get_item(sm, bad)).status == ItemStatus.failed
    assert (await get_item(sm, good)).status == ItemStatus.done


async def test_retryable_enrichment_failure_backs_off_and_keeps_partial_result(sm, store):
    before = utcnow()
    batch_id, (a,) = await run_one(
        sm, store, FakeEnricher([retryable("rate limited")]), [("a.jsonl", recording())]
    )
    item = await get_item(sm, a)
    assert item.status == ItemStatus.queued and item.attempts == 1
    assert item.error_retryable is True and "rate limited" in item.error
    assert item.not_before > before + timedelta(seconds=2)  # base 5s, jitter keeps it >= 2.5s
    assert item.locked_at is None
    assert await count(sm, Session) == 1 and await count(sm, Enrichment) == 0  # partial result
    assert (await get_batch(sm, batch_id)).status == BatchStatus.queued


async def test_retry_then_success(sm, store):
    enricher = FakeEnricher([retryable()])
    _, (a,) = await run_one(sm, store, enricher, [("a.jsonl", recording())])
    async with sm() as db:
        await db.execute(update(BatchItem).where(BatchItem.id == a).values(not_before=None))
        await db.commit()
    (claim,) = await claim_items(sm, 1)
    assert claim.attempts == 2
    await processor(sm, store, enricher).process(claim)
    assert (await get_item(sm, a)).status == ItemStatus.done
    assert await count(sm, Session) == 1 and await count(sm, Enrichment) == 1


async def test_retryable_failure_exhausts_attempts(sm, store):
    enricher = FakeEnricher([retryable()] * 3)
    batch_id, (a,) = await run_one(sm, store, enricher, [("a.jsonl", recording())], max_attempts=1)
    item = await get_item(sm, a)
    assert item.status == ItemStatus.failed and item.attempts == 1
    assert (await get_batch(sm, batch_id)).status == BatchStatus.done


async def test_permanent_enrichment_failure_fails_immediately(sm, store):
    _, (a,) = await run_one(
        sm, store, FakeEnricher([permanent("bad output")]), [("a.jsonl", recording())]
    )
    item = await get_item(sm, a)
    assert item.status == ItemStatus.failed and item.error_retryable is False


async def test_unexpected_error_is_retryable_and_leaks_no_text(sm, store):
    _, (a,) = await run_one(
        sm,
        store,
        FakeEnricher([RuntimeError("recording content here")]),
        [("a.jsonl", recording())],
    )
    item = await get_item(sm, a)
    assert item.status == ItemStatus.queued and item.error == "RuntimeError"


async def test_timeout_is_retryable(sm, store):
    _, ids = await make_batch(sm, store, [("a.jsonl", recording())])
    (claim,) = await claim_items(sm, 1)
    await processor(sm, store, FakeEnricher(gated=True), timeout=0.05).process(claim)  # hangs
    item = await get_item(sm, ids[0])
    assert item.status == ItemStatus.queued and "timed out" in item.error


async def test_expired_raw_fails_permanently(sm, store):
    batch_id, (a,) = await make_batch(sm, store, [("a.jsonl", recording())])
    async with sm() as db:
        await db.execute(RawRecording.__table__.update().values(expired_at=utcnow()))
        await db.commit()
    (claim,) = await claim_items(sm, 1)
    enricher = FakeEnricher()
    await processor(sm, store, enricher).process(claim)
    item = await get_item(sm, a)
    assert item.status == ItemStatus.failed and item.error_retryable is False
    assert item.error == "raw recording expired" and enricher.calls == 0
    assert (await get_batch(sm, batch_id)).status == BatchStatus.done


async def test_object_gone_marks_row_expired_and_fails(sm, store):
    _, (a,) = await make_batch(sm, store, [("a.jsonl", recording())])
    store.objects.clear()
    (claim,) = await claim_items(sm, 1)
    await processor(sm, store, FakeEnricher()).process(claim)
    assert (await get_item(sm, a)).error == "raw recording expired"
    async with sm() as db:
        assert (await db.execute(select(RawRecording.expired_at))).scalar_one() is not None


async def test_processing_end_to_end_with_every_real_store(sm, any_store):
    _, (a,) = await run_one(sm, any_store, FakeEnricher(), [("a.jsonl", recording("e2e"))])
    item = await get_item(sm, a)
    assert item.status == ItemStatus.done
    async with sm() as db:
        assert (await db.execute(select(Enrichment))).scalar_one()


async def test_processing_end_to_end_with_the_filesystem_store_and_real_files(sm, fs_store):
    files = [("a.jsonl", recording("fs-a")), ("b.jsonl", recording("fs-b"))]
    _, ids = await run_one(sm, fs_store, FakeEnricher(), files)
    for i in ids:
        assert (await get_item(sm, i)).status == ItemStatus.done
    on_disk = sorted(p for p in fs_store.root.rglob("*.jsonl"))
    assert len(on_disk) == 2  # the recordings are plain files under the data dir


async def test_lost_claim_does_not_overwrite_the_new_holder(sm, store):
    _, (a,) = await make_batch(sm, store, [("a.jsonl", recording())])
    (claim,) = await claim_items(sm, 1)
    async with sm() as db:  # someone else took over: new claim token
        await db.execute(
            update(BatchItem)
            .where(BatchItem.id == a)
            .values(locked_at=utcnow() + timedelta(seconds=10))
        )
        await db.commit()
    await processor(sm, store, FakeEnricher()).process(claim)
    assert (await get_item(sm, a)).status == ItemStatus.running
