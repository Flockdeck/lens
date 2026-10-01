import asyncio
from datetime import timedelta

from sqlalchemy import select, text, update

from session_lens.db.models import Batch, BatchItem, BatchStatus, ItemStatus, RawRecording, utcnow
from session_lens.worker import cleanup
from session_lens.worker.cleanup import LOCK_NAME, run_cleanup
from tests.worker.helpers import make_batch, recording


async def test_expiry_runs_in_chunks(sm, store, monkeypatch):
    monkeypatch.setattr(cleanup, "CHUNK", 2)
    await make_batch(sm, store, [(f"{i}.jsonl", recording(str(i))) for i in range(5)])
    async with sm() as db:
        await db.execute(update(BatchItem).values(status=ItemStatus.done))
        await db.execute(update(RawRecording).values(created_at=utcnow() - timedelta(days=40)))
        await db.commit()
    assert (await run_cleanup(sm, store, 30)).raws_expired == 5
    async with sm() as db:
        unexpired = select(RawRecording).where(RawRecording.expired_at.is_(None))
        assert (await db.execute(unexpired)).first() is None


async def test_old_batches_are_deleted_in_chunks(sm, store, monkeypatch):
    monkeypatch.setattr(cleanup, "CHUNK", 2)
    for i in range(5):
        await make_batch(sm, store, [(f"{i}.jsonl", recording(str(i)))])
    async with sm() as db:
        await db.execute(update(BatchItem).values(status=ItemStatus.done))
        await db.execute(
            update(Batch).values(status=BatchStatus.done, created_at=utcnow() - timedelta(days=100))
        )
        await db.commit()
    assert (await run_cleanup(sm, store, 30)).batches_deleted == 5


async def test_a_concurrent_run_is_skipped(sm, store):
    async with sm() as other:  # another cleanup run is in progress on a different connection
        got = (await other.execute(text("SELECT GET_LOCK(:n, 0)"), {"n": LOCK_NAME})).scalar()
        assert got == 1
        result = await run_cleanup(sm, store, 30)
        assert result.skipped and (result.raws_expired, result.batches_deleted) == (0, 0)
        await other.execute(text("SELECT RELEASE_LOCK(:n)"), {"n": LOCK_NAME})
    assert not (await run_cleanup(sm, store, 30)).skipped  # the lock was released


async def test_overlapping_runs_do_not_collide(sm, store):
    await make_batch(sm, store, [("a.jsonl", recording())])
    async with sm() as db:
        await db.execute(update(BatchItem).values(status=ItemStatus.done))
        await db.execute(update(RawRecording).values(created_at=utcnow() - timedelta(days=40)))
        await db.commit()
    results = await asyncio.gather(*(run_cleanup(sm, store, 30) for _ in range(4)))
    assert sum(r.raws_expired for r in results) == 1
