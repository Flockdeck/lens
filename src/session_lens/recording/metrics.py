"""Deterministic metrics computed from parsed events."""

from collections import Counter
from typing import Literal

from session_lens.recording.models import RECORDER_TYPES, Event, Metrics, PermissionStats

Completeness = Literal["clean", "truncated", "cut_off", "partial_agent"]


def completeness(events: list[Event]) -> Completeness:
    """How the file ended. Agents with no hooks record only the recorder's own lines."""
    if all(e.type in RECORDER_TYPES for e in events):
        return "partial_agent"
    last = events[-1].type
    if last == "recording_truncated":
        return "truncated"
    if last == "recording_stopped":
        return "clean"
    return "cut_off"


def _matches(prompt: Event, outcome: Event) -> bool:
    if prompt.tool_use_id and outcome.tool_use_id:
        return prompt.tool_use_id == outcome.tool_use_id
    if prompt.tool and outcome.tool:
        return prompt.tool == outcome.tool
    return True


def compute_metrics(events: list[Event]) -> Metrics:
    m = Metrics()
    perm = PermissionStats()
    mix: Counter[str] = Counter()
    call_ids: set[str] = set()
    result_ids: set[str] = set()
    idless_calls: Counter[str] = Counter()
    idless_results: Counter[str] = Counter()
    pending: list[Event] = []

    for e in events:
        if e.redacted:
            m.redacted_lines += 1
        if e.clipped:
            m.clipped_lines += 1

        if e.type == "user_prompt":
            # A <task-notification> is Claude Code talking to itself, not a turn the user took.
            if not e.subagent and not (e.text or "").startswith("<task-notification"):
                m.turns += 1
        elif e.type == "tool_call":
            name = e.tool or "unknown"
            m.tool_calls += 1
            mix[name] += 1
            if e.tool_use_id:
                call_ids.add(e.tool_use_id)
            else:
                idless_calls[name] += 1
        elif e.type == "tool_result":
            if e.interrupted:
                m.tool_interrupted += 1
            elif e.is_error:
                m.tool_errors += 1
            if e.tool_use_id:
                result_ids.add(e.tool_use_id)
            else:
                idless_results[e.tool or "unknown"] += 1
        elif e.type == "permission_prompt":
            perm.prompts += 1
            pending.append(e)
        elif e.type == "permission_outcome":
            if e.inferred:
                perm.inferred += 1
            match e.outcome:
                case "allowed":
                    perm.allowed += 1
                case "denied":
                    perm.denied += 1
                case "auto_approved":
                    perm.auto_approved += 1
                case "abandoned":
                    perm.abandoned += 1
            for i, p in enumerate(pending):
                if _matches(p, e):
                    del pending[i]
                    break

    # A prompt that never got an outcome line (crash, or the line was lost) was not answered.
    perm.abandoned += len(pending)

    m.tool_mix = dict(mix)
    m.permission = perm
    m.unpaired_calls = len(call_ids - result_ids) + sum(
        max(0, n - idless_results[tool]) for tool, n in idless_calls.items()
    )
    m.status_seconds = _status_seconds(events)
    m.duration_seconds = round(max(0.0, (events[-1].time - events[0].time).total_seconds()), 3)
    return m


def _status_seconds(events: list[Event]) -> dict[str, float]:
    """Time in each pane status: a status lasts until the next status line, or the last line."""
    end = events[-1].time
    changes = [e for e in events if e.type == "status" and e.status]
    totals: dict[str, float] = {}
    for i, e in enumerate(changes):
        until = changes[i + 1].time if i + 1 < len(changes) else end
        assert e.status is not None
        totals[e.status] = totals.get(e.status, 0.0) + max(0.0, (until - e.time).total_seconds())
    return {k: round(v, 3) for k, v in totals.items()}
