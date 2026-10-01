"""Fixtures for the enrich tests, built on the real recording models."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from session_lens.recording.models import Analysis


@pytest.fixture
def make_analysis() -> Callable[..., Analysis]:
    def make(**overrides: Any) -> Analysis:
        data: dict[str, Any] = {
            "recording_session": "s1",
            "project": "proj",
            "agent": "claude",
            "model": "claude-x",
            "started_at": datetime(2026, 1, 1, tzinfo=UTC),
            "completeness": "clean",
            "metrics": {"duration_seconds": 120, "turns": 5, "tool_calls": 10},
            "digest": {
                "user_prompts": [{"seq": 2, "text": "SECRET-PROMPT fix the bug"}],
                "final_messages": [{"seq": 40, "text": "done"}],
                "failing_results": [],
            },
        }
        data.update(overrides)
        return Analysis.model_validate(data)

    return make
