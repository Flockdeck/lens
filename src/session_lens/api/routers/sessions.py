"""Session browsing, raw event view, re-enrichment and deletion."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Any, Literal

import zstandard
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager, selectinload

from session_lens.api.deps import get_db, get_enricher
from session_lens.api.schemas import (
    EnrichmentOut,
    EventsPage,
    SessionDetail,
    SessionList,
    SessionSummary,
)
from session_lens.db.models import Enrichment, RawRecording
from session_lens.db.models import Session as SessionRow

if TYPE_CHECKING:
    from session_lens.enrich.base import Enricher

router = APIRouter(prefix="/sessions", tags=["sessions"])
log = logging.getLogger("session_lens.api.sessions")

_SORTS: dict[str, Any] = {
    "started_at": SessionRow.started_at,
    "ended_at": SessionRow.ended_at,
    "created_at": SessionRow.created_at,
    "project": SessionRow.project,
    "frustration": Enrichment.frustration,
}


def _naive_utc(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def _summary_fields(row: SessionRow) -> dict[str, Any]:
    enr = row.enrichment
    return {
        "id": row.id,
        "recording_session": row.recording_session,
        "project": row.project,
        "agent": row.agent,
        "model": row.model,
        "pane": row.pane,
        "started_at": row.started_at,
        "ended_at": row.ended_at,
        "completeness": row.completeness,
        "duration_seconds": row.metrics.get("duration_seconds"),
        "tool_calls": row.metrics.get("tool_calls"),
        "has_raw": row.raw_id is not None,
        "created_at": row.created_at,
        "category": enr.category if enr else None,
        "outcome": enr.outcome if enr else None,
        "frustration": enr.frustration if enr else None,
        "summary": enr.summary if enr else None,
    }


def _detail(row: SessionRow) -> SessionDetail:
    return SessionDetail(
        **_summary_fields(row),
        metrics=row.metrics,
        risky_actions=row.risky_actions,
        files_touched=row.files_touched,
        warnings=row.warnings,
        enrichment=EnrichmentOut.model_validate(row.enrichment, from_attributes=True)
        if row.enrichment
        else None,
    )


async def _get_row(db: AsyncSession, session_id: int) -> SessionRow:
    row = (
        await db.execute(
            select(SessionRow)
            .where(SessionRow.id == session_id)
            .options(selectinload(SessionRow.enrichment))
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    return row


def _decompress(data: bytes, size: int) -> bytes:
    return zstandard.ZstdDecompressor().decompress(data, max_output_size=size + 1)


async def _load_raw(db: AsyncSession, row: SessionRow) -> bytes:
    raw = await db.get(RawRecording, row.raw_id) if row.raw_id is not None else None
    if raw is None:
        raise HTTPException(status.HTTP_410_GONE, "raw recording has been deleted")
    return await asyncio.to_thread(_decompress, raw.data, raw.size_bytes)


@router.get("", response_model=SessionList)
async def list_sessions(
    db: Annotated[AsyncSession, Depends(get_db)],
    project: str | None = None,
    agent: str | None = None,
    model: str | None = None,
    category: str | None = None,
    outcome: str | None = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    sort: Literal["started_at", "ended_at", "created_at", "project", "frustration"] = "started_at",
    order: Literal["asc", "desc"] = "desc",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SessionList:
    conditions: list[ColumnElement[bool]] = []
    for column, value in (
        (SessionRow.project, project),
        (SessionRow.agent, agent),
        (SessionRow.model, model),
        (Enrichment.category, category),
        (Enrichment.outcome, outcome),
    ):
        if value is not None:
            conditions.append(column == value)
    if (start := _naive_utc(from_)) is not None:
        conditions.append(SessionRow.started_at >= start)
    if (end := _naive_utc(to)) is not None:
        conditions.append(SessionRow.started_at <= end)

    base = select(SessionRow).outerjoin(SessionRow.enrichment).where(*conditions)
    total = (
        await db.execute(
            select(func.count()).select_from(base.with_only_columns(SessionRow.id).subquery())
        )
    ).scalar_one()
    sort_col = _SORTS[sort]
    ordering = [sort_col.asc() if order == "asc" else sort_col.desc(), SessionRow.id.desc()]
    rows = (
        (
            await db.execute(
                base.options(contains_eager(SessionRow.enrichment))
                .order_by(*ordering)
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return SessionList(total=total, items=[SessionSummary(**_summary_fields(r)) for r in rows])


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: int, db: Annotated[AsyncSession, Depends(get_db)]
) -> SessionDetail:
    return _detail(await _get_row(db, session_id))


@router.get("/{session_id}/events", response_model=EventsPage)
async def get_events(
    session_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    after_seq: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> EventsPage:
    from session_lens.recording.parser import iter_events

    row = await _get_row(db, session_id)
    data = await _load_raw(db, row)
    events = await asyncio.to_thread(iter_events, data, after_seq, limit)
    dumped = [e.model_dump(mode="json") for e in events]
    next_seq = dumped[-1]["seq"] if len(dumped) >= limit else None
    return EventsPage(events=dumped, next_after_seq=next_seq)


@router.post("/{session_id}/enrich", response_model=SessionDetail)
async def reenrich(
    session_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    enricher: Annotated["Enricher", Depends(get_enricher)],
) -> SessionDetail:
    from session_lens.enrich.base import EnrichmentError
    from session_lens.recording.parser import (
        EmptyRecording,
        UnsupportedVersion,
        analyze,
        parse,
    )

    row = await _get_row(db, session_id)
    data = await _load_raw(db, row)
    try:
        analysis = await asyncio.to_thread(lambda: analyze(parse(data)))
    except (UnsupportedVersion, EmptyRecording) as exc:
        raise HTTPException(422, type(exc).__name__) from exc
    try:
        result = await enricher.enrich(analysis)
    except EnrichmentError as exc:
        log.warning(
            "re-enrich failed", extra={"session_id": session_id, "retryable": exc.retryable}
        )
        code = status.HTTP_503_SERVICE_UNAVAILABLE if exc.retryable else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(code, "enrichment failed") from exc

    values: dict[str, Any] = {
        "prompt_version": result.prompt_version,
        "model": result.model,
        "summary": result.summary,
        "category": result.category,
        "outcome": result.outcome,
        "frustration": result.frustration,
        "stuck_points": [p.model_dump(mode="json") for p in result.stuck_points],
        "prompt_feedback": result.prompt_feedback,
        "risk_notes": [n.model_dump(mode="json") for n in result.risk_notes],
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
    }
    if row.enrichment is None:
        row.enrichment = Enrichment(**values)
    else:
        for key, value in values.items():
            setattr(row.enrichment, key, value)
        row.enrichment.created_at = datetime.now(UTC).replace(tzinfo=None)
    await db.commit()
    log.info("session re-enriched", extra={"session_id": session_id})
    return _detail(await _get_row(db, session_id))


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: int, db: Annotated[AsyncSession, Depends(get_db)]) -> Response:
    row = await _get_row(db, session_id)
    raw_id = row.raw_id
    await db.execute(delete(Enrichment).where(Enrichment.session_id == session_id))
    await db.execute(delete(SessionRow).where(SessionRow.id == session_id))
    if raw_id is not None:
        still_used = (
            await db.execute(
                select(func.count()).select_from(SessionRow).where(SessionRow.raw_id == raw_id)
            )
        ).scalar_one()
        if not still_used:
            await db.execute(delete(RawRecording).where(RawRecording.id == raw_id))
    await db.commit()
    log.info("session deleted", extra={"session_id": session_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
