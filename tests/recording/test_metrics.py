from collections.abc import Callable

from session_lens.recording import analyze, parse
from tests.recording.conftest import make_line, to_bytes

Fx = Callable[[str], bytes]


def test_full_session_metrics(fixture: Fx) -> None:
    m = analyze(parse(fixture("claude_full.jsonl"))).metrics
    assert m.duration_seconds == 932.7
    assert m.turns == 2  # the <task-notification> prompt is not a turn
    assert m.tool_calls == 9
    assert m.tool_mix == {"Bash": 4, "Read": 3, "Edit": 1, "Grep": 1}  # subagent call included
    assert m.tool_errors == 2 and m.tool_interrupted == 1
    assert m.unpaired_calls == 0
    assert m.redacted_lines == 3 and m.clipped_lines == 1


def test_permission_split_and_inferred(fixture: Fx) -> None:
    p = analyze(parse(fixture("claude_full.jsonl"))).metrics.permission
    assert (p.prompts, p.allowed, p.denied, p.auto_approved, p.abandoned) == (2, 1, 1, 1, 0)
    assert p.inferred == 2  # allowed and denied were inferred; auto_approved was reported


def test_prompt_without_outcome_counts_as_abandoned(fixture: Fx) -> None:
    p = analyze(parse(fixture("missing_tool_result.jsonl"))).metrics.permission
    assert p.prompts == 1 and p.abandoned == 1 and p.allowed == 0


def test_reported_abandoned_outcome_is_not_double_counted() -> None:
    data = to_bytes(
        make_line(1, "permission_prompt", tool="Bash", toolUseId="a"),
        make_line(2, "permission_outcome", tool="Bash", toolUseId="a", outcome="abandoned",
                  inferred=True),
        make_line(3, "permission_prompt", tool="Bash", toolUseId="b"),
        make_line(4, "permission_outcome", tool="Bash", toolUseId="b", outcome="denied"),
    )
    p = analyze(parse(data)).metrics.permission
    assert (p.prompts, p.abandoned, p.denied, p.inferred) == (2, 1, 1, 1)


def test_missing_tool_result_is_unpaired_and_warned(fixture: Fx) -> None:
    a = analyze(parse(fixture("missing_tool_result.jsonl")))
    assert a.metrics.tool_calls == 2 and a.metrics.unpaired_calls == 1
    assert "1 tool calls without a result" in a.warnings


def test_result_without_call_is_not_an_error() -> None:
    data = to_bytes(make_line(1, "tool_result", tool="Bash", toolUseId="x", output="hi"))
    assert analyze(parse(data)).metrics.unpaired_calls == 0


def test_calls_without_ids_pair_by_tool_name(fixture: Fx) -> None:
    m = analyze(parse(fixture("chat_client.jsonl"))).metrics
    assert m.tool_calls == 2 and m.unpaired_calls == 1  # read_file never answered


def test_status_seconds(fixture: Fx) -> None:
    s = analyze(parse(fixture("claude_full.jsonl"))).metrics.status_seconds
    assert s == {"working": 69.9, "blocked": 5.1, "waiting": 846.8}


def test_status_runs_to_the_last_line() -> None:
    data = to_bytes(
        make_line(1, "status", time="10:00:00", status="working"),
        make_line(2, "status", time="10:00:10", status="idle"),
        make_line(3, "recording_stopped", time="10:00:25"),
    )
    assert analyze(parse(data)).metrics.status_seconds == {"working": 10.0, "idle": 15.0}


def test_out_of_order_times_never_go_negative() -> None:
    data = to_bytes(
        make_line(1, "status", time="10:00:10", status="working"),
        make_line(2, "status", time="10:00:05", status="idle"),
    )
    m = analyze(parse(data)).metrics
    assert all(v >= 0 for v in m.status_seconds.values()) and m.duration_seconds == 0.0


def test_interrupted_without_is_error_still_counts_as_interrupted() -> None:
    data = to_bytes(make_line(1, "tool_result", tool="Bash", interrupted=True))
    m = analyze(parse(data)).metrics
    assert (m.tool_interrupted, m.tool_errors) == (1, 0)


def test_redacted_and_clipped_lines_are_reported(fixture: Fx) -> None:
    a = analyze(parse(fixture("claude_full.jsonl")))
    assert "3 lines had content redacted" in a.warnings
    assert "1 lines had content clipped" in a.warnings


def test_subagent_prompt_is_not_a_turn() -> None:
    data = to_bytes(
        make_line(1, "user_prompt", text="a"),
        make_line(2, "user_prompt", text="b", subagent="s1"),
    )
    assert analyze(parse(data)).metrics.turns == 1


def test_subagent_events_are_counted_and_paired(fixture: Fx) -> None:
    events = parse(fixture("claude_full.jsonl"))
    sub = [e for e in events if e.subagent == "agent-7"]
    assert [e.type for e in sub] == ["tool_call", "tool_result", "assistant_message"]
    assert analyze(events).metrics.tool_mix["Grep"] == 1
