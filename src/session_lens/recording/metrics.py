"""Deterministic metrics computed from parsed events."""

from collections import Counter, deque
from typing import Literal

from session_lens.recording.models import (
    KNOWN_TYPES,
    RECORDER_TYPES,
    Event,
    Metrics,
    PermissionStats,
)

Completeness = Literal["clean", "truncated", "cut_off", "partial_agent"]


def completeness(events: list[Event]) -> Completeness:
    """How the file ended.

    Lines of a type this reader does not know are ignored when looking for the ending, so a
    later release's trailing line does not turn a clean file into a cut-off one. A file with
    only the recorder's own lines and a stop line comes from an agent Flockdeck has no hooks
    for; one with only a start line was simply cut off.
    """
    known = [e for e in events if e.type in KNOWN_TYPES]
    if not known:
        return "cut_off"
    last = known[-1].type
    if last == "recording_truncated":
        return "truncated"
    if last != "recording_stopped":
        return "cut_off"
    if all(e.type in RECORDER_TYPES for e in known):
        return "partial_agent"
    return "clean"


class _PendingPrompts:
    """Permission prompts still waiting for an outcome, matched in O(1) amortised.

    An outcome answers the oldest pending prompt with its toolUseId, else (for a prompt that
    carried none) the oldest with its tool name, else the oldest at all. Entries are dropped
    lazily from the queues that did not find them.
    """

    def __init__(self) -> None:
        self._alive: list[bool] = []
        self._all: deque[int] = deque()
        self._by_id: dict[str, deque[int]] = {}
        self._by_tool: dict[str, deque[int]] = {}
        self._idless_by_tool: dict[str, deque[int]] = {}
        self.count = 0

    def add(self, prompt: Event) -> None:
        i = len(self._alive)
        self._alive.append(True)
        self.count += 1
        tool = prompt.tool or ""
        self._all.append(i)
        self._by_tool.setdefault(tool, deque()).append(i)
        if prompt.tool_use_id:
            self._by_id.setdefault(prompt.tool_use_id, deque()).append(i)
        else:
            self._idless_by_tool.setdefault(tool, deque()).append(i)

    def _pop(self, queue: deque[int] | None) -> bool:
        while queue:
            i = queue.popleft()
            if self._alive[i]:
                self._alive[i] = False
                self.count -= 1
                return True
        return False

    def resolve(self, outcome: Event) -> bool:
        tool = outcome.tool or ""
        if outcome.tool_use_id:
            if self._pop(self._by_id.get(outcome.tool_use_id)):
                return True
            if self._pop(self._idless_by_tool.get(tool)):
                return True
        elif outcome.tool:
            if self._pop(self._by_tool.get(tool)):
                return True
        elif self._pop(self._all):
            return True
        # An answer that names nothing we know still answers some prompt. auto_approved comes
        # from auto-review, which has no prompt of its own, so it never takes one.
        return outcome.outcome != "auto_approved" and self._pop(self._all)


def compute_metrics(events: list[Event]) -> Metrics:
    m = Metrics()
    perm = PermissionStats()
    mix: Counter[str] = Counter()
    call_ids: set[str] = set()
    result_ids: set[str] = set()
    idless_calls: Counter[str] = Counter()
    idless_results: Counter[str] = Counter()
    pending = _PendingPrompts()

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
            pending.add(e)
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
            pending.resolve(e)

    # A prompt that never got an outcome line (crash, or the line was lost) was not answered.
    perm.abandoned += pending.count

    m.tool_mix = dict(mix)
    m.permission = perm
    m.unpaired_calls = len(call_ids - result_ids) + sum(
        max(0, n - idless_results[tool]) for tool, n in idless_calls.items()
    )
    m.status_seconds = _status_seconds(events)
    m.models = list(dict.fromkeys(e.model for e in events if e.model))
    m.duration_seconds = round(max(0.0, (events[-1].time - events[0].time).total_seconds()), 3)
    return m


def _status_seconds(events: list[Event]) -> dict[str, float]:
    """Time in each pane status: a status lasts until the next status line, or the last line.

    This can overstate "working" (and "blocked"). Flockdeck only writes a status line when an
    agent event causes the change; a pane that goes idle on a timer, or whose process ends,
    changes status without a line, so the old status runs on until the next line that does
    appear. Treat these as upper bounds, not measurements.
    """
    end = events[-1].time
    changes = [e for e in events if e.type == "status" and e.status]
    totals: dict[str, float] = {}
    for i, e in enumerate(changes):
        until = changes[i + 1].time if i + 1 < len(changes) else end
        assert e.status is not None
        totals[e.status] = totals.get(e.status, 0.0) + max(0.0, (until - e.time).total_seconds())
    return {k: round(v, 3) for k, v in totals.items()}
