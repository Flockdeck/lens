"""Pydantic models for Flockdeck recording format v1 and for what is computed from it."""

import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SUPPORTED_VERSION = 1

KNOWN_TYPES = frozenset(
    {
        "recording_started",
        "recording_stopped",
        "recording_truncated",
        "session",
        "user_prompt",
        "assistant_message",
        "tool_call",
        "tool_result",
        "permission_prompt",
        "permission_outcome",
        "status",
    }
)

# Event types that only the recorder itself writes. A file holding nothing else comes from an
# agent Flockdeck has no hooks for.
RECORDER_TYPES = frozenset({"recording_started", "recording_stopped", "recording_truncated"})

_EXTRA_FRACTION = re.compile(r"(\.\d{6})\d+")

_LOOSE_STR_FIELDS = (
    "pane_name",
    "project",
    "agent",
    "model",
    "conversation",
    "subagent",
    "text",
    "source",
    "reason",
    "tool",
    "tool_use_id",
    "output",
    "outcome",
    "status",
    "previous",
    "detail",
)
_LOOSE_BOOL_FIELDS = ("redacted", "is_error", "interrupted", "inferred")


def parse_time(value: str) -> datetime:
    """Parse RFC 3339 with up to nanosecond precision (Python keeps microseconds)."""
    dt = datetime.fromisoformat(_EXTRA_FRACTION.sub(r"\1", value))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


class Event(BaseModel):
    """One parsed line. The envelope is typed; unknown fields are kept as extras.

    The required envelope (`v`, `seq`, `time`, `session`, `pane`, `type`) is strict: a line
    without it, or with it in another shape, is malformed. Every other field is read loosely: if
    a later release gives one a different shape (say `text` as an object), the field reads as
    None and the line is kept as an event of unknown shape, not dropped.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    v: int = Field(strict=True)
    seq: int = Field(strict=True)
    time: datetime
    session: str
    pane: str
    type: str

    pane_name: str | None = Field(default=None, alias="paneName")
    project: str | None = None
    agent: str | None = None
    model: str | None = None
    conversation: str | None = None
    subagent: str | None = None
    redacted: bool | None = None
    clipped: dict[str, int] | None = None

    # Type-specific fields. All optional here: the parser must not reject a line for lacking one.
    text: str | None = None
    source: str | None = None
    reason: str | None = None
    tool: str | None = None
    tool_use_id: str | None = Field(default=None, alias="toolUseId")
    input: Any = None
    output: str | None = None
    is_error: bool | None = Field(default=None, alias="isError")
    interrupted: bool | None = None
    outcome: str | None = None
    inferred: bool | None = None
    status: str | None = None
    previous: str | None = None
    detail: str | None = None

    @field_validator("time", mode="before")
    @classmethod
    def _parse_time(cls, value: Any) -> Any:
        # Only RFC 3339 text. Pydantic would otherwise read an integer as a Unix timestamp.
        if isinstance(value, str):
            return parse_time(value)
        raise ValueError("time must be an RFC 3339 string")

    @field_validator(*_LOOSE_STR_FIELDS, mode="before")
    @classmethod
    def _loose_str(cls, value: Any) -> Any:
        return value if isinstance(value, str) else None

    @field_validator(*_LOOSE_BOOL_FIELDS, mode="before")
    @classmethod
    def _loose_bool(cls, value: Any) -> Any:
        return value if isinstance(value, bool) else None

    @field_validator("clipped", mode="before")
    @classmethod
    def _loose_clipped(cls, value: Any) -> Any:
        if isinstance(value, dict) and all(
            isinstance(k, str) and isinstance(n, int) and not isinstance(n, bool)
            for k, n in value.items()
        ):
            return value
        return None


class PermissionStats(BaseModel):
    prompts: int = 0
    allowed: int = 0
    denied: int = 0
    auto_approved: int = 0
    abandoned: int = 0
    # Outcomes the recorder worked out from what came next, rather than were reported.
    inferred: int = 0


class Metrics(BaseModel):
    duration_seconds: float = 0.0
    turns: int = 0
    tool_calls: int = 0
    tool_mix: dict[str, int] = Field(default_factory=dict)
    # Tool failures, not counting those the user interrupted (see tool_interrupted).
    tool_errors: int = 0
    tool_interrupted: int = 0
    unpaired_calls: int = 0
    permission: PermissionStats = Field(default_factory=PermissionStats)
    status_seconds: dict[str, float] = Field(default_factory=dict)
    redacted_lines: int = 0
    clipped_lines: int = 0


class RiskyAction(BaseModel):
    seq: int
    tool: str
    summary: str
    severity: Literal["low", "medium", "high"]
    rule: str


class FilesTouched(BaseModel):
    """The lists keep the latest entries up to a cap; the totals are counted before the cap."""

    read: list[str] = Field(default_factory=list)
    edited: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    read_total: int = 0
    edited_total: int = 0
    commands_total: int = 0


class DigestMessage(BaseModel):
    seq: int
    text: str
    redacted: bool = False
    clipped: bool = False


class DigestFailure(BaseModel):
    seq: int
    tool: str
    output: str
    interrupted: bool = False


class Digest(BaseModel):
    """Compact, size-bounded input for the LLM. Never the raw transcript."""

    project: str | None = None
    agent: str | None = None
    model: str | None = None
    completeness: str = "clean"
    metrics: Metrics = Field(default_factory=Metrics)
    user_prompts: list[DigestMessage] = Field(default_factory=list)
    omitted_prompts: int = 0
    final_messages: list[DigestMessage] = Field(default_factory=list)
    failing_results: list[DigestFailure] = Field(default_factory=list)
    omitted_failures: int = 0
    risky_actions: list[RiskyAction] = Field(default_factory=list)
    files_edited: list[str] = Field(default_factory=list)
    files_read_count: int = 0
    commands_count: int = 0


class Analysis(BaseModel):
    """Everything computed from one recording file, without an LLM."""

    recording_session: str
    project: str | None = None
    agent: str | None = None
    model: str | None = None
    pane: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    completeness: Literal["clean", "truncated", "cut_off", "partial_agent"]
    metrics: Metrics
    risky_actions: list[RiskyAction] = Field(default_factory=list)
    files_touched: FilesTouched = Field(default_factory=FilesTouched)
    warnings: list[str] = Field(default_factory=list)
    digest: Digest
