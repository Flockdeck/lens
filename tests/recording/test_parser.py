from collections.abc import Callable
from datetime import UTC

import pytest

from session_lens.recording import EmptyRecording, UnsupportedVersion, analyze, iter_events, parse
from tests.recording.conftest import make_line, to_bytes

Fx = Callable[[str], bytes]


def test_parses_documented_example_envelope(fixture: Fx) -> None:
    events = parse(fixture("claude_full.jsonl"))
    first = events[0]
    assert (first.v, first.seq, first.type, first.text) == (1, 1, "recording_started", "turned on")
    assert first.pane_name == "api" and first.project == "shop" and first.model == "opus"
    assert first.time.tzinfo is UTC and first.time.microsecond == 100000
    call = next(e for e in events if e.type == "tool_call")
    assert call.tool_use_id == "toolu_01" and call.input["command"] == "go test ./..."
    assert [e.seq for e in events] == list(range(1, len(events) + 1))


def test_nanosecond_timestamps() -> None:
    data = to_bytes(make_line(1, "recording_started", time="10:15:30.123456789"))
    assert parse(data)[0].time.microsecond == 123456


def test_unknown_types_and_fields_are_kept_and_reported(fixture: Fx) -> None:
    events = parse(fixture("unknown_types_and_fields.jsonl"))
    assert len(events) == 6
    assert events[1].type == "hologram"
    assert events[0].model_extra == {"futureField": {"a": [1, 2]}}
    analysis = analyze(events)
    assert "skipped 2 unknown event types" in analysis.warnings
    assert analysis.completeness == "clean"
    assert analysis.metrics.turns == 1


def test_wrong_version_is_refused(fixture: Fx) -> None:
    with pytest.raises(UnsupportedVersion):
        parse(fixture("wrong_version.jsonl"))


def test_wrong_version_on_first_line_is_refused() -> None:
    with pytest.raises(UnsupportedVersion):
        parse(to_bytes(make_line(1, "recording_started", v=2)))


@pytest.mark.parametrize("data", [b"", b"\n\n", b"  \n"])
def test_empty_file(data: bytes) -> None:
    with pytest.raises(EmptyRecording):
        parse(data)


def test_empty_fixture(fixture: Fx) -> None:
    with pytest.raises(EmptyRecording):
        parse(fixture("empty.jsonl"))


def test_only_garbage_is_empty() -> None:
    with pytest.raises(EmptyRecording):
        parse(b'{"v":1,"seq":1,"time":"2026')


def test_crash_cut_last_line_is_ignored(fixture: Fx) -> None:
    events = parse(fixture("cut_off_last_line.jsonl"))
    assert [e.seq for e in events] == [1, 2, 3]
    analysis = analyze(events)
    assert analysis.completeness == "cut_off"
    assert "unterminated last line" in analysis.warnings
    assert "cut off: no stop line" in analysis.warnings


def test_cut_line_in_the_middle_is_skipped_and_counted() -> None:
    data = (
        to_bytes(make_line(1, "recording_started"))
        + b'{"v":1,"seq":2,\n'
        + to_bytes(make_line(3, "recording_stopped"))
    )
    events = parse(data)
    assert [e.seq for e in events] == [1, 3]
    warnings = analyze(events).warnings
    assert "skipped 1 malformed lines" in warnings
    assert "unterminated last line" not in warnings


def test_line_missing_envelope_field_is_skipped() -> None:
    bad = make_line(2, "user_prompt")
    del bad["pane"]
    events = parse(to_bytes(make_line(1, "recording_started"), bad, make_line(3, "user_prompt")))
    assert [e.seq for e in events] == [1, 3]


def test_crlf_bom_and_final_line_without_newline() -> None:
    raw = to_bytes(make_line(1, "recording_started"), make_line(2, "recording_stopped"))
    data = b"\xef\xbb\xbf" + raw.replace(b"\n", b"\r\n").rstrip()
    assert [e.seq for e in parse(data)] == [1, 2]


def test_invalid_utf8_only_damages_its_line() -> None:
    data = to_bytes(make_line(1, "user_prompt", text="ok")) + b'{"seq":\xff\xfe\n'
    assert [e.seq for e in parse(data)] == [1]


def test_truncated_recording(fixture: Fx) -> None:
    analysis = analyze(parse(fixture("truncated.jsonl")))
    assert analysis.completeness == "truncated"
    assert "recording truncated at the size cap" in analysis.warnings


def test_clean_recording_has_no_completeness_warnings(fixture: Fx) -> None:
    analysis = analyze(parse(fixture("claude_full.jsonl")))
    assert analysis.completeness == "clean"
    assert not any("cut off" in w or "truncated" in w for w in analysis.warnings)


def test_start_stop_only_agent(fixture: Fx) -> None:
    analysis = analyze(parse(fixture("start_stop_only.jsonl")))
    assert analysis.completeness == "partial_agent"
    assert analysis.agent == "codex" and analysis.model is None and analysis.project == "shop"
    assert analysis.metrics.tool_calls == 0 and analysis.metrics.turns == 0
    assert analysis.metrics.duration_seconds == 1799.9
    assert analysis.digest.user_prompts == []
    assert analysis.risky_actions == [] and analysis.files_touched.commands == []


def test_analysis_identity_fields(fixture: Fx) -> None:
    a = analyze(parse(fixture("claude_full.jsonl")))
    assert a.recording_session == "20261001T101530Z-0123abcd"
    assert (a.project, a.agent, a.model) == ("shop", "claude", "opus")
    assert a.pane == "0123abcd-5e6f-4a7b-8c9d-0e1f2a3b4c5d"
    assert a.started_at and a.ended_at and a.started_at < a.ended_at


def test_seq_gap_warning() -> None:
    data = to_bytes(make_line(1, "recording_started"), make_line(4, "recording_stopped"))
    assert "2 lines missing from the sequence" in analyze(parse(data)).warnings


def test_warnings_never_contain_recording_content(fixture: Fx) -> None:
    for name in ("claude_full.jsonl", "cut_off_last_line.jsonl", "unknown_types_and_fields.jsonl"):
        text = " ".join(analyze(parse(fixture(name))).warnings)
        for secret in ("go test", "hello", "fix the build", "hologram", "rm -rf"):
            assert secret not in text


def test_iter_events_pages_by_seq(fixture: Fx) -> None:
    data = fixture("claude_full.jsonl")
    page = iter_events(data, after_seq=0, limit=5)
    assert [e.seq for e in page] == [1, 2, 3, 4, 5]
    nxt = iter_events(data, after_seq=page[-1].seq, limit=3)
    assert [e.seq for e in nxt] == [6, 7, 8]
    assert iter_events(data, after_seq=10_000) == []


def test_iter_events_keeps_unknown_types(fixture: Fx) -> None:
    assert "hologram" in [e.type for e in iter_events(fixture("unknown_types_and_fields.jsonl"))]


def test_analyze_empty_list() -> None:
    with pytest.raises(EmptyRecording):
        analyze([])
