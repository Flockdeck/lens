"""Tolerant reader for Flockdeck recording format v1.

Rules (docs/recording-format.md section 2): ignore unknown fields, keep unknown event types
without interpreting them, refuse any other `v`, ignore a last line that is not valid JSON.
Warnings carry counts only, never recording content.
"""

import json
from collections.abc import Iterable

from pydantic import ValidationError

from session_lens.recording.digest import build_digest
from session_lens.recording.files import MAX_ITEMS, extract_files_touched
from session_lens.recording.metrics import completeness as compute_completeness
from session_lens.recording.metrics import compute_metrics
from session_lens.recording.models import (
    KNOWN_TYPES,
    SUPPORTED_VERSION,
    Analysis,
    Event,
)
from session_lens.recording.risk import find_risky_actions


class UnsupportedVersion(Exception):
    """The file has a format version this reader does not know. Permanent failure."""


class EmptyRecording(Exception):
    """The file holds no usable events. Permanent failure."""


def _version_message(version: object) -> str:
    """Describe a bad `v` without echoing recording content (it can be any JSON, any size)."""
    if isinstance(version, int) and not isinstance(version, bool):
        return f"recording format version {str(version)[:20]} is not supported"
    return f"recording format version of type {type(version).__name__} is not supported"


class EventList(list[Event]):
    """The events of a file, plus the warnings the parser raised while reading it.

    `parse` and `parse_lines` return this. The warnings live on the object, so they are lost
    if you copy it with `list(...)` or slice it. `analyze` reads them from an EventList; for any
    other list pass them with `parse_warnings=`. `analyze_lines` does both for you.
    """

    def __init__(self, events: list[Event] | None = None, warnings: list[str] | None = None):
        super().__init__(events or [])
        self.warnings: list[str] = warnings or []


def parse_lines(lines: Iterable[str]) -> EventList:
    """Parse stored lines, in order. Skips bad lines; may return an empty list.

    Safe on a page that starts mid-file: no `recording_started` is required, and an empty page
    is not an error. Raises UnsupportedVersion for a line with another `v`.
    """
    items = list(lines)
    last = max((i for i, ln in enumerate(items) if ln.strip()), default=-1)
    events: list[Event] = []
    malformed = 0
    cut_last_line = False

    for i, raw in enumerate(items):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw.lstrip("﻿") if i == 0 else raw)
        except (ValueError, RecursionError):
            # not JSON (JSONDecodeError), a number past Python's size limit (ValueError), or
            # nesting too deep to parse (RecursionError): a bad line, not a failed file
            if i == last:
                cut_last_line = True
            else:
                malformed += 1
            continue
        if not isinstance(obj, dict):
            malformed += 1
            continue
        version = obj.get("v")
        if version is not None and (isinstance(version, bool) or version != SUPPORTED_VERSION):
            raise UnsupportedVersion(_version_message(version))
        try:
            events.append(Event.model_validate(obj))
        except (ValidationError, ValueError):
            # missing envelope field, wrong field type or unparsable time
            if i == last:
                cut_last_line = True
            else:
                malformed += 1

    warnings: list[str] = []
    if cut_last_line:
        warnings.append("unterminated last line")
    if malformed:
        warnings.append(f"skipped {malformed} malformed lines")
    return EventList(events, warnings)


def parse(data: bytes) -> EventList:
    """Parse a whole recording. Raises UnsupportedVersion or EmptyRecording."""
    # decode per line so invalid UTF-8 only damages its own line
    events = parse_lines(raw.decode("utf-8", errors="replace") for raw in data.split(b"\n"))
    if not events:
        raise EmptyRecording("the recording holds no events")
    return events


def analyze_lines(lines: Iterable[str]) -> Analysis:
    """parse_lines + analyze, for a whole recording. Raises EmptyRecording if no events."""
    return analyze(parse_lines(lines))


def _seq_gaps(events: list[Event]) -> int:
    seqs = sorted({e.seq for e in events})
    return sum(b - a - 1 for a, b in zip(seqs, seqs[1:], strict=False)) + max(0, seqs[0] - 1)


def analyze(events: list[Event], parse_warnings: Iterable[str] | None = None) -> Analysis:
    """Compute everything deterministic from parsed events.

    Warnings raised while parsing come from `parse_warnings` if given, else from the events
    if they are an EventList, else there are none (a plain list carries no warnings).
    """
    if not events:
        raise EmptyRecording("the recording holds no events")

    if parse_warnings is not None:
        warnings = list(parse_warnings)
    elif isinstance(events, EventList):
        warnings = list(events.warnings)
    else:
        warnings = []
    metrics = compute_metrics(events)
    completeness = compute_completeness(events)
    risky = find_risky_actions(events)
    files = extract_files_touched(events)
    digest = build_digest(
        events, completeness=completeness, metrics=metrics, risky_actions=risky, files=files
    )

    unknown = sum(1 for e in events if e.type not in KNOWN_TYPES)
    if unknown:
        warnings.append(f"skipped {unknown} unknown event types")
    if completeness == "truncated":
        warnings.append("recording truncated at the size cap")
    elif completeness == "cut_off":
        warnings.append("cut off: no stop line")
    elif completeness == "partial_agent":
        warnings.append("agent records only start and stop lines")
    if metrics.unpaired_calls:
        warnings.append(f"{metrics.unpaired_calls} tool calls without a result")
    if max(files.read_total, files.edited_total, files.commands_total) > MAX_ITEMS:
        warnings.append(f"files and commands lists keep only the latest {MAX_ITEMS}")
    gaps = _seq_gaps(events)
    if gaps:
        warnings.append(f"{gaps} lines missing from the sequence")
    if metrics.redacted_lines:
        warnings.append(f"{metrics.redacted_lines} lines had content redacted")
    if metrics.clipped_lines:
        warnings.append(f"{metrics.clipped_lines} lines had content clipped")

    first = events[0]
    return Analysis(
        recording_session=first.session,
        project=next((e.project for e in events if e.project), None),
        agent=next((e.agent for e in events if e.agent), None),
        model=next((e.model for e in events if e.model), None),
        pane=first.pane,
        pane_name=next((e.pane_name for e in events if e.pane_name), None),
        started_at=first.time,
        ended_at=events[-1].time,
        completeness=completeness,
        metrics=metrics,
        risky_actions=risky,
        files_touched=files,
        warnings=warnings,
        digest=digest,
    )
