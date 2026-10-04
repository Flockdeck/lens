import time
from collections.abc import Callable

import pytest

from lens.recording import (
    Event,
    UnsupportedVersion,
    analyze,
    analyze_lines,
    parse,
    parse_lines,
)
from lens.recording.files import MAX_ITEMS
from lens.recording.metrics import compute_metrics
from lens.recording.risk import risks_for_call, secret_file_severity
from tests.recording.conftest import make_line, to_bytes

Fx = Callable[[str], bytes]


def bash(command: str) -> list[tuple[str, str]]:
    e = Event.model_validate(make_line(1, "tool_call", tool="Bash", input={"command": command}))
    return [(rule, sev) for rule, sev, _ in risks_for_call(e)]


# 1. UnsupportedVersion never echoes recording content


@pytest.mark.parametrize("bad", ["x" * 10_000, ["secret"] * 1000, {"k": "secret"}, True])
def test_version_message_has_no_content(bad: object) -> None:
    line = {**make_line(1, "user_prompt"), "v": bad}
    with pytest.raises(UnsupportedVersion) as exc:
        parse(to_bytes(line))
    assert "xxx" not in str(exc.value) and "secret" not in str(exc.value)
    assert len(str(exc.value)) < 100


def test_version_message_reports_an_int_capped() -> None:
    with pytest.raises(UnsupportedVersion, match="version 2 is not"):
        parse(to_bytes({**make_line(1, "user_prompt"), "v": 2}))
    with pytest.raises(UnsupportedVersion) as exc:
        parse(to_bytes({**make_line(1, "user_prompt"), "v": 10**3000}))
    assert len(str(exc.value)) < 100


# 2. pathological lines are malformed lines, not a failed file


def test_deeply_nested_line_is_malformed_not_fatal() -> None:
    lines = [
        to_bytes(make_line(1, "recording_started")).decode().strip(),
        "[" * 200_000,
        to_bytes(make_line(3, "recording_stopped")).decode().strip(),
    ]
    events = parse_lines(lines)
    assert [e.seq for e in events] == [1, 3]
    assert events.warnings == ["skipped 1 malformed lines"]


def test_deeply_nested_last_line_counts_as_cut_off_line() -> None:
    good = to_bytes(make_line(1, "recording_started")).decode().strip()
    events = parse_lines([good, "[" * 200_000])
    assert events.warnings == ["unterminated last line"]


def test_oversized_integer_line_is_malformed() -> None:
    good = to_bytes(make_line(1, "recording_started")).decode().strip()
    events = parse_lines([good, '{"v":1,"seq":' + "9" * 6000 + "}", good])
    assert len(events) == 2 and events.warnings == ["skipped 1 malformed lines"]


# 3. risk false positives


@pytest.mark.parametrize(
    "command",
    [
        "grep id_field models.py",
        "git config credential.helper store",
        "git commit -m 'drop table users'",
        "echo 'DROP TABLE users'",
        "git commit -m 'mkfs and DELETE FROM users;'",
        "dd if=/dev/zero of=/dev/null bs=1M count=1",
        "git log --grep='terraform destroy'",
    ],
)
def test_false_positives_are_not_flagged(command: str) -> None:
    assert bash(command) == []


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ('psql -c "DROP TABLE users"', ("destructive_sql", "high")),
        ('echo "DROP TABLE users" | psql shop', ("destructive_sql", "high")),
        ('docker exec db mysql -e "TRUNCATE TABLE t"', ("destructive_sql", "high")),
        ("dd if=a.img of=/dev/sdb", ("disk_write", "high")),
        ("sudo mkfs.ext4 /dev/sdb1", ("disk_write", "high")),
        ("cat ./keys/id_rsa", ("secret_file", "high")),
        ("cat id_ed25519", ("secret_file", "high")),
        ("cat config/credentials.json", ("secret_file", "high")),
        ("cat credentials.json", ("secret_file", "high")),
    ],
)
def test_real_statements_and_paths_still_flagged(command: str, expected: tuple[str, str]) -> None:
    assert expected in bash(command)


def test_name_checks_are_strict_for_bare_words_only() -> None:
    assert secret_file_severity("id_field", pathlike=False) is None
    assert secret_file_severity("credential.helper", pathlike=False) is None
    assert secret_file_severity("src/id_field.py", pathlike=True) == "high"  # path fields: full


