import asyncio

from lens.config import Settings
from lens.db.models import BatchStatus, ItemStatus
from lens.worker.loop import run_worker
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
    from lens.worker import processor

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


async def test_cleanup_loop_runs_with_the_worker_and_stops_with_it(sm, store, monkeypatch):
    from lens.worker import loop as loop_module

    calls = []

    async def counting(sm_, store_, days):
        calls.append(days)

    monkeypatch.setattr(loop_module, "run_cleanup", counting)
    before = asyncio.all_tasks()
    worker = Running(sm, store, FakeEnricher(), cleanup_interval_seconds=3600, raw_retention_days=7)

    async def ran():
        return bool(calls)

    await eventually(ran)  # runs immediately at startup, not after the first interval
    assert calls == [7]
    await worker.shutdown()
    assert not (asyncio.all_tasks() - before - {asyncio.current_task()})  # nothing left running


async def test_cleanup_loop_deletes_expired_files_then_stops(sm, store):
    import asyncio
    from datetime import timedelta

    from sqlalchemy import select, update

    from lens.db.models import BatchItem, ItemStatus, RawRecording, utcnow
    from lens.worker.loop import cleanup_loop

    _, (a,) = await make_batch(sm, store, [("a.jsonl", recording())])
    async with sm() as db:
        await db.execute(update(BatchItem).values(status=ItemStatus.done))
        await db.execute(update(RawRecording).values(created_at=utcnow() - timedelta(days=40)))
        await db.commit()
    stop = asyncio.Event()
    task = asyncio.create_task(cleanup_loop(sm, store, settings(), stop))

    async def expired():
        async with sm() as db:
            return (await db.execute(select(RawRecording.expired_at))).scalar_one() is not None

    await eventually(expired)
    assert not store.objects  # the file was deleted
    assert not task.done()  # sleeping until the next interval
    stop.set()
    await asyncio.wait_for(task, 5)  # stops promptly, not after the interval


async def test_cleanup_loop_survives_a_failing_run(sm, store, monkeypatch):
    import asyncio

    from lens.worker import loop as loop_module

    calls = 0

    async def flaky(sm_, store_, days):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("database hiccup")

    monkeypatch.setattr(loop_module, "run_cleanup", flaky)
    stop = asyncio.Event()
    task = asyncio.create_task(
        loop_module.cleanup_loop(sm, store, settings(cleanup_interval_seconds=1), stop)
    )

    async def ran_twice():
        return calls >= 2

    await eventually(ran_twice)  # the failure did not end the loop
    stop.set()
    await asyncio.wait_for(task, 5)


async def test_cleanup_interval_zero_disables_the_background_task(sm, store, monkeypatch):
    from lens.worker import loop as loop_module

    started = []
    monkeypatch.setattr(loop_module, "cleanup_loop", lambda *a: started.append(1))
    worker = Running(sm, store, FakeEnricher(), cleanup_interval_seconds=0)
    await worker.shutdown()
    assert started == []
