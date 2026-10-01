import asyncio

from session_lens.config import Settings
from session_lens.db.models import BatchStatus, ItemStatus
from session_lens.worker.loop import run_worker
from tests.worker.helpers import FakeEnricher, get_batch, get_item, make_batch, recording, retryable


async def run_until_done(sm, store, enricher, batch_id, concurrency=3, limit=15):
    settings = Settings(worker_concurrency=concurrency, worker_poll_seconds=0.05, max_attempts=3)
    stop = asyncio.Event()
    task = asyncio.create_task(run_worker(sm, store, enricher, settings, stop))
    try:
        async with asyncio.timeout(limit):
            while (await get_batch(sm, batch_id)).status != BatchStatus.done:  # noqa: ASYNC110
                await asyncio.sleep(0.05)
    finally:
        stop.set()
        await task


async def test_worker_drains_a_batch_with_bounded_concurrency(sm, store):
    batch_id, ids = await make_batch(
        sm, store, [(f"{i}.jsonl", recording(str(i))) for i in range(12)]
    )
    enricher = FakeEnricher(delay=0.05)
    await run_until_done(sm, store, enricher, batch_id, concurrency=3)
    assert enricher.calls == 12
    assert 1 < enricher.peak <= 3
    for i in ids:
        assert (await get_item(sm, i)).status == ItemStatus.done


async def test_failures_are_isolated_and_batch_still_finishes(sm, store):
    files = [
        ("ok1.jsonl", recording("a")),
        ("bad.jsonl", recording("b", v=2)),
        ("ok2.jsonl", recording("c")),
    ]
    batch_id, (ok1, bad, ok2) = await make_batch(sm, store, files)
    await run_until_done(sm, store, FakeEnricher(), batch_id)
    assert (await get_item(sm, ok1)).status == ItemStatus.done
    assert (await get_item(sm, ok2)).status == ItemStatus.done
    assert (await get_item(sm, bad)).status == ItemStatus.failed


async def test_flaky_enricher_eventually_succeeds_after_backoff(sm, store, monkeypatch):
    from session_lens.worker import processor

    monkeypatch.setattr(processor, "backoff_seconds", lambda attempt: 0.1)
    batch_id, (a,) = await make_batch(sm, store, [("a.jsonl", recording())])
    enricher = FakeEnricher([retryable(), retryable()])
    await run_until_done(sm, store, enricher, batch_id)
    item = await get_item(sm, a)
    assert item.status == ItemStatus.done and item.attempts == 3 and enricher.calls == 3
