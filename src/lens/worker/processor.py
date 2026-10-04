"""Processing one batch item: raw blob -> parse -> analyze -> Session -> enrich -> Enrichment."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import case, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lens.db.models import BatchItem, Enrichment, ItemStatus, RawRecording, Session, utcnow
from lens.enrich.base import Enricher, EnrichmentResult
from lens.recording.models import Analysis
from lens.recording.parser import analyze, parse
from lens.storage.base import RecordingExpired, RecordingStore
from lens.worker.queue import read_raw, refresh_batch_status
from lens.worker.retry import Failure, backoff_seconds, classify

log = logging.getLogger(__name__)


def _analyze_blob(data: bytes) -> Analysis:
    return analyze(parse(data))


@dataclass(frozen=True)
class Claim:
    item_id: int
    batch_id: int
    locked_at: datetime  # the claim token: only its holder may finish the item
    attempts: int


def _naive(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=None) if value else None  # stored as naive UTC


def _apply_analysis(
    row: Session, analysis: Analysis, content_hash: str, raw_id: int | None
) -> None:
    row.content_hash = content_hash
    row.project = analysis.project
    row.agent = analysis.agent
    row.model = analysis.model
    row.pane = analysis.pane
    row.pane_name = analysis.pane_name
    row.started_at = _naive(analysis.started_at)
    row.ended_at = _naive(analysis.ended_at)
    row.completeness = analysis.completeness
    row.metrics = analysis.metrics.model_dump(mode="json")
    row.risky_actions = [r.model_dump(mode="json") for r in analysis.risky_actions]
    row.files_touched = analysis.files_touched.model_dump(mode="json")
    row.warnings = list(analysis.warnings)
    if raw_id is not None:
        row.raw_id = raw_id  # the newest raw we could actually read


async def upsert_session(
    db: AsyncSession, analysis: Analysis, content_hash: str, raw_id: int | None
) -> tuple[Session, bool]:
    """One Session per recording_session: a later upload of the same session supersedes the
    stored one in place. Returns `(row, unchanged)`, where unchanged means the stored content
    hash already equals `content_hash`. Flushed, not committed. Two workers inserting the same
    recording_session at once are handled: the loser's insert fails on the unique key and it
    updates the winner's row instead."""
    query = select(Session).where(Session.recording_session == analysis.recording_session)
    for _attempt in range(2):
        row = (await db.execute(query)).scalar_one_or_none()
        if row is not None:
            unchanged = row.content_hash == content_hash
            _apply_analysis(row, analysis, content_hash, raw_id)
            await db.flush()
            return row, unchanged
        row = Session(recording_session=analysis.recording_session)
        _apply_analysis(row, analysis, content_hash, raw_id)
        try:
            async with db.begin_nested():
                db.add(row)
                await db.flush()
        except IntegrityError:
            continue  # lost the race; reload and update
        return row, False
    raise RuntimeError("could not upsert session")


def _apply_result(row: Enrichment, result: EnrichmentResult) -> None:
    row.prompt_version = result.prompt_version
    row.model = result.model
    row.summary = result.summary
    row.category = result.category
    row.outcome = result.outcome
    row.frustration = result.frustration
    row.stuck_points = [s.model_dump(mode="json") for s in result.stuck_points]
    row.prompt_feedback = result.prompt_feedback
    row.model_fit = result.model_fit
    row.model_fit_reason = result.model_fit_reason
    row.risk_notes = [n.model_dump(mode="json") for n in result.risk_notes]
    row.input_tokens = result.input_tokens
    row.output_tokens = result.output_tokens
    row.created_at = utcnow()


async def upsert_enrichment(db: AsyncSession, session_id: int, result: EnrichmentResult) -> None:
    """Create or overwrite the session's enrichment. Flushed, not committed. Reusable by the
    API's re-enrich endpoint. Safe against a concurrent insert for the same session (a second
    worker, or a re-enrich request): the loser updates the winner's row."""
    query = select(Enrichment).where(Enrichment.session_id == session_id)
    for _attempt in range(2):
        row = (await db.execute(query)).scalar_one_or_none()
        if row is not None:
            _apply_result(row, result)
            await db.flush()
            return
        row = Enrichment(session_id=session_id)
        _apply_result(row, result)
        try:
            async with db.begin_nested():
                db.add(row)
                await db.flush()
        except IntegrityError:
            continue
        return
    raise RuntimeError("could not upsert enrichment")


