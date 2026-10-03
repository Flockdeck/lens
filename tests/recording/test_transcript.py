"""Files made from the agent's stored conversation (Flockdeck 0.3.48 and later), and old ones."""

import json
from collections.abc import Callable
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from session_lens.recording import Analysis, Event, analyze, parse
from session_lens.recording.models import KNOWN_TYPES
from tests.recording.conftest import FIXTURES, make_line, to_bytes

TRANSCRIPTS = ["transcript_full.jsonl", "transcript_truncated.jsonl", "transcript_minimal.jsonl"]
CONVERSATION = "0123abcd-5e6f-4a7b-8c9d-0e1f2a3b4c5d"


@pytest.fixture
def full(fixture: Callable[[str], bytes]) -> Analysis:
    return analyze(parse(fixture("transcript_full.jsonl")))


def test_transcript_identity(full: Analysis) -> None:
    assert full.source_format == "transcript"
    assert full.recording_session == "20261001T101530Z-0123abcd"
    # `pane` is the conversation's id in a transcript, and no pane name is written
    assert full.pane == CONVERSATION
    assert full.conversation == CONVERSATION
    assert full.pane_name is None
    assert full.completeness == "clean"
    assert full.warnings == []


def test_title_is_the_last_one(full: Analysis) -> None:
    assert full.title == "Fix the handler error check"
    assert full.digest.title == "Fix the handler error check"


def test_no_title_is_none(fixture: Callable[[str], bytes]) -> None:
    a = analyze(parse(fixture("transcript_minimal.jsonl")))
    assert a.title is None and a.digest.title is None
    assert a.source_format == "transcript"


def test_metrics(full: Analysis) -> None:
    m = full.metrics
    assert m.turns == 2
    assert m.tool_calls == 6
    assert m.tool_mix == {"Bash": 3, "Read": 1, "Edit": 1, "Task": 1}
    assert m.tool_errors == 2
    assert m.unpaired_calls == 0
    assert m.compactions == 1
    assert m.models == ["claude-opus-5-5"]
    assert full.model == "claude-opus-5-5"


def test_usage_is_summed_over_every_line_that_has_it(full: Analysis) -> None:
    usage = full.metrics.usage
    assert usage is not None
    assert usage.input_tokens == 6 + 3 + 2 + 3 + 2 + 2 + 5 + 3
    assert usage.output_tokens == 40 + 55 + 80 + 60 + 30 + 12 + 25 + 9
    assert usage.cache_creation_input_tokens == 1450 + 210 + 150 + 120 + 90 + 40 + 22085 + 30
    assert (
        usage.cache_read_input_tokens == 30705 + 32155 + 32365 + 32515 + 32635 + 32725 + 0 + 22085
    )


def test_permissions_and_status_are_not_recorded_not_zero(full: Analysis) -> None:
    m = full.metrics
    assert m.permissions_recorded is False and m.status_recorded is False
    assert m.permission.prompts == 0 and m.permission.denied == 0
    assert m.status_seconds == {}


def test_a_rejected_tool_is_an_error_not_a_permission_denial(full: Analysis) -> None:
    # nothing says a dialog was shown: the refusal is only a failed tool result
    assert full.metrics.permission.denied == 0
    assert [f.tool for f in full.digest.failing_results] == ["Bash", "Bash"]
    assert [r.rule for r in full.risky_actions] == ["git_force_push"]


def test_digest_keeps_the_last_message_of_each_turn(full: Analysis) -> None:
    # not "Let me run the tests first." or the message between two tool calls
    assert [m.text for m in full.digest.final_messages] == [
        "All 212 tests pass.",
        "Understood, I have not pushed.",
    ]
    assert [m.text for m in full.digest.user_prompts] == [
        "run the tests and fix what fails",
        "push it to main",
    ]
    assert full.digest.source_format == "transcript"


def test_files_touched(full: Analysis) -> None:
    f = full.files_touched
    assert f.read == ["api/handler.go"] and f.edited == ["api/handler.go"]
    assert f.commands == ["go test ./...", "go test ./...", "git push --force origin main"]


def test_entry_fields_are_read(fixture: Callable[[str], bytes]) -> None:
    events = parse(fixture("transcript_full.jsonl"))
    prompt = next(e for e in events if e.type == "user_prompt")
    assert (prompt.git_branch, prompt.cwd, prompt.agent_version) == (
        "main",
        "/home/sam/shop",
        "2.1.286",
    )
    compacted = next(e for e in events if e.type == "conversation_compacted")
    assert (compacted.trigger, compacted.tokens_before, compacted.tokens_after) == (
        "auto",
        970192,
        22085,
    )
    stop = next(e for e in events if e.type == "assistant_message")
    assert stop.stop_reason == "tool_use" and stop.usage is not None
    # a title has no entry of its own, so none of those fields
    assert next(e for e in events if e.type == "conversation_title").cwd is None


