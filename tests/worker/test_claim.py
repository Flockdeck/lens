import asyncio
from datetime import timedelta

from sqlalchemy import update

from session_lens.db.models import BatchItem, BatchStatus, ItemStatus, utcnow
from session_lens.worker.loop import claim_items, recover_stale
from tests.worker.helpers import get_batch, get_item, make_batch, recording


async def test_claim_marks_running_and_counts_attempt(sm, store):
    batch_id, (a,) = await make_batch(sm, store, [("a.jsonl", recording())])
    (claim,) = await claim_items(sm, 5)
    assert claim.item_id == a and claim.attempts == 1
    item = await get_item(sm, a)
    assert item.status == ItemStatus.running and item.locked_at == claim.locked_at
    assert (await get_batch(sm, batch_id)).status == BatchStatus.running
    assert await claim_items(sm, 5) == []


async def test_concurrent_claimers_never_share_items(sm, store):
    _, ids = await make_batch(sm, store, [(f"{i}.jsonl", recording(str(i))) for i in range(30)])
    results = await asyncio.gather(*(claim_items(sm, 4) for _ in range(12)))
    claimed = [c.item_id for r in results for c in r]
    assert len(claimed) == len(set(claimed)) == 30
    assert set(claimed) == set(ids)


async def test_not_before_is_respected(sm, store):
    _, (a, b) = await make_batch(
        sm, store, [("a.jsonl", recording("a")), ("b.jsonl", recording("b"))]
    )
    async with sm() as db:
        await db.execute(
            update(BatchItem)
            .where(BatchItem.id == a)
            .values(not_before=utcnow() + timedelta(hours=1))
        )
        await db.commit()
    assert [c.item_id for c in await claim_items(sm, 5)] == [b]
    async with sm() as db:
        await db.execute(
            update(BatchItem)
            .where(BatchItem.id == a)
            .values(not_before=utcnow() - timedelta(seconds=1))
        )
        await db.commit()
    assert [c.item_id for c in await claim_items(sm, 5)] == [a]


async def _age_claim(sm, item_id, seconds):
    async with sm() as db:
        await db.execute(
            update(BatchItem)
            .where(BatchItem.id == item_id)
            .values(locked_at=utcnow() - timedelta(seconds=seconds))
        )
        await db.commit()


async def test_stale_claim_is_requeued_fresh_one_is_not(sm, store):
    _, (a, b) = await make_batch(
        sm, store, [("a.jsonl", recording("a")), ("b.jsonl", recording("b"))]
    )
    await claim_items(sm, 5)
    await _age_claim(sm, a, 600)
    assert await recover_stale(sm, claim_timeout_seconds=300, max_attempts=4) == 1
    assert (await get_item(sm, a)).status == ItemStatus.queued
    assert (await get_item(sm, b)).status == ItemStatus.running
    assert [c.attempts for c in await claim_items(sm, 5)] == [2]


async def test_stale_claim_out_of_attempts_fails(sm, store):
    batch_id, (a,) = await make_batch(sm, store, [("a.jsonl", recording())])
    await claim_items(sm, 5)
    await _age_claim(sm, a, 600)
    assert await recover_stale(sm, claim_timeout_seconds=300, max_attempts=1) == 1
    item = await get_item(sm, a)
    assert item.status == ItemStatus.failed and item.error == "claim timed out"
    assert (await get_batch(sm, batch_id)).status == BatchStatus.done


async def test_claim_concurrent_with_cancel_does_not_deadlock(sm, store):
    from session_lens.worker.queue import cancel_batch

    async def cancel(batch_id):
        async with sm() as db:
            n = await cancel_batch(db, batch_id)
            await db.commit()
            return n

    for _ in range(15):
        batch_id, ids = await make_batch(
            sm, store, [(f"{i}.jsonl", recording(str(i))) for i in range(6)]
        )
        claimed, cancelled = await asyncio.gather(claim_items(sm, 6), cancel(batch_id))
        assert len(claimed) + cancelled == 6  # every item ran or was cancelled, never both
        statuses = [(await get_item(sm, i)).status for i in ids]
        assert statuses.count(ItemStatus.running) == len(claimed)
        assert statuses.count(ItemStatus.cancelled) == cancelled
