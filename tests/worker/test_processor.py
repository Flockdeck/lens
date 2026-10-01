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
    _now,
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


def processor(sm, enricher, max_attempts=3, timeout=30):
    return ItemProcessor(sm, enricher, max_attempts, timeout)


async def count(sm, model):
    async with sm() as db:
        return (await db.execute(select(func.count()).select_from(model))).scalar_one()


async def run_one(sm, enricher, files, **kw):
    batch_id, ids = await make_batch(sm, files)
    claims = await claim_items(sm, len(ids))
    p = processor(sm, enricher, **kw)
    for c in claims:
        await p.process(c)
    return batch_id, ids


async def test_success_stores_session_and_enrichment(sm):
    batch_id, (a,) = await run_one(sm, FakeEnricher(), [("a.jsonl", recording("s1"))])
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


async def test_resubmitting_same_content_is_free(sm):
    enricher = FakeEnricher()
    await run_one(sm, enricher, [("a.jsonl", recording("s1"))])
    await run_one(sm, enricher, [("again.jsonl", recording("s1"))])
    assert enricher.calls == 1
    assert await count(sm, Session) == 1 and await count(sm, Enrichment) == 1


async def test_grown_session_is_a_new_row(sm):
    enricher = FakeEnricher()
    files = [("a.jsonl", recording("s1")), ("b.jsonl", recording("s1", extra="more"))]
    await run_one(sm, enricher, files)
    assert enricher.calls == 2
    assert await count(sm, Session) == 2


@pytest.mark.parametrize("data", [recording("s1", v=2), b""])
async def test_permanent_parse_failure_fails_without_retry(sm, data):
    enricher = FakeEnricher()
    batch_id, (a,) = await run_one(sm, enricher, [("a.jsonl", data)])
    item = await get_item(sm, a)
    assert item.status == ItemStatus.failed and item.error_retryable is False
    assert item.not_before is None and enricher.calls == 0
    assert (await get_batch(sm, batch_id)).status == BatchStatus.done


async def test_one_bad_item_does_not_fail_the_batch(sm):
    _, (bad, good) = await run_one(
        sm, FakeEnricher(), [("bad.jsonl", recording("x", v=9)), ("good.jsonl", recording("y"))]
    )
    assert (await get_item(sm, bad)).status == ItemStatus.failed
    assert (await get_item(sm, good)).status == ItemStatus.done


async def test_retryable_enrichment_failure_backs_off_and_keeps_partial_result(sm):
    before = _now()
    batch_id, (a,) = await run_one(
        sm, FakeEnricher([retryable("rate limited")]), [("a.jsonl", recording())]
    )
    item = await get_item(sm, a)
    assert item.status == ItemStatus.queued and item.attempts == 1
    assert item.error_retryable is True and "rate limited" in item.error
    assert item.not_before > before + timedelta(seconds=2)  # base 5s, jitter keeps it >= 2.5s
    assert item.locked_at is None
    assert await count(sm, Session) == 1 and await count(sm, Enrichment) == 0  # partial result
    assert (await get_batch(sm, batch_id)).status == BatchStatus.queued


async def test_retry_then_success(sm):
    enricher = FakeEnricher([retryable()])
    _, (a,) = await run_one(sm, enricher, [("a.jsonl", recording())])
    async with sm() as db:
        await db.execute(update(BatchItem).where(BatchItem.id == a).values(not_before=None))
        await db.commit()
    (claim,) = await claim_items(sm, 1)
    assert claim.attempts == 2
    await processor(sm, enricher).process(claim)
    assert (await get_item(sm, a)).status == ItemStatus.done
    assert await count(sm, Session) == 1 and await count(sm, Enrichment) == 1


async def test_retryable_failure_exhausts_attempts(sm):
    enricher = FakeEnricher([retryable()] * 3)
    batch_id, (a,) = await run_one(sm, enricher, [("a.jsonl", recording())], max_attempts=1)
    item = await get_item(sm, a)
    assert item.status == ItemStatus.failed and item.attempts == 1
    assert (await get_batch(sm, batch_id)).status == BatchStatus.done


async def test_permanent_enrichment_failure_fails_immediately(sm):
    _, (a,) = await run_one(sm, FakeEnricher([permanent("bad output")]), [("a.jsonl", recording())])
    item = await get_item(sm, a)
    assert item.status == ItemStatus.failed and item.error_retryable is False


async def test_unexpected_error_is_retryable_and_leaks_no_text(sm):
    _, (a,) = await run_one(
        sm, FakeEnricher([RuntimeError("recording content here")]), [("a.jsonl", recording())]
    )
    item = await get_item(sm, a)
    assert item.status == ItemStatus.queued and item.error == "RuntimeError"


async def test_timeout_is_retryable(sm):
    _, ids = await make_batch(sm, [("a.jsonl", recording())])
    (claim,) = await claim_items(sm, 1)
    await processor(sm, FakeEnricher(delay=5), timeout=0.05).process(claim)
    item = await get_item(sm, ids[0])
    assert item.status == ItemStatus.queued and "timed out" in item.error


async def test_missing_raw_is_permanent(sm):
    _, (a,) = await make_batch(sm, [("a.jsonl", recording())])
    async with sm() as db:
        await db.execute(RawRecording.__table__.delete())
        await db.commit()
    (claim,) = await claim_items(sm, 1)
    await processor(sm, FakeEnricher()).process(claim)
    item = await get_item(sm, a)
    assert item.status == ItemStatus.failed and item.error_retryable is False


async def test_lost_claim_does_not_overwrite_the_new_holder(sm):
    _, (a,) = await make_batch(sm, [("a.jsonl", recording())])
    (claim,) = await claim_items(sm, 1)
    async with sm() as db:  # someone else took over: new claim token
        await db.execute(
            update(BatchItem)
            .where(BatchItem.id == a)
            .values(locked_at=_now() + timedelta(seconds=10))
        )
        await db.commit()
    await processor(sm, FakeEnricher()).process(claim)
    assert (await get_item(sm, a)).status == ItemStatus.running
