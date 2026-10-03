"""Response models for the HTTP API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class RejectedFile(BaseModel):
    filename: str
    reason: str


class BatchAccepted(BaseModel):
    id: int
    accepted: list[str]
    rejected: list[RejectedFile]


class BatchItemOut(BaseModel):
    id: int
    filename: str
    status: str
    attempts: int
    error: str | None
    session_id: int | None


class BatchOut(BaseModel):
    id: int
    status: str
    counts: dict[str, int]
    items: list[BatchItemOut]


class EnrichmentOut(BaseModel):
    summary: str
    category: str
    outcome: str
    frustration: float
    stuck_points: list[dict[str, Any]]
    prompt_feedback: str | None
    model_fit: str | None  # null: made before this was assessed
    model_fit_reason: str | None
    risk_notes: list[dict[str, Any]]
    input_tokens: int
    output_tokens: int
    model: str
    prompt_version: str
    created_at: datetime


class SessionSummary(BaseModel):
    id: int
    recording_session: str
    project: str | None
    agent: str | None
    model: str | None
    pane: str | None
    pane_name: str | None
    started_at: datetime | None
    ended_at: datetime | None
    completeness: str
    duration_seconds: float | None
    tool_calls: int | None
    raw_available: bool
    created_at: datetime
    category: str | None
    outcome: str | None
    frustration: float | None
    summary: str | None


class SessionList(BaseModel):
    total: int
    items: list[SessionSummary]


class SessionDetail(SessionSummary):
    metrics: dict[str, Any]
    risky_actions: list[dict[str, Any]]
    files_touched: dict[str, Any]
    warnings: list[str]
    enrichment: EnrichmentOut | None


class EventsPage(BaseModel):
    items: list[dict[str, Any]]
    next_after_seq: int | None  # pass as after_seq for the next page; None when exhausted


class TrendPoint(BaseModel):
    bucket: str  # ISO date; the Monday for interval=week
    sessions: int
    outcomes: dict[str, int]
    avg_frustration: float | None
    tool_error_rate: float | None


class ComparePoint(BaseModel):
    key: str
    sessions: int
    outcomes: dict[str, int]
    tool_error_rate: float | None
    permission_denial_rate: float | None
    avg_frustration: float | None


class Usage(BaseModel):
    input_tokens: int
    output_tokens: int
    enrichments: int


class RuntimeConfig(BaseModel):
    storage: str  # always "filesystem"; kept so the UI can say where recordings are
    enricher: str  # "mock" | "ollama" | "anthropic", as set in the UI or the environment
    raw_retention_days: int  # 0 = keep raw recordings forever
    cleanup_interval_seconds: int | None
    version: str
