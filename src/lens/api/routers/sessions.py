"""Session browsing, raw event view, re-enrichment and deletion."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import ColumnElement, delete, exists, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager, selectinload

from lens.api.dates import RANGE_DOC, range_conditions
from lens.api.deps import (
    EnricherProvider,
    QueueApi,
    StoreProvider,
    get_db,
    get_enricher_provider,
    get_queue,
    get_store_provider,
    provide_or_503,
)
from lens.api.schemas import (
    EnrichmentOut,
    EventsPage,
    SessionDetail,
    SessionList,
    SessionSummary,
)
from lens.db.models import Enrichment, RawRecording
from lens.db.models import Session as SessionRow

router = APIRouter(prefix="/sessions", tags=["sessions"])
log = logging.getLogger("lens.api.sessions")

_SORTS: dict[str, Any] = {
    "started_at": SessionRow.started_at,
    "ended_at": SessionRow.ended_at,
    "created_at": SessionRow.created_at,
    "project": SessionRow.project,
    "frustration": Enrichment.frustration,
}


def _summary_fields(row: SessionRow, raw_available: bool) -> dict[str, Any]:
    enr = row.enrichment
    return {
        "id": row.id,
        "recording_session": row.recording_session,
        "project": row.project,
        "agent": row.agent,
        "model": row.model,
        "pane": row.pane,
        "pane_name": row.pane_name,
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


async def _fetch_raw(db: AsyncSession, store_provider: StoreProvider, raw_id: int | None) -> bytes:
    """Fetch a recording without holding a DB transaction or pooled connection during the
    object-store call: look up the key, end the transaction, then read from the store.

    410 if the file is expired/missing; 503 if the store itself is failing.
    """
    from lens.storage.base import RecordingExpired

    gone = HTTPException(status.HTTP_410_GONE, "raw recording has expired or been deleted")
    if raw_id is None:
        raise gone
    found = (
        await db.execute(
            select(RawRecording.object_key, RawRecording.expired_at).where(
                RawRecording.id == raw_id
            )
        )
    ).first()
    await db.rollback()  # release the connection before the slow call
    if found is None or found.expired_at is not None:
        raise gone
    store = provide_or_503(store_provider, "object store")
    try:
        data: bytes = await store.get(found.object_key)
        return data
    except RecordingExpired as exc:
        # The file is gone (removed outside the app, or expired before the reconcile ran):
        # record it in a fresh transaction so raw_available is false from now on.
        await db.execute(
            update(RawRecording)
            .where(RawRecording.id == raw_id, RawRecording.expired_at.is_(None))
            .values(expired_at=datetime.now(UTC).replace(tzinfo=None))
        )
        await db.commit()
        raise gone from exc
    except Exception as exc:
        log.error("object store get failed", extra={"exc_type": type(exc).__name__})
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "object store unavailable"
        ) from exc


@router.get(
    "",
    response_model=SessionList,
    description=(
        "List sessions. "
        + RANGE_DOC
        + " The range applies to `started_at`: sessions whose `started_at` is NULL (for example "
        "a recording that never logged a start) are excluded whenever `from` or `to` is given, "
        "and are included otherwise. Sorting by a nullable column puts NULLs last when "
        "descending and first when ascending."
    ),
)
async def list_sessions(
    db: Annotated[AsyncSession, Depends(get_db)],
    project: str | None = None,
    agent: str | None = None,
    model: str | None = None,
    category: str | None = None,
    outcome: str | None = None,
    from_: Annotated[str | None, Query(alias="from", examples=["2026-01-01"])] = None,
    to: Annotated[str | None, Query(examples=["2026-01-31"])] = None,
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
    conditions += range_conditions(SessionRow.started_at, from_, to)

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
    store_provider: Annotated[StoreProvider, Depends(get_store_provider)],
    after_seq: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> EventsPage:
    from lens.recording.parser import parse

    row, _ = await _get_row(db, session_id)
    data = await _fetch_raw(db, store_provider, row.raw_id)
    try:
        events = await asyncio.to_thread(parse, data)
    except Exception as exc:
        log.warning(
            "recording unparseable",
            extra={"session_id": session_id, "exc_type": type(exc).__name__},
        )
        raise HTTPException(422, "recording could not be parsed") from exc
    later = [e for e in events if e.seq > after_seq]
    page = later[:limit]
    dumped = [e.model_dump(by_alias=True, mode="json") for e in page]
    more = len(later) > limit
    return EventsPage(items=dumped, next_after_seq=page[-1].seq if more else None)


@router.post("/{session_id}/enrich", response_model=SessionDetail)
async def reenrich(
    session_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    enricher_provider: Annotated[EnricherProvider, Depends(get_enricher_provider)],
    queue: Annotated[QueueApi, Depends(get_queue)],
    store_provider: Annotated[StoreProvider, Depends(get_store_provider)],
) -> SessionDetail:
    """Re-run enrichment, overwriting the stored result.

    No DB transaction is held while the file is fetched, parsed or sent to the LLM; the result
    is written in a fresh transaction (retried once on a concurrent-insert conflict).
    """
    from lens.enrich.base import EnrichmentError
    from lens.recording.parser import analyze, parse

    row, _ = await _get_row(db, session_id)
    data = await _fetch_raw(db, store_provider, row.raw_id)
    try:
        analysis = await asyncio.to_thread(lambda: analyze(parse(data)))
    except Exception as exc:
        log.warning(
            "recording unparseable",
            extra={"session_id": session_id, "exc_type": type(exc).__name__},
        )
        raise HTTPException(422, "recording could not be parsed") from exc
    enricher = provide_or_503(enricher_provider, "enricher")
    try:
        result = await enricher.enrich(analysis)
    except EnrichmentError as exc:
        log.warning(
            "re-enrich failed", extra={"session_id": session_id, "retryable": exc.retryable}
        )
        code = status.HTTP_503_SERVICE_UNAVAILABLE if exc.retryable else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(code, "enrichment failed") from exc
    except Exception as exc:
        log.error(
            "re-enrich crashed", extra={"session_id": session_id, "exc_type": type(exc).__name__}
        )
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "enrichment failed") from exc

    for attempt in (1, 2):
        try:
            await queue.upsert_enrichment(db, session_id, result)
            await db.commit()
            break
        except IntegrityError as exc:
            # A concurrent re-enrich inserted the row first (unique session_id): retry once,
            # when the upsert will find it and overwrite. Or the session was deleted meanwhile.
            await db.rollback()
            exists_now = (
                await db.execute(select(func.count()).where(SessionRow.id == session_id))
            ).scalar_one()
            await db.rollback()
            if not exists_now:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from exc
            if attempt == 2:
                raise HTTPException(
                    status.HTTP_409_CONFLICT, "concurrent re-enrichment, try again"
                ) from exc
    log.info("session re-enriched", extra={"session_id": session_id})
    return await _detail(db, session_id)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    queue: Annotated[QueueApi, Depends(get_queue)],
    store_provider: Annotated[StoreProvider, Depends(get_store_provider)],
) -> Response:
    row, _ = await _get_row(db, session_id)
    store = provide_or_503(store_provider, "object store")
    # Raw rows are found through the session (Session.raw_id, batch_items.session_id), so remove
    # them before the session row.
    await queue.delete_raws_for_session(db, store, session_id)
    await db.execute(delete(Enrichment).where(Enrichment.session_id == session_id))
    await db.execute(delete(SessionRow).where(SessionRow.id == session_id))
    await db.commit()
    log.info("session deleted", extra={"session_id": session_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