class ItemProcessor:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        store: RecordingStore,
        enricher: Enricher,
        max_attempts: int,
        timeout_seconds: float,
    ) -> None:
        self._sm = sessionmaker
        self._store = store
        self._enricher = enricher
        self._max_attempts = max_attempts
        # An item must finish before its claim goes stale, or another worker would take it
        # over while it is still running.
        self._timeout = timeout_seconds

    async def process(self, claim: Claim) -> None:
        """Run one claimed item to done, back to queued (retry), or failed. Item errors never
        propagate."""
        try:
            async with asyncio.timeout(self._timeout):
                session_id = await self._run(claim)
        except asyncio.CancelledError:
            # Shutdown cancelled us mid-item: hand it back without costing an attempt.
            await asyncio.shield(self._release(claim))
            raise
        except Exception as exc:
            await self._fail(claim, classify(exc))
        else:
            await self._settle(claim, status=ItemStatus.done, session_id=session_id)

    async def _release(self, claim: Claim) -> None:
        async with self._sm() as db:
            result = await db.execute(
                update(BatchItem)
                .where(
                    BatchItem.id == claim.item_id,
                    BatchItem.status == ItemStatus.running,
                    BatchItem.locked_at == claim.locked_at,
                )
                .values(
                    status=ItemStatus.queued,
                    attempts=case((BatchItem.attempts > 1, BatchItem.attempts - 1), else_=0),
                    locked_at=None,
                    not_before=None,
                    updated_at=utcnow(),
                )
            )
            if result.rowcount:  # type: ignore[attr-defined]
                await refresh_batch_status(db, claim.batch_id)
            await db.commit()
        log.info("item released on shutdown", extra={"item_id": claim.item_id})

    async def _run(self, claim: Claim) -> int:
        # Phase 1: parse and store the computed session. This happens before the LLM call, so
        # a flaky enricher still leaves a usable (unenriched) session behind.
        async with self._sm() as db:
            item = await db.get(BatchItem, claim.item_id)
            if item is None or item.raw_id is None:
                raise RecordingExpired(claim.item_id)
            try:
                data = await read_raw(db, self._store, item.raw_id)
            except RecordingExpired:
                await db.commit()  # keep expired_at if the object turned out to be gone
                raise
            raw = await db.get(RawRecording, item.raw_id)
            assert raw is not None
            # CPU-bound on up to 16 MiB: keep it off the event loop.
            analysis = await asyncio.to_thread(_analyze_blob, data)
            del data
            row, unchanged = await upsert_session(db, analysis, raw.content_hash, raw.id)
            session_id = row.id
            enriched = (
                await db.execute(select(Enrichment.id).where(Enrichment.session_id == session_id))
            ).first()
            await db.commit()
        if unchanged and enriched is not None:  # same content resubmitted: nothing to redo
            return session_id
        # Phase 2: no DB connection is held while the LLM runs.
        result = await self._enricher.enrich(analysis)
        async with self._sm() as db:
            await upsert_enrichment(db, session_id, result)
            await db.commit()
        return session_id

    async def _fail(self, claim: Claim, failure: Failure) -> None:
        log.warning(
            "item failed",
            extra={
                "item_id": claim.item_id,
                "batch_id": claim.batch_id,
                "attempt": claim.attempts,
                "retryable": failure.retryable,
                "error": failure.message,
            },
        )
        if failure.retryable and claim.attempts < self._max_attempts:
            await self._settle(
                claim,
                status=ItemStatus.queued,
                error=failure.message,
                retryable=True,
                not_before=utcnow() + timedelta(seconds=backoff_seconds(claim.attempts)),
            )
        else:
            await self._settle(
                claim,
                status=ItemStatus.failed,
                error=failure.message,
                retryable=failure.retryable,
            )

    async def _settle(
        self,
        claim: Claim,
        *,
        status: ItemStatus,
        session_id: int | None = None,
        error: str | None = None,
        retryable: bool | None = None,
        not_before: datetime | None = None,
    ) -> None:
        values: dict[str, object] = {
            "status": status,
            "error": error,
            "error_retryable": retryable,
            "not_before": not_before,
            "locked_at": None,
            "updated_at": utcnow(),
        }
        if session_id is not None:
            values["session_id"] = session_id
        async with self._sm() as db:
            # Fenced on the claim token: if our claim went stale and was taken over, drop ours.
            result = await db.execute(
                update(BatchItem)
                .where(
                    BatchItem.id == claim.item_id,
                    BatchItem.status == ItemStatus.running,
                    BatchItem.locked_at == claim.locked_at,
                )
                .values(**values)
            )
            if result.rowcount:  # type: ignore[attr-defined]
                await refresh_batch_status(db, claim.batch_id)
            else:
                log.warning("claim lost", extra={"item_id": claim.item_id})
            await db.commit()