def test_known_types_raise_no_unknown_warning(full: Analysis) -> None:
    assert not any("unknown event types" in w for w in full.warnings)


def test_truncated_transcript(fixture: Callable[[str], bytes]) -> None:
    a = analyze(parse(fixture("transcript_truncated.jsonl")))
    assert a.completeness == "truncated"
    assert "recording truncated at the size cap" in a.warnings
    assert a.metrics.clipped_lines == 1
    assert a.metrics.unpaired_calls == 1  # the Bash call at the cut has no result
    assert a.metrics.permissions_recorded is False


def test_conversation_title_without_a_title_is_ignored() -> None:
    data = to_bytes(
        make_line(1, "recording_started", text="start of the transcript"),
        make_line(2, "conversation_title", title="Real title"),
        make_line(3, "conversation_title", title={"odd": "shape"}),
        make_line(4, "conversation_title"),
        make_line(5, "recording_stopped", text="end of the transcript"),
    )
    a = analyze(parse(data))
    assert a.title == "Real title"


def test_odd_shapes_in_new_fields_read_as_absent() -> None:
    data = to_bytes(
        make_line(1, "recording_started", text="start of the transcript"),
        make_line(
            2,
            "assistant_message",
            text="hi",
            usage={"inputTokens": 1, "outputTokens": "many"},
            stopReason=7,
            gitBranch=["main"],
            cwd=3,
            agentVersion=None,
        ),
        make_line(3, "conversation_compacted", tokensBefore="lots", tokensAfter=True, trigger={}),
        make_line(4, "conversation_title", title="t", futureField=[1]),
        make_line(5, "recording_stopped", text="end of the transcript"),
    )
    events = parse(data)
    msg, compacted = events[1], events[2]
    assert msg.usage is None and msg.stop_reason is None
    assert msg.git_branch is None and msg.cwd is None and msg.agent_version is None
    assert compacted.tokens_before is None and compacted.tokens_after is None
    assert compacted.trigger is None
    a = analyze(events)
    assert a.metrics.usage is None and a.metrics.compactions == 1 and a.title == "t"


def test_usage_with_a_negative_count_is_kept_non_negative() -> None:
    usage = {
        "inputTokens": -1,
        "outputTokens": 2,
        "cacheCreationInputTokens": 0,
        "cacheReadInputTokens": 0,
    }
    events = parse(to_bytes(make_line(1, "assistant_message", text="x", usage=usage)))
    assert events[0].usage is not None and events[0].usage.input_tokens == 0


def test_subagent_lines_stay_out_of_turns_and_final_messages() -> None:
    # a transcript of Claude Code has none, the schema allows them, and old files have them
    data = to_bytes(
        make_line(1, "recording_started", text="start of the transcript"),
        make_line(2, "user_prompt", text="look into it"),
        make_line(3, "user_prompt", text="subagent brief", subagent="agent-7"),
        make_line(4, "assistant_message", text="Found one.", subagent="agent-7"),
        make_line(5, "assistant_message", text="Done."),
        make_line(6, "recording_stopped", text="end of the transcript"),
    )
    a = analyze(parse(data))
    assert a.metrics.turns == 1
    assert [m.text for m in a.digest.final_messages] == ["Done."]
    assert [m.text for m in a.digest.user_prompts] == ["look into it"]


@pytest.mark.parametrize(
    "text",
    [
        "<system-reminder>be careful</system-reminder>",
        "<task-notification>build finished</task-notification>",
        "<command-name>/clear</command-name>",
        "[Request interrupted by user]",
        "This session is being continued from a previous conversation that ran out of context.",
    ],
)
def test_the_agents_own_prompts_are_not_turns(text: str) -> None:
    # files from hooks hold these as prompts; a transcript leaves them out
    data = to_bytes(
        make_line(1, "recording_started", text="turned on"),
        make_line(2, "user_prompt", text="do the thing"),
        make_line(3, "assistant_message", text="first answer"),
        make_line(4, "user_prompt", text=text),
        make_line(5, "assistant_message", text="second answer"),
        make_line(6, "recording_stopped", text="turned off"),
    )
    a = analyze(parse(data))
    assert a.metrics.turns == 1
    assert [m.text for m in a.digest.user_prompts] == ["do the thing"]
    assert [m.text for m in a.digest.final_messages] == ["second answer"]


