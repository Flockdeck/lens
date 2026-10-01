"""The claim loop: claim due items with SELECT ... FOR UPDATE SKIP LOCKED, run them with
bounded concurrency, and recover claims whose worker died."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from session_lens.config import Settings
from session_lens.db.models import BatchItem, ItemStatus, utcnow
from session_lens.enrich.base import Enricher
from session_lens.worker.processor import Claim, ItemProcessor
from session_lens.worker.queue import refresh_batch_status

log = logging.getLogger(__name__)

STALE_SWEEP_SECONDS = 30.0


async def claim_items(sm: async_sessionmaker[AsyncSession], limit: int) -> list[Claim]:
    """Atomically move up to `limit` due queued items to running. Concurrent workers skip rows
    another worker holds, so no item is claimed twice. attempts is counted here, so an item
    that keeps killing its worker still runs out of attempts."""
    if limit <= 0:
        return []
    now = utcnow().replace(
        microsecond=0
    )  # MySQL DATETIME has no fraction; the claim token must round-trip
    async with sm() as db:
        items = (
            (
                await db.execute(
                    select(BatchItem)
                    .where(
                        BatchItem.status == ItemStatus.queued,
                        or_(BatchItem.not_before.is_(None), BatchItem.not_before <= now),
                    )
                    .order_by(BatchItem.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            .scalars()
            .all()
        )
        claims: list[Claim] = []
        for item in items:
            item.status = ItemStatus.running
            item.locked_at = now
            item.attempts += 1
            claims.append(Claim(item.id, item.batch_id, now, item.attempts))
        await db.flush()
        for batch_id in sorted({c.batch_id for c in claims}):
            await refresh_batch_status(db, batch_id)
        await db.commit()
    return claims


async def recover_stale(
    sm: async_sessionmaker[AsyncSession], claim_timeout_seconds: int, max_attempts: int
) -> int:
    """Re-queue running items whose claim is older than the timeout (their worker died or
    hung); fail those that have used all their attempts. Returns how many were recovered."""
    cutoff = utcnow() - timedelta(seconds=claim_timeout_seconds)
    async with sm() as db:
        items = (
            (
                await db.execute(
                    select(BatchItem)
                    .where(BatchItem.status == ItemStatus.running, BatchItem.locked_at < cutoff)
                    .order_by(BatchItem.id)
                    .with_for_update(skip_locked=True)
                )
            )
            .scalars()
            .all()
        )
        for item in items:
            item.locked_at = None
            item.error = "claim timed out"
            item.error_retryable = True
            if item.attempts >= max_attempts:
                item.status = ItemStatus.failed
            else:
                item.status = ItemStatus.queued
                item.not_before = None
        await db.flush()
        for batch_id in sorted({i.batch_id for i in items}):
            await refresh_batch_status(db, batch_id)
        await db.commit()
    if items:
        log.warning("recovered stale claims", extra={"count": len(items)})
    return len(items)


async def run_worker(
    sm: async_sessionmaker[AsyncSession],
    enricher: Enricher,
    settings: Settings,
    stop: asyncio.Event,
) -> None:
    """Run until `stop` is set, then let in-flight items finish."""
    processor = ItemProcessor(
        sm, enricher, settings.max_attempts, timeout_seconds=settings.claim_timeout_seconds * 0.9
    )
    inflight: set[asyncio.Task[None]] = set()
    clock = asyncio.get_running_loop().time
    last_sweep = clock() - STALE_SWEEP_SECONDS

    log.info("worker started", extra={"concurrency": settings.worker_concurrency})
    while not stop.is_set():
        claims: list[Claim] = []
        try:
            if clock() - last_sweep >= STALE_SWEEP_SECONDS:
                await recover_stale(sm, settings.claim_timeout_seconds, settings.max_attempts)
                last_sweep = clock()
            claims = await claim_items(sm, settings.worker_concurrency - len(inflight))
        except Exception:
            log.exception("claim failed")  # e.g. DB briefly unreachable; keep the loop alive
        for claim in claims:
            task = asyncio.create_task(processor.process(claim))
            inflight.add(task)
            task.add_done_callback(inflight.discard)
        if claims and len(inflight) < settings.worker_concurrency:
            continue  # the queue may hold more due work
        # Sleep until a slot frees, the poll interval passes, or we are told to stop.
        stopper = asyncio.create_task(stop.wait())
        try:
            await asyncio.wait(
                {stopper, *inflight},
                timeout=settings.worker_poll_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            stopper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await stopper
    if inflight:
        log.info("draining", extra={"inflight": len(inflight)})
        await asyncio.gather(*inflight, return_exceptions=True)
    log.info("worker stopped")
