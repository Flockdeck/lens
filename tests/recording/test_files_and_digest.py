from collections.abc import Callable

from lens.recording import analyze, parse
from lens.recording.digest import (
    FAILURE_CHARS,
    MAX_FAILURES,
    MAX_PROMPTS,
    PROMPT_CHARS,
)
from tests.recording.conftest import make_line, to_bytes

Fx = Callable[[str], bytes]


def test_files_touched(fixture: Fx) -> None:
    f = analyze(parse(fixture("claude_full.jsonl"))).files_touched
    assert f.read == ["api/handler.go", "/home/u/.env"]  # missing.go failed, so it is left out
    assert f.edited == ["api/handler.go"]
    assert f.commands[:3] == ["go test ./...", "rm -rf build", "git push --force origin main"]


def test_files_are_distinct_and_cover_edit_tools() -> None:
    data = to_bytes(
        make_line(1, "tool_call", tool="Read", input={"file_path": "a"}),
        make_line(2, "tool_call", tool="Read", input={"file_path": "a"}),
        make_line(3, "tool_call", tool="Write", input={"file_path": "b"}),
        make_line(4, "tool_call", tool="MultiEdit", input={"file_path": "c"}),
        make_line(5, "tool_call", tool="NotebookEdit", input={"notebook_path": "n.ipynb"}),
        make_line(6, "tool_call", tool="Grep", input={"path": "src"}),
    )
    f = analyze(parse(data)).files_touched
    assert f.read == ["a"] and f.edited == ["b", "c", "n.ipynb"]


def test_digest_holds_prompts_final_message_and_failures(fixture: Fx) -> None:
    d = analyze(parse(fixture("claude_full.jsonl"))).digest
    assert d.user_prompts[0].text == "run the tests and fix what fails"
    assert [m.text for m in d.final_messages] == ["All 212 tests pass."]  # subagent's is excluded
    assert [(f.tool, f.interrupted) for f in d.failing_results] == [
        ("Bash", False),
        ("Read", False),
        ("Bash", True),
    ]
    assert (d.project, d.agent, d.model, d.completeness) == ("shop", "claude", "opus", "clean")
    assert d.metrics.tool_calls == 9
    assert d.risky_actions[0].severity == "high"  # most severe first
    assert d.files_edited == ["api/handler.go"] and d.commands_count == 4


def test_digest_flags_clipped_and_redacted_messages() -> None:
    data = to_bytes(
        make_line(
            1, "user_prompt", text="long…[clipped 99 bytes]", clipped={"text": 200}, redacted=True
        ),
    )
    m = analyze(parse(data)).digest.user_prompts[0]
    assert m.clipped and m.redacted


def test_digest_is_bounded_whatever_the_session_size() -> None:
    lines = []
    for i in range(500):
        lines.append(make_line(3 * i + 1, "user_prompt", text=f"p{i} " + "x" * 5000))
        lines.append(
            make_line(3 * i + 2, "tool_result", tool="Bash", isError=True, output="e" * 5000)
        )
        lines.append(make_line(3 * i + 3, "assistant_message", text="m" * 40000))
    d = analyze(parse(to_bytes(*lines))).digest
    assert len(d.user_prompts) == MAX_PROMPTS and d.omitted_prompts == 500 - MAX_PROMPTS
    assert d.user_prompts[0].text.startswith("p0 ") and d.user_prompts[-1].text.startswith("p499 ")
    assert all(len(m.text) < PROMPT_CHARS + 50 for m in d.user_prompts)
    assert len(d.failing_results) == MAX_FAILURES and d.omitted_failures == 500 - MAX_FAILURES
    assert all(len(f.output) < FAILURE_CHARS + 50 for f in d.failing_results)
    assert len(d.model_dump_json()) < 60_000


def test_digest_for_start_stop_only_agent(fixture: Fx) -> None:
    d = analyze(parse(fixture("start_stop_only.jsonl"))).digest
    assert d.completeness == "partial_agent" and d.final_messages == [] and d.failing_results == []