# Files from hooks (Flockdeck 0.3.47) keep working.


def test_hook_file_is_labelled_and_records_permissions(fixture: Callable[[str], bytes]) -> None:
    a = analyze(parse(fixture("claude_full.jsonl")))
    assert a.source_format == "hooks"
    assert a.title is None and a.metrics.usage is None and a.metrics.compactions == 0
    assert a.metrics.permissions_recorded is True and a.metrics.status_recorded is True
    assert a.metrics.permission.prompts == 2 and a.metrics.permission.denied == 1
    assert a.metrics.status_seconds
    assert a.pane == "0123abcd-5e6f-4a7b-8c9d-0e1f2a3b4c5d" and a.pane_name == "api"
    assert a.conversation == "c1"


def test_hook_file_without_permission_lines_says_so(fixture: Callable[[str], bytes]) -> None:
    a = analyze(parse(fixture("chat_client.jsonl")))
    assert a.source_format == "hooks"
    assert a.metrics.permissions_recorded is False and a.metrics.status_recorded is False


def test_agent_with_start_and_stop_only(fixture: Callable[[str], bytes]) -> None:
    a = analyze(parse(fixture("start_stop_only.jsonl")))
    assert a.source_format == "hooks" and a.completeness == "partial_agent"


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        ([make_line(1, "recording_started", text="start of the transcript")], "transcript"),
        ([make_line(1, "recording_started", text="turned on")], "hooks"),
        ([make_line(1, "recording_started", text="resumed")], "hooks"),
        # no start line (a page from the middle): a line only one kind has decides
        ([make_line(7, "status", status="working")], "hooks"),
        ([make_line(7, "user_prompt", text="x", paneName="api")], "hooks"),
        ([make_line(7, "conversation_title", title="t")], "transcript"),
        ([make_line(7, "user_prompt", text="x", cwd="/w")], "transcript"),
        # the first line wins over a stray marker, and nothing decides a bare file
        (
            [
                make_line(1, "recording_started", text="start of the transcript"),
                make_line(2, "status", status="working"),
            ],
            "transcript",
        ),
        ([make_line(7, "user_prompt", text="x")], None),
        ([make_line(1, "recording_started", text="something later")], None),
    ],
)
def test_source_format_detection(lines: list[dict[str, Any]], expected: str | None) -> None:
    assert analyze(parse(to_bytes(*lines))).source_format == expected


def test_mixed_old_and_new_lines_in_one_file_do_not_fail() -> None:
    data = to_bytes(
        make_line(1, "recording_started", text="start of the transcript"),
        make_line(2, "permission_prompt", tool="Bash"),
        make_line(3, "permission_outcome", outcome="denied"),
        make_line(4, "recording_stopped", text="end of the transcript"),
    )
    a = analyze(parse(data))
    assert a.metrics.permissions_recorded is True and a.metrics.permission.denied == 1


# The schema Flockdeck publishes, copied to tests/fixtures.

SCHEMA = json.loads((FIXTURES / "recording-line.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=Draft202012Validator.FORMAT_CHECKER)


@pytest.mark.parametrize("name", TRANSCRIPTS)
def test_every_line_of_a_transcript_fixture_validates(name: str) -> None:
    lines = (FIXTURES / name).read_text(encoding="utf-8").splitlines()
    assert lines
    for number, raw in enumerate(lines, start=1):
        errors = [e.message for e in VALIDATOR.iter_errors(json.loads(raw))]
        assert not errors, f"{name} line {number}: {errors}"
        assert json.loads(raw)["seq"] == number


@pytest.mark.parametrize("name", TRANSCRIPTS)
def test_transcript_fixtures_have_no_hook_only_lines(name: str) -> None:
    for e in parse((FIXTURES / name).read_bytes()):
        assert e.type not in {"session", "permission_prompt", "permission_outcome", "status"}
        assert e.pane_name is None


def test_the_schema_catches_a_bad_line() -> None:
    bad = {"v": 1, "seq": 1, "time": "2026-10-01", "session": "s", "pane": "p", "type": "tool_call"}
    assert len(list(VALIDATOR.iter_errors(bad))) == 2  # time shape, and no `tool`


def test_every_event_type_in_the_schema_is_known_to_the_parser() -> None:
    assert set(SCHEMA["properties"]["type"]["enum"]) == KNOWN_TYPES


def test_every_schema_field_is_read_by_the_parser() -> None:
    read = {f.alias or name for name, f in Event.model_fields.items()}
    assert set(SCHEMA["properties"]) <= read
