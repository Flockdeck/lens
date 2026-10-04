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
        "conversation_title",
        "conversation_compacted",
    }
)

# Lines that only files made from live hooks (Flockdeck 0.3.47) hold. A transcript made from the
# agent's stored conversation has none of them.
HOOK_ONLY_TYPES = frozenset({"session", "permission_prompt", "permission_outcome", "status"})

# `recording_started` text that says how the file was made (docs/recording-format.md section 6).
TRANSCRIPT_START_TEXT = "start of the transcript"
HOOK_START_TEXTS = frozenset({"turned on", "resumed"})

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
    "title",
    "trigger",
    "stop_reason",
    "git_branch",
    "cwd",
    "agent_version",
)
_LOOSE_INT_FIELDS = ("tokens_before", "tokens_after")
_LOOSE_BOOL_FIELDS = ("redacted", "is_error", "interrupted", "inferred")


def parse_time(value: str) -> datetime:
    """Parse RFC 3339 with up to nanosecond precision (Python keeps microseconds)."""
    dt = datetime.fromisoformat(_EXTRA_FRACTION.sub(r"\1", value))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


_USAGE_KEYS = ("inputTokens", "outputTokens", "cacheCreationInputTokens", "cacheReadInputTokens")


class TokenUsage(BaseModel):
    """Tokens a model reply used, as the agent stored them. Not a bill."""

    model_config = ConfigDict(populate_by_name=True)

    input_tokens: int = Field(default=0, alias="inputTokens")
    output_tokens: int = Field(default=0, alias="outputTokens")
    cache_creation_input_tokens: int = Field(default=0, alias="cacheCreationInputTokens")
    cache_read_input_tokens: int = Field(default=0, alias="cacheReadInputTokens")


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
    # Written by transcripts only (Flockdeck 0.3.48 and later), where the stored entry has them.
    git_branch: str | None = Field(default=None, alias="gitBranch")
    cwd: str | None = None
    agent_version: str | None = Field(default=None, alias="agentVersion")

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
    # conversation_title, conversation_compacted, and the per-reply usage of a transcript
    title: str | None = None
    trigger: str | None = None
    tokens_before: int | None = Field(default=None, alias="tokensBefore")
    tokens_after: int | None = Field(default=None, alias="tokensAfter")
    usage: TokenUsage | None = None
    stop_reason: str | None = Field(default=None, alias="stopReason")

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

    @field_validator(*_LOOSE_INT_FIELDS, mode="before")
    @classmethod
    def _loose_int(cls, value: Any) -> Any:
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    @field_validator("usage", mode="before")
    @classmethod
    def _loose_usage(cls, value: Any) -> Any:
        # all four counts, as non-negative integers, or the field reads as absent
        if isinstance(value, dict) and all(
            isinstance(value.get(key), int) and not isinstance(value.get(key), bool)
            for key in _USAGE_KEYS
        ):
            return {key: max(0, value[key]) for key in _USAGE_KEYS}
        return None

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


SourceFormat = Literal["transcript", "hooks"]


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
    # Whether the file has any permission lines / status lines at all. A transcript made from the
    # agent's stored conversation has none, so `permission` (all zero) and `status_seconds`
    # (empty) say nothing there: no denials were recorded, which is not the same as none
    # happening. None on metrics stored before these fields existed.
    permissions_recorded: bool | None = None
    status_recorded: bool | None = None
    # Replies that were summarised to make room (conversation_compacted lines).
    compactions: int = 0
    # Sum of the per-reply `usage` of a transcript; None if no line has one.
    usage: TokenUsage | None = None
    redacted_lines: int = 0
    clipped_lines: int = 0
    # Every model the recording names, in order of first appearance. A session can change model
    # part-way (e.g. /model); `Analysis.model` is only the first.
    models: list[str] = Field(default_factory=list)


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
    title: str | None = None
    source_format: SourceFormat | None = None
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
    # In a transcript made from the agent's stored conversation `pane` holds the conversation's
    # id (not a pane's), and there is no `pane_name`.
    pane: str | None = None
    pane_name: str | None = None
    conversation: str | None = None
    # The conversation's last title (a `conversation_title` line), if the file has one.
    title: str | None = None
    # "transcript": made from the agent's stored conversation (Flockdeck 0.3.48 and later);
    # "hooks": made from live hook events (0.3.47); None where the file does not say.
    source_format: SourceFormat | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    completeness: Literal["clean", "truncated", "cut_off", "partial_agent"]
    metrics: Metrics
    risky_actions: list[RiskyAction] = Field(default_factory=list)
    files_touched: FilesTouched = Field(default_factory=FilesTouched)
    warnings: list[str] = Field(default_factory=list)
    digest: Digest
