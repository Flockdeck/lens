"""Session browsing, raw event view, re-enrichment and deletion."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import ColumnElement, delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager, selectinload

from session_lens.api.deps import QueueApi, get_db, get_enricher, get_queue, get_store
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
    from session_lens.storage.base import RecordingStore

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


def _summary_fields(row: SessionRow, raw_available: bool) -> dict[str, Any]:
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
        "raw_available": raw_available,
        "created_at": row.created_at,
        "category": enr.category if enr else None,
        "outcome": enr.outcome if enr else None,
        "frustration": enr.frustration if enr else None,
        "summary": enr.summary if enr else None,
    }


def _raw_ok() -> ColumnElement[bool]:
    return exists().where(RawRecording.id == SessionRow.raw_id, RawRecording.expired_at.is_(None))


def _detail_of(row: SessionRow, raw_available: bool) -> SessionDetail:
    return SessionDetail(
        **_summary_fields(row, raw_available),
        metrics=row.metrics,
        risky_actions=row.risky_actions,
        files_touched=row.files_touched,
        warnings=row.warnings,
        enrichment=EnrichmentOut.model_validate(row.enrichment, from_attributes=True)
        if row.enrichment
        else None,
    )


async def _get_row(db: AsyncSession, session_id: int) -> tuple[SessionRow, bool]:
    result = (
        await db.execute(
            select(SessionRow, _raw_ok())
            .where(SessionRow.id == session_id)
            .options(selectinload(SessionRow.enrichment))
            .execution_options(populate_existing=True)
        )
    ).first()
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    return result[0], bool(result[1])


async def _detail(db: AsyncSession, session_id: int) -> SessionDetail:
    row, available = await _get_row(db, session_id)
    return _detail_of(row, available)


async def _read_raw(
    db: AsyncSession, queue: QueueApi, store: "RecordingStore", row: SessionRow
) -> bytes:
    from session_lens.storage.base import RecordingExpired

    gone = HTTPException(status.HTTP_410_GONE, "raw recording has expired or been deleted")
    if row.raw_id is None:
        raise gone
    try:
        return await queue.read_raw(db, store, row.raw_id)
    except RecordingExpired as exc:
        await db.commit()  # read_raw marks the row expired
        raise gone from exc


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
                base.add_columns(_raw_ok())
                .options(contains_eager(SessionRow.enrichment))
                .order_by(*ordering)
                .limit(limit)
                .offset(offset)
            )
        )
        .unique()
        .all()
    )
    return SessionList(
        total=total,
        items=[SessionSummary(**_summary_fields(r, bool(ok))) for r, ok in rows],
    )


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: int, db: Annotated[AsyncSession, Depends(get_db)]
) -> SessionDetail:
    return await _detail(db, session_id)


@router.get("/{session_id}/events", response_model=EventsPage)
async def get_events(
    session_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    queue: Annotated[QueueApi, Depends(get_queue)],
    store: Annotated["RecordingStore", Depends(get_store)],
    after_seq: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> EventsPage:
    from session_lens.recording.parser import parse

    row, _ = await _get_row(db, session_id)
    data = await _read_raw(db, queue, store, row)
    events = await asyncio.to_thread(parse, data)
    later = [e for e in events if e.seq > after_seq]
    page = later[:limit]
    dumped = [e.model_dump(by_alias=True, mode="json") for e in page]
    more = len(later) > limit
    return EventsPage(items=dumped, next_after_seq=page[-1].seq if more else None)


@router.post("/{session_id}/enrich", response_model=SessionDetail)
async def reenrich(
    session_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    enricher: Annotated["Enricher", Depends(get_enricher)],
    queue: Annotated[QueueApi, Depends(get_queue)],
    store: Annotated["RecordingStore", Depends(get_store)],
) -> SessionDetail:
    from session_lens.enrich.base import EnrichmentError
    from session_lens.recording.parser import EmptyRecording, UnsupportedVersion, analyze, parse

    row, _ = await _get_row(db, session_id)
    data = await _read_raw(db, queue, store, row)
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
    await queue.upsert_enrichment(db, session_id, result)
    await db.commit()
    log.info("session re-enriched", extra={"session_id": session_id})
    return await _detail(db, session_id)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    queue: Annotated[QueueApi, Depends(get_queue)],
    store: Annotated["RecordingStore", Depends(get_store)],
) -> Response:
    row, _ = await _get_row(db, session_id)
    content_hash = row.content_hash
    await db.execute(delete(Enrichment).where(Enrichment.session_id == session_id))
    await db.execute(delete(SessionRow).where(SessionRow.id == session_id))
    await queue.delete_raws_for_hash(db, store, content_hash)
    await db.commit()
    log.info("session deleted", extra={"session_id": session_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