# 4. risk false negatives


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("rm -rf ./*", ("rm_rf", "high")),
        ("rm -rf ~/*", ("rm_rf", "high")),
        ("rm -rf /*", ("rm_rf", "high")),
        ("rm -rf $HOME/*", ("rm_rf", "high")),
        ("git push origin :main", ("git_push_delete", "high")),
        ("git push origin :feature/x", ("git_push_delete", "medium")),
        ("git push --delete origin master", ("git_push_delete", "high")),
        ("git push -d origin old-branch", ("git_push_delete", "medium")),
        ("make build && sudo make install", ("sudo", "low")),
        ("ls; sudo reboot", ("sudo", "low")),
        ("cat x | sudo tee /etc/y", ("sudo", "low")),
        ("sudo -u root rm -rf /", ("rm_rf", "high")),
    ],
)
def test_false_negatives_are_flagged(command: str, expected: tuple[str, str]) -> None:
    assert expected in bash(command)


def test_ordinary_push_is_not_a_delete() -> None:
    assert bash("git push -u origin feature") == []
    assert bash("rm -rf ./build") == [("rm_rf", "medium")]


# 5. permission matching


def test_unmatched_outcome_does_not_leave_its_prompt_abandoned() -> None:
    data = to_bytes(
        make_line(1, "permission_prompt", tool="Bash", toolUseId="a"),
        make_line(2, "permission_outcome", tool="Read", toolUseId="zzz", outcome="denied"),
    )
    p = analyze(parse(data)).metrics.permission
    assert (p.prompts, p.denied, p.abandoned) == (1, 1, 0)


def test_auto_approved_outcome_never_consumes_a_prompt() -> None:
    data = to_bytes(
        make_line(1, "permission_prompt", tool="Bash", toolUseId="a"),
        make_line(2, "permission_outcome", tool="Read", outcome="auto_approved"),
    )
    p = analyze(parse(data)).metrics.permission
    assert (p.auto_approved, p.abandoned) == (1, 1)


def test_outcome_matches_by_id_then_by_tool_in_order() -> None:
    data = to_bytes(
        make_line(1, "permission_prompt", tool="Bash", toolUseId="a"),
        make_line(2, "permission_prompt", tool="Bash", toolUseId="b"),
        make_line(3, "permission_prompt", tool="Read"),
        make_line(4, "permission_outcome", tool="Bash", toolUseId="b", outcome="allowed"),
        make_line(5, "permission_outcome", tool="Read", toolUseId="new", outcome="denied"),
        make_line(6, "permission_outcome", tool="Bash", outcome="allowed"),
    )
    p = analyze(parse(data)).metrics.permission
    assert (p.prompts, p.allowed, p.denied, p.abandoned) == (3, 2, 1, 0)


def test_permission_matching_is_fast_on_a_pathological_file() -> None:
    n = 30_000
    lines = [
        make_line(i + 1, "permission_prompt", tool="Bash", toolUseId=f"t{i}") for i in range(n)
    ]
    # answered in reverse, so a front-first scan of the pending list would be quadratic
    lines += [
        make_line(
            n + 1 + j,
            "permission_outcome",
            tool="Bash",
            toolUseId=f"t{n - 1 - j}",
            outcome="allowed",
        )
        for j in range(n)
    ]
    # and a pile of outcomes that match nothing
    lines += [
        make_line(2 * n + 1 + j, "permission_outcome", tool="X", outcome="auto_approved")
        for j in range(n)
    ]
    events = parse(to_bytes(*lines))
    start = time.perf_counter()
    p = compute_metrics(events).permission
    assert time.perf_counter() - start < 2.0
    assert (p.prompts, p.allowed, p.abandoned) == (n, n, 0)


# 6. files and digest totals


def test_totals_are_counted_before_the_cap_and_latest_commands_are_kept() -> None:
    n = MAX_ITEMS + 100
    lines = [
        make_line(i + 1, "tool_call", tool="Bash", input={"command": f"echo {i}"}) for i in range(n)
    ]
    lines += [
        make_line(n + i + 1, "tool_call", tool="Read", input={"file_path": f"f{i}"})
        for i in range(n)
    ]
    a = analyze(parse(to_bytes(*lines)))
    f = a.files_touched
    assert len(f.commands) == MAX_ITEMS and f.commands[-1] == f"echo {n - 1}"
    assert f.commands[0] == "echo 100"
    assert len(f.read) == MAX_ITEMS and f.read[-1] == f"f{n - 1}"
    assert (f.commands_total, f.read_total) == (n, n)
    assert (a.digest.commands_count, a.digest.files_read_count) == (n, n)
    assert any("latest" in w for w in a.warnings)


