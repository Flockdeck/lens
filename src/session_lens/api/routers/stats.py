"""Aggregate statistics over sessions and enrichments."""

from collections import defaultdict
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from session_lens.api.dates import RANGE_DOC, range_conditions
from session_lens.api.deps import get_db
from session_lens.api.schemas import ComparePoint, TrendPoint, Usage
from session_lens.db.models import Enrichment
from session_lens.db.models import Session as SessionRow

router = APIRouter(prefix="/stats", tags=["stats"])

UNENRICHED = "unenriched"


def _metric(*path: str) -> ColumnElement[int]:
    """Integer metric from the JSON column, 0 when missing."""
    element = SessionRow.metrics[path] if len(path) > 1 else SessionRow.metrics[path[0]]
    return func.coalesce(element.as_integer(), 0)


@dataclass
class _Acc:
    sessions: int = 0
    outcomes: dict[str, int] | None = None
    frustration_sum: float = 0.0
    frustration_n: int = 0
    errors: int = 0
    calls: int = 0
    denied: int = 0
    prompts: int = 0

    def add(self, row: Any) -> None:
        if self.outcomes is None:
            self.outcomes = defaultdict(int)
        self.sessions += row.sessions
        self.outcomes[row.outcome or UNENRICHED] += row.sessions
        self.frustration_sum += float(row.frustration_sum or 0)
        self.frustration_n += row.frustration_n
        self.errors += int(row.errors or 0)
        self.calls += int(row.calls or 0)
        self.denied += int(row.denied or 0)
        self.prompts += int(row.prompts or 0)

    @property
    def outcome_counts(self) -> dict[str, int]:
        return dict(self.outcomes or {})

    @property
    def avg_frustration(self) -> float | None:
        return self.frustration_sum / self.frustration_n if self.frustration_n else None

    @property
    def error_rate(self) -> float | None:
        return self.errors / self.calls if self.calls else None

    @property
    def denial_rate(self) -> float | None:
        return self.denied / self.prompts if self.prompts else None


def _aggregates() -> list[Any]:
    return [
        Enrichment.outcome.label("outcome"),
        func.count(SessionRow.id).label("sessions"),
        func.sum(Enrichment.frustration).label("frustration_sum"),
        func.count(Enrichment.id).label("frustration_n"),
        func.sum(_metric("tool_errors")).label("errors"),
        func.sum(_metric("tool_calls")).label("calls"),
        func.sum(_metric("permission", "denied")).label("denied"),
        func.sum(_metric("permission", "prompts")).label("prompts"),
    ]


@router.get(
    "/trends",
    response_model=list[TrendPoint],
    description=(
        "Sessions grouped by day or week (weeks start Monday, UTC), using `started_at` and "
        "falling back to the upload time (`created_at`) when `started_at` is NULL. " + RANGE_DOC
    ),
)
async def trends(
    db: Annotated[AsyncSession, Depends(get_db)],
    project: str | None = None,
    interval: Literal["day", "week"] = "day",
    from_: Annotated[str | None, Query(alias="from", examples=["2026-01-01"])] = None,
    to: Annotated[str | None, Query(examples=["2026-01-31"])] = None,
) -> list[TrendPoint]:
    moment = func.coalesce(SessionRow.started_at, SessionRow.created_at)
    day = func.date(moment)
    # Weeks start on Monday (MySQL WEEKDAY: Monday = 0).
    bucket = day if interval == "day" else func.subdate(day, func.weekday(moment))
    stmt = (
        select(bucket.label("bucket"), *_aggregates())
        .select_from(SessionRow)
        .outerjoin(Enrichment, Enrichment.session_id == SessionRow.id)
        .group_by(bucket, Enrichment.outcome)
        .order_by(bucket)
    )
    if project is not None:
        stmt = stmt.where(SessionRow.project == project)
    stmt = stmt.where(*range_conditions(moment, from_, to))
    accs: dict[str, _Acc] = defaultdict(_Acc)
    for row in (await db.execute(stmt)).all():
        accs[str(row.bucket)].add(row)
    return [
        TrendPoint(
            bucket=key,
            sessions=a.sessions,
            outcomes=a.outcome_counts,
            avg_frustration=a.avg_frustration,
            tool_error_rate=a.error_rate,
        )
        for key, a in sorted(accs.items())
    ]


@router.get("/compare", response_model=list[ComparePoint])
async def compare(
    db: Annotated[AsyncSession, Depends(get_db)],
    by: Literal["agent", "model"] = "agent",
    project: str | None = None,
) -> list[ComparePoint]:
    key_col = SessionRow.agent if by == "agent" else SessionRow.model
    stmt = (
        select(key_col.label("key"), *_aggregates())
        .select_from(SessionRow)
        .outerjoin(Enrichment, Enrichment.session_id == SessionRow.id)
        .group_by(key_col, Enrichment.outcome)
    )
    if project is not None:
        stmt = stmt.where(SessionRow.project == project)
    accs: dict[str, _Acc] = defaultdict(_Acc)
    for row in (await db.execute(stmt)).all():
        accs[row.key or "unknown"].add(row)
    return [
        ComparePoint(
            key=key,
            sessions=a.sessions,
            outcomes=a.outcome_counts,
            tool_error_rate=a.error_rate,
            permission_denial_rate=a.denial_rate,
            avg_frustration=a.avg_frustration,
        )
        for key, a in sorted(accs.items(), key=lambda kv: (-kv[1].sessions, kv[0]))
    ]


@router.get("/usage", response_model=Usage)
async def usage(db: Annotated[AsyncSession, Depends(get_db)]) -> Usage:
    row = (
        await db.execute(
            select(
                func.coalesce(func.sum(Enrichment.input_tokens), 0),
                func.coalesce(func.sum(Enrichment.output_tokens), 0),
                func.count(Enrichment.id),
            )
        )
    ).one()
    return Usage(input_tokens=int(row[0]), output_tokens=int(row[1]), enrichments=row[2])
