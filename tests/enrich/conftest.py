"""Fixtures for the enrich tests.

`Analysis` belongs to the recording component. Until it lands, a minimal stand-in with the
contract's field names is registered as `session_lens.recording.models`. Once the real module
exists the stand-in is not used.
"""

import importlib.util
import sys
import types
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal

import pytest
from pydantic import BaseModel, Field


def _real_models_available() -> bool:
    try:
        return importlib.util.find_spec("session_lens.recording.models") is not None
    except ModuleNotFoundError:
        return False


if not _real_models_available():

    class Permission(BaseModel):
        prompts: int = 0
        allowed: int = 0
        denied: int = 0
        auto_approved: int = 0
        abandoned: int = 0

    class Metrics(BaseModel):
        duration_seconds: float = 0
        turns: int = 0
        tool_calls: int = 0
        tool_mix: dict[str, int] = Field(default_factory=dict)
        tool_errors: int = 0
        tool_interrupted: int = 0
        unpaired_calls: int = 0
        permission: Permission = Field(default_factory=Permission)
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
        read: list[str] = Field(default_factory=list)
        edited: list[str] = Field(default_factory=list)
        commands: list[str] = Field(default_factory=list)

    class Digest(BaseModel):
        user_prompts: list[str] = Field(default_factory=list)
        final_assistant_messages: list[str] = Field(default_factory=list)
        failing_tool_results: list[str] = Field(default_factory=list)

    class Analysis(BaseModel):
        recording_session: str
        project: str | None = None
        agent: str | None = None
        model: str | None = None
        pane: str | None = None
        started_at: datetime | None = None
        ended_at: datetime | None = None
        completeness: Literal["clean", "truncated", "cut_off", "partial_agent"] = "clean"
        metrics: Metrics = Field(default_factory=Metrics)
        risky_actions: list[RiskyAction] = Field(default_factory=list)
        files_touched: FilesTouched = Field(default_factory=FilesTouched)
        warnings: list[str] = Field(default_factory=list)
        digest: Digest = Field(default_factory=Digest)

    _module = types.ModuleType("session_lens.recording.models")
    for _cls in (Permission, Metrics, RiskyAction, FilesTouched, Digest, Analysis):
        setattr(_module, _cls.__name__, _cls)
    sys.modules["session_lens.recording.models"] = _module

from session_lens.recording.models import Analysis as _Analysis  # noqa: E402


@pytest.fixture
def make_analysis() -> Callable[..., _Analysis]:
    def make(**overrides: Any) -> _Analysis:
        data: dict[str, Any] = {
            "recording_session": "s1",
            "project": "proj",
            "agent": "claude",
            "model": "claude-x",
            "started_at": datetime(2026, 1, 1, tzinfo=UTC),
            "metrics": {"duration_seconds": 120, "turns": 5, "tool_calls": 10},
            "digest": {
                "user_prompts": ["SECRET-PROMPT fix the bug"],
                "final_assistant_messages": ["done"],
                "failing_tool_results": [],
            },
        }
        data.update(overrides)
        return _Analysis.model_validate(data)

    return make