def test_small_session_totals_equal_list_lengths(fixture: Fx) -> None:
    a = analyze(parse(fixture("claude_full.jsonl")))
    assert a.files_touched.read_total == len(a.files_touched.read) == 2
    assert not any("latest" in w for w in a.warnings)


# 7. warnings travel with the events, or explicitly


def test_event_list_warnings_survive_analyze_but_not_copies(fixture: Fx) -> None:
    events = parse(fixture("cut_off_last_line.jsonl"))
    assert "unterminated last line" in analyze(events).warnings
    assert "unterminated last line" not in analyze(list(events)).warnings  # plain copy: none
    assert "unterminated last line" not in analyze(events[:]).warnings  # slice: plain list


def test_warnings_can_be_passed_explicitly(fixture: Fx) -> None:
    events = parse(fixture("cut_off_last_line.jsonl"))
    a = analyze(list(events), parse_warnings=events.warnings)
    assert "unterminated last line" in a.warnings
    assert analyze(events, parse_warnings=[]).warnings.count("unterminated last line") == 0


def test_analyze_lines_keeps_parse_warnings(fixture: Fx) -> None:
    lines = fixture("cut_off_last_line.jsonl").decode().split("\n")
    assert "unterminated last line" in analyze_lines(lines).warnings


# 8. completeness


def test_lone_recording_started_is_cut_off_not_partial_agent() -> None:
    a = analyze(parse(to_bytes(make_line(1, "recording_started", text="turned on"))))
    assert a.completeness == "cut_off"


def test_unknown_trailing_line_does_not_hide_a_clean_stop() -> None:
    data = to_bytes(
        make_line(1, "recording_started"),
        make_line(2, "user_prompt", text="x"),
        make_line(3, "recording_stopped"),
        make_line(4, "future_trailer"),
    )
    assert analyze(parse(data)).completeness == "clean"


def test_unknown_trailing_line_does_not_hide_truncation() -> None:
    data = to_bytes(
        make_line(1, "recording_started"),
        make_line(2, "user_prompt", text="x"),
        make_line(3, "recording_truncated"),
        make_line(4, "future_trailer"),
    )
    assert analyze(parse(data)).completeness == "truncated"


def test_only_unknown_types_is_cut_off() -> None:
    assert analyze(parse(to_bytes(make_line(1, "future_a")))).completeness == "cut_off"


def test_start_then_stop_only_is_still_partial_agent(fixture: Fx) -> None:
    assert analyze(parse(fixture("start_stop_only.jsonl"))).completeness == "partial_agent"


# 9. loose typing of non-required fields, strict time


def test_unknown_shape_of_optional_fields_keeps_the_line() -> None:
    data = to_bytes(
        make_line(1, "user_prompt", text={"parts": ["a"]}, redacted="yes", clipped=[1]),
        make_line(2, "status", status=3, previous=["x"]),
        make_line(3, "tool_result", tool="Bash", output={"stdout": "x"}, isError="no"),
        make_line(4, "tool_call", tool={"name": "Bash"}, toolUseId=12),
        make_line(5, "future", agent=7, project=None),
    )
    events = parse(data)
    assert len(events) == 5 and events.warnings == []
    assert events[0].text is None and events[0].redacted is None and events[0].clipped is None
    assert events[1].status is None
    assert events[2].output is None and events[2].is_error is None
    a = analyze(events)
    assert a.metrics.turns == 1 and a.metrics.tool_calls == 1


def test_integer_time_is_not_coerced() -> None:
    good = make_line(1, "recording_started")
    bad = {**make_line(2, "user_prompt"), "time": 1790849730}
    events = parse(to_bytes(good, bad, make_line(3, "recording_stopped")))
    assert [e.seq for e in events] == [1, 3]
    assert events.warnings == ["skipped 1 malformed lines"]


@pytest.mark.parametrize("field", ["seq", "v"])
def test_required_ints_are_strict(field: str) -> None:
    good = make_line(1, "recording_started")
    bad = {**make_line(2, "user_prompt"), field: "2"}
    if field == "v":
        with pytest.raises(UnsupportedVersion):
            parse(to_bytes(good, bad))
    else:
        assert [e.seq for e in parse(to_bytes(good, bad))] == [1]
