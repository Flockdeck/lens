import asyncio

from session_lens.config import Settings
from session_lens.db.models import BatchStatus, ItemStatus
from session_lens.worker.loop import run_worker
from tests.worker.helpers import (
    FakeEnricher,
    eventually,
    get_batch,
    get_item,
    make_batch,
    recording,
    retryable,
)


def settings(**kw):
    kw.setdefault("worker_concurrency", 3)
    return Settings(worker_poll_seconds=0.05, max_attempts=3, **kw)


class Running:
    """A worker running in the background."""

    def __init__(self, sm, store, enricher, **kw):
        self.stop = asyncio.Event()
        self.task = asyncio.create_task(run_worker(sm, store, enricher, settings(**kw), self.stop))

    async def shutdown(self):
        self.stop.set()
        await asyncio.wait_for(self.task, 30)


async def batch_done(sm, batch_id):
    return (await get_batch(sm, batch_id)).status == BatchStatus.done


async def test_worker_drains_a_batch_with_bounded_concurrency(sm, store):
    batch_id, ids = await make_batch(
        sm, store, [(f"{i}.jsonl", recording(str(i))) for i in range(12)]
    )
    enricher = FakeEnricher(gated=True)
    worker = Running(sm, store, enricher, worker_concurrency=3)
    await enricher.wait_for(lambda: enricher.active == 3)  # three running, nine waiting
    assert enricher.calls == 3  # never more than the bound, while all are blocked
    enricher.release()
    await eventually(lambda: batch_done(sm, batch_id))
    await worker.shutdown()
    assert enricher.calls == 12 and enricher.peak == 3
    for i in ids:
        assert (await get_item(sm, i)).status == ItemStatus.done


async def test_failures_are_isolated_and_batch_still_finishes(sm, store):
    files = [
        ("ok1.jsonl", recording("a")),
        ("bad.jsonl", recording("b", v=2)),
        ("ok2.jsonl", recording("c")),
    ]
    batch_id, (ok1, bad, ok2) = await make_batch(sm, store, files)
    worker = Running(sm, store, FakeEnricher())
    await eventually(lambda: batch_done(sm, batch_id))
    await worker.shutdown()
    assert (await get_item(sm, ok1)).status == ItemStatus.done
    assert (await get_item(sm, ok2)).status == ItemStatus.done
    assert (await get_item(sm, bad)).status == ItemStatus.failed


async def test_flaky_enricher_eventually_succeeds_after_backoff(sm, store, monkeypatch):
    from session_lens.worker import processor

    monkeypatch.setattr(processor, "backoff_seconds", lambda attempt: 0.0)
    batch_id, (a,) = await make_batch(sm, store, [("a.jsonl", recording())])
    enricher = FakeEnricher([retryable(), retryable()])
    worker = Running(sm, store, enricher)
    await eventually(lambda: batch_done(sm, batch_id))
    await worker.shutdown()
    item = await get_item(sm, a)
    assert item.status == ItemStatus.done and item.attempts == 3 and enricher.calls == 3


async def test_shutdown_waits_for_inflight_items_within_the_grace_period(sm, store):
    batch_id, (a,) = await make_batch(sm, store, [("a.jsonl", recording())])
    enricher = FakeEnricher(gated=True)
    worker = Running(sm, store, enricher, shutdown_grace_seconds=30)
    await enricher.wait_for(lambda: enricher.active == 1)
    worker.stop.set()  # SIGTERM
    await asyncio.sleep(0)  # let the loop notice; the item is still blocked, so it must wait
    assert not worker.task.done()
    enricher.release()
    await asyncio.wait_for(worker.task, 30)
    assert (await get_item(sm, a)).status == ItemStatus.done


async def test_shutdown_past_the_grace_period_requeues_without_consuming_an_attempt(sm, store):
    batch_id, (a, b) = await make_batch(
        sm, store, [("a.jsonl", recording("a")), ("b.jsonl", recording("b"))]
    )
    enricher = FakeEnricher(gated=True)  # never released: the items hang
    worker = Running(sm, store, enricher, shutdown_grace_seconds=0.2)
    await enricher.wait_for(lambda: enricher.active == 2)
    await worker.shutdown()
    for i in (a, b):
        item = await get_item(sm, i)
        assert item.status == ItemStatus.queued
        assert item.attempts == 0 and item.locked_at is None and item.not_before is None
    assert (await get_batch(sm, batch_id)).status == BatchStatus.queued
