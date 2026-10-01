"""Processing one batch item: raw blob -> parse -> analyze -> Session -> enrich -> Enrichment."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from session_lens.db.models import BatchItem, Enrichment, ItemStatus, RawRecording, Session, _now
from session_lens.enrich.base import Enricher, EnrichmentResult
from session_lens.recording.models import Analysis
from session_lens.recording.parser import analyze, parse
from session_lens.worker.queue import decompress, refresh_batch_status
from session_lens.worker.retry import Failure, MissingRaw, backoff_seconds, classify

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Claim:
    item_id: int
    batch_id: int
    locked_at: datetime  # the claim token: only its holder may finish the item
    attempts: int


def _naive(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=None) if value else None  # stored as naive UTC


async def upsert_session(
    db: AsyncSession, analysis: Analysis, content_hash: str, raw_id: int | None
) -> Session:
    """Create or refresh the Session keyed on (recording_session, content_hash). Flushed, not
    committed. An existing session keeps its raw_id unless that was deleted by retention."""
    row = (
        await db.execute(
            select(Session).where(
                Session.recording_session == analysis.recording_session,
                Session.content_hash == content_hash,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = Session(recording_session=analysis.recording_session, content_hash=content_hash)
        db.add(row)
    row.project = analysis.project
    row.agent = analysis.agent
    row.model = analysis.model
    row.pane = analysis.pane
    row.started_at = _naive(analysis.started_at)
    row.ended_at = _naive(analysis.ended_at)
    row.completeness = analysis.completeness
    row.metrics = analysis.metrics.model_dump(mode="json")
    row.risky_actions = [r.model_dump(mode="json") for r in analysis.risky_actions]
    row.files_touched = analysis.files_touched.model_dump(mode="json")
    row.warnings = list(analysis.warnings)
    if row.raw_id is None:
        row.raw_id = raw_id
    await db.flush()
    return row


async def upsert_enrichment(db: AsyncSession, session_id: int, result: EnrichmentResult) -> None:
    """Create or overwrite the session's enrichment. Flushed, not committed. Reusable by the
    API's re-enrich endpoint."""
    row = (
        await db.execute(select(Enrichment).where(Enrichment.session_id == session_id))
    ).scalar_one_or_none()
    if row is None:
        row = Enrichment(session_id=session_id)
        db.add(row)
    row.prompt_version = result.prompt_version
    row.model = result.model
    row.summary = result.summary
    row.category = result.category
    row.outcome = result.outcome
    row.frustration = result.frustration
    row.stuck_points = [s.model_dump(mode="json") for s in result.stuck_points]
    row.prompt_feedback = result.prompt_feedback
    row.risk_notes = [n.model_dump(mode="json") for n in result.risk_notes]
    row.input_tokens = result.input_tokens
    row.output_tokens = result.output_tokens
    row.created_at = _now()
    await db.flush()


class ItemProcessor:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        enricher: Enricher,
        max_attempts: int,
        timeout_seconds: float,
    ) -> None:
        self._sm = sessionmaker
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
        except Exception as exc:
            await self._fail(claim, classify(exc))
        else:
            await self._settle(claim, status=ItemStatus.done, session_id=session_id)

    async def _run(self, claim: Claim) -> int:
        # Phase 1: parse and store the computed session. This happens before the LLM call, so
        # a flaky enricher still leaves a usable (unenriched) session behind.
        async with self._sm() as db:
            item = await db.get(BatchItem, claim.item_id)
            raw = await db.get(RawRecording, item.raw_id) if item and item.raw_id else None
            if raw is None:
                raise MissingRaw
            analysis = analyze(parse(decompress(raw.data)))
            row = await upsert_session(db, analysis, raw.content_hash, raw.id)
            session_id = row.id
            enriched = (
                await db.execute(select(Enrichment.id).where(Enrichment.session_id == session_id))
            ).first()
            await db.commit()
        if enriched is not None:  # same content resubmitted: nothing to redo
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
                not_before=_now() + timedelta(seconds=backoff_seconds(claim.attempts)),
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
            "updated_at": _now(),
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
