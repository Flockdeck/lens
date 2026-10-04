"""Generates the recording fixtures from the examples in Flockdeck's docs/recording-format.md.

Run `python tests/fixtures/build.py` to rewrite the .jsonl files next to this script. A test
checks the committed files match, so edit this script, not the files.
"""

import json
import sys
from pathlib import Path

SESSION = "20261001T101530Z-0123abcd"
PANE = "0123abcd-5e6f-4a7b-8c9d-0e1f2a3b4c5d"
HERE = Path(__file__).parent


class Recording:
    """Builds lines with the envelope from the format reference's examples."""

    def __init__(self, agent: str | None = "claude", model: str | None = "opus") -> None:
        self.agent, self.model = agent, model
        self.lines: list[str] = []
        self.seq = 0

    def add(
        self, time: str, type_: str, *, envelope: dict[str, object] | None = None, **fields: object
    ) -> "Recording":
        self.seq += 1
        line: dict[str, object] = {
            "v": 1,
            "seq": self.seq,
            "time": f"2026-10-01T{time}Z",
            "session": SESSION,
            "pane": PANE,
            "paneName": "api",
            "project": "shop",
        }
        if self.agent:
            line["agent"] = self.agent
        if self.model:
            line["model"] = self.model
        line["type"] = type_
        line.update(envelope or {})
        line.update(fields)
        self.lines.append(json.dumps(line, ensure_ascii=False, separators=(",", ":")))
        return self

    def data(self, trailing: bytes = b"") -> bytes:
        return ("\n".join(self.lines) + "\n").encode("utf-8") + trailing


def claude_full() -> bytes:
    """A complete Claude Code session touching every event type and tolerance feature."""
    r = Recording()
    r.add("10:15:30.1", "recording_started", text="turned on")
    r.add("10:15:31.0", "session", source="startup", text="start", envelope={"conversation": "c1"})
    r.add("10:15:40.2", "user_prompt", text="run the tests and fix what fails")
    r.add("10:15:41.0", "status", status="working", previous="waiting", detail="Bash")
    r.add(
        "10:15:42.0",
        "tool_call",
        tool="Bash",
        toolUseId="toolu_01",
        input={"command": "go test ./...", "description": "Run the tests"},
    )
    r.add(
        "10:15:58.4",
        "tool_result",
        tool="Bash",
        toolUseId="toolu_01",
        output="FAIL\tshop/api\t0.412s",
        isError=True,
    )
    r.add(
        "10:16:00.0",
        "tool_call",
        tool="Read",
        toolUseId="toolu_02",
        input={"file_path": "api/handler.go"},
    )
    r.add("10:16:00.5", "tool_result", tool="Read", toolUseId="toolu_02", output="package api")
    r.add(
        "10:16:05.0",
        "tool_call",
        tool="Edit",
        toolUseId="toolu_03",
        input={"file_path": "api/handler.go", "old_string": "a", "new_string": "b"},
    )
    r.add("10:16:05.4", "tool_result", tool="Edit", toolUseId="toolu_03", output="edited")
    r.add(
        "10:16:10.0",
        "tool_call",
        tool="Read",
        toolUseId="toolu_04",
        input={"file_path": "missing.go"},
    )
    r.add(
        "10:16:10.2",
        "tool_result",
        tool="Read",
        toolUseId="toolu_04",
        output="no such file",
        isError=True,
    )
    r.add("10:16:15.0", "status", status="blocked", previous="working", detail="Bash")
    r.add(
        "10:16:16.0",
        "permission_prompt",
        tool="Bash",
        toolUseId="toolu_05",
        input={"command": "rm -rf build"},
    )
    r.add(
        "10:16:20.0",
        "permission_outcome",
        tool="Bash",
        toolUseId="toolu_05",
        outcome="allowed",
        inferred=True,
    )
    r.add("10:16:20.1", "status", status="working", previous="blocked", detail="Bash")
    r.add(
        "10:16:20.5",
        "tool_call",
        tool="Bash",
        toolUseId="toolu_05",
        input={"command": "rm -rf build"},
    )
    r.add("10:16:21.0", "tool_result", tool="Bash", toolUseId="toolu_05", output="")
    r.add(
        "10:16:22.0",
        "permission_prompt",
        tool="Bash",
        toolUseId="toolu_06",
        input={"command": "git push --force origin main"},
    )
    r.add(
        "10:16:25.0",
        "permission_outcome",
        tool="Bash",
        toolUseId="toolu_06",
        outcome="denied",
        inferred=True,
    )
    r.add(
        "10:16:26.0",
        "permission_outcome",
        tool="Bash",
        outcome="auto_approved",
        reason="read-only command",
    )
    r.add(
        "10:16:27.0",
        "tool_call",
        tool="Bash",
        toolUseId="toolu_07",
        input={"command": "git push --force origin main"},
    )
    r.add(
        "10:16:28.0",
        "tool_result",
        tool="Bash",
        toolUseId="toolu_07",
        output="stopped by user",
        isError=True,
        interrupted=True,
    )
    r.add(
        "10:16:30.0",
        "tool_call",
        tool="Read",
        toolUseId="toolu_08",
        input={"file_path": "/home/u/.env"},
        redacted=True,
    )
    r.add(
        "10:16:30.2",
        "tool_result",
        tool="Read",
        toolUseId="toolu_08",
        output="[withheld: a secret file]",
        redacted=True,
    )
    r.add(
        "10:16:31.0",
        "tool_call",
        tool="Bash",
        toolUseId="toolu_09",
        input={"command": "curl -H 'Authorization: Bearer [redacted]' https://x.test"},
        redacted=True,
    )
    r.add(
        "10:16:32.0",
        "tool_result",
        tool="Bash",
        toolUseId="toolu_09",
        output="x" * 20 + "…[clipped 16384 bytes]",
        clipped={"output": 24576},
    )
    r.add(
        "10:16:40.0",
        "tool_call",
        tool="Grep",
        toolUseId="toolu_sub1",
        envelope={"subagent": "agent-7"},
        input={"pattern": "TODO"},
    )
    r.add(
        "10:16:41.0",
        "tool_result",
        tool="Grep",
        toolUseId="toolu_sub1",
        envelope={"subagent": "agent-7"},
        output="handler.go:12",
    )
    r.add(
        "10:16:42.0", "assistant_message", text="Found one TODO.", envelope={"subagent": "agent-7"}
    )
    r.add("10:16:50.0", "user_prompt", text="<task-notification>build finished</task-notification>")
    r.add("10:16:55.0", "user_prompt", text="now run them again")
    r.add("10:16:55.9", "assistant_message", text="All 212 tests pass.")
    r.add("10:16:56.0", "status", status="waiting", previous="working")
    r.add("10:31:02.0", "session", text="end")
    r.add("10:31:02.8", "recording_stopped", text="turned off")
    return r.data()


def truncated() -> bytes:
    r = Recording()
    r.add("10:15:30.1", "recording_started", text="turned on")
    r.add("10:15:40.2", "user_prompt", text="refactor the parser")
    r.add(
        "10:15:42.0",
        "tool_call",
        tool="Read",
        toolUseId="toolu_01",
        input={"file_path": "parser.go"},
    )
    r.add("10:15:42.3", "tool_result", tool="Read", toolUseId="toolu_01", output="package p")
    r.add(
        "11:02:44.0",
        "recording_truncated",
        text="the recording reached its size cap of 16 MiB and ended here",
    )
    return r.data()


def cut_off_last_line() -> bytes:
    """No stop line, and a last line cut mid-object by a crash."""
    r = Recording()
    r.add("10:15:30.1", "recording_started", text="turned on")
    r.add("10:15:40.2", "user_prompt", text="fix the build")
    r.add("10:15:42.0", "tool_call", tool="Bash", toolUseId="toolu_01", input={"command": "make"})
    return r.data(trailing=b'{"v":1,"seq":4,"time":"2026-10-01T10:15:50.0Z","session":"20261001T')


def unknown_types_and_fields() -> bytes:
    r = Recording()
    r.add("10:15:30.1", "recording_started", text="turned on", futureField={"a": [1, 2]})
    r.add("10:15:31.0", "hologram", text="a type from a later release", shape="cube")
    r.add("10:15:40.2", "user_prompt", text="hello", sentiment="calm")
    r.add("10:15:41.0", "assistant_message", text="hi", extraEnvelope=True)
    r.add("10:15:42.0", "another_future_type")
    r.add("10:15:43.0", "recording_stopped", text="turned off")
    return r.data()


def wrong_version() -> bytes:
    r = Recording()
    r.add("10:15:30.1", "recording_started", text="turned on")
    r.add("10:15:40.2", "user_prompt", text="hello", envelope={"v": 2})
    return r.data()


def missing_tool_result() -> bytes:
    r = Recording()
    r.add("10:15:30.1", "recording_started", text="turned on")
    r.add("10:15:40.2", "user_prompt", text="deploy it")
    r.add("10:15:42.0", "tool_call", tool="Bash", toolUseId="toolu_01", input={"command": "ls"})
    r.add("10:15:43.0", "tool_call", tool="Bash", toolUseId="toolu_02", input={"command": "pwd"})
    r.add("10:15:44.0", "tool_result", tool="Bash", toolUseId="toolu_02", output="/app")
    r.add(
        "10:15:45.0",
        "permission_prompt",
        tool="Bash",
        toolUseId="toolu_03",
        input={"command": "make deploy"},
    )
    r.add("10:15:50.0", "recording_stopped", text="the pane was closed")
    return r.data()


def start_stop_only() -> bytes:
    """Codex, Gemini CLI, Aider and friends: only the recorder's own lines."""
    r = Recording(agent="codex", model=None)
    r.add("10:15:30.1", "recording_started", text="turned on")
    r.add("10:45:30.0", "recording_stopped", text="turned off")
    return r.data()


def chat_client() -> bytes:
    """Flockdeck's own chat client: tool names only, no ids, no permission or message lines."""
    r = Recording(agent="claude-api", model="sonnet")
    r.add("10:15:30.1", "recording_started", text="turned on")
    r.add("10:15:31.0", "session", source="startup", text="start")
    r.add("10:15:40.2", "user_prompt", text="what is in this repo?")
    r.add("10:15:41.0", "tool_call", tool="list_files")
    r.add("10:15:41.5", "tool_result", tool="list_files")
    r.add("10:15:42.0", "tool_call", tool="read_file")
    r.add("10:15:50.0", "recording_stopped", text="turned off")
    return r.data()


CONVERSATION = "0123abcd-5e6f-4a7b-8c9d-0e1f2a3b4c5d"
MODEL = "claude-opus-5-5"
USAGE_KEYS = ("inputTokens", "outputTokens", "cacheCreationInputTokens", "cacheReadInputTokens")
ENTRY = {"gitBranch": "main", "cwd": "/home/sam/shop", "agentVersion": "2.1.286"}


class Transcript:
    """Builds lines the way a transcript made from the agent's stored conversation has them.

    `pane` is the conversation's id and there is no `paneName`. `model`, `gitBranch`, `cwd` and
    `agentVersion` come from the stored entry, so only the lines made from one have them (see
    `entry`, `reply`). A reply's `usage` and `stopReason` go on its first line only.
    """

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.seq = 0

    def add(self, time: str, type_: str, **fields: object) -> "Transcript":
        self.seq += 1
        line: dict[str, object] = {
            "v": 1,
            "seq": self.seq,
            "time": f"2026-10-01T{time}Z",
            "session": SESSION,
            "pane": CONVERSATION,
            "project": "shop",
            "agent": "claude",
            "conversation": CONVERSATION,
            "type": type_,
        }
        line.update(fields)
        self.lines.append(json.dumps(line, ensure_ascii=False, separators=(",", ":")))
        return self

    def entry(self, time: str, type_: str, **fields: object) -> "Transcript":
        """A line made from an entry of the stored conversation."""
        return self.add(time, type_, **ENTRY, **fields)

    def reply(
        self,
        time: str,
        type_: str,
        *,
        usage: tuple[int, int, int, int] | None = None,
        stop: str | None = None,
        **fields: object,
    ) -> "Transcript":
        """An assistant_message or tool_call: it has the turn's own model."""
        extra: dict[str, object] = {"model": MODEL}
        if usage:
            extra["usage"] = dict(zip(USAGE_KEYS, usage, strict=True))
        if stop:
            extra["stopReason"] = stop
        return self.entry(time, type_, **extra, **fields)

    def data(self) -> bytes:
        return ("\n".join(self.lines) + "\n").encode("utf-8")


def transcript_full() -> bytes:
    """A complete transcript: titles, tool calls and results, a subagent, a compaction.

    Two turns. The agent speaks mid-turn ("Let me run the tests first."), which a transcript
    records and a file from hooks does not. No permission, status or session lines.
    """
    t = Transcript()
    t.add("10:15:30.1", "recording_started", text="start of the transcript")
    t.entry("10:15:30.1", "user_prompt", text="run the tests and fix what fails")
    t.add("10:15:30.1", "conversation_title", title="Fix the failing tests")
    t.reply(
        "10:15:41.0",
        "assistant_message",
        text="Let me run the tests first.",
        usage=(6, 40, 1450, 30705),
        stop="tool_use",
    )
    t.reply(
        "10:15:42.0",
        "tool_call",
        tool="Bash",
        toolUseId="toolu_01",
        input={"command": "go test ./...", "description": "Run the tests"},
    )
    t.entry(
        "10:15:58.4",
        "tool_result",
        tool="Bash",
        toolUseId="toolu_01",
        output="FAIL\tshop/api\t0.412s",
        isError=True,
    )
    t.reply(
        "10:16:00.0",
        "tool_call",
        tool="Read",
        toolUseId="toolu_02",
        input={"file_path": "api/handler.go"},
        usage=(3, 55, 210, 32155),
        stop="tool_use",
    )
    t.entry("10:16:00.5", "tool_result", tool="Read", toolUseId="toolu_02", output="package api")
    t.reply(
        "10:16:04.0",
        "assistant_message",
        text="The handler returns before it checks the error. I will fix that.",
        usage=(2, 80, 150, 32365),
        stop="tool_use",
    )
    t.reply(
        "10:16:05.0",
        "tool_call",
        tool="Edit",
        toolUseId="toolu_03",
        input={"file_path": "api/handler.go", "old_string": "a", "new_string": "b"},
    )
    t.entry("10:16:05.4", "tool_result", tool="Edit", toolUseId="toolu_03", output="edited")
    t.reply(
        "10:16:10.0",
        "tool_call",
        tool="Task",
        toolUseId="toolu_04",
        input={"description": "Find TODOs", "prompt": "List the TODO comments in api/"},
        usage=(3, 60, 120, 32515),
        stop="tool_use",
    )
    t.entry(
        "10:16:42.0", "tool_result", tool="Task", toolUseId="toolu_04", output="One: handler.go:12"
    )
    t.reply(
        "10:16:45.0",
        "tool_call",
        tool="Bash",
        toolUseId="toolu_05",
        input={"command": "go test ./..."},
        usage=(2, 30, 90, 32635),
        stop="tool_use",
    )
    t.entry("10:16:50.0", "tool_result", tool="Bash", toolUseId="toolu_05", output="ok  shop/api")
    t.reply(
        "10:16:55.9",
        "assistant_message",
        text="All 212 tests pass.",
        usage=(2, 12, 40, 32725),
        stop="end_turn",
    )
    t.entry(
        "10:30:00.0",
        "conversation_compacted",
        trigger="auto",
        tokensBefore=970192,
        tokensAfter=22085,
    )
    t.add("10:30:00.0", "conversation_title", title="Fix the handler error check")
    t.entry("10:31:00.0", "user_prompt", text="push it to main")
    t.reply(
        "10:31:03.0",
        "tool_call",
        tool="Bash",
        toolUseId="toolu_06",
        input={"command": "git push --force origin main"},
        usage=(5, 25, 22085, 0),
        stop="tool_use",
    )
    t.entry(
        "10:31:30.0",
        "tool_result",
        tool="Bash",
        toolUseId="toolu_06",
        output="The user rejected this tool use.",
        isError=True,
    )
    t.reply(
        "10:31:32.0",
        "assistant_message",
        text="Understood, I have not pushed.",
        usage=(3, 9, 30, 22085),
        stop="end_turn",
    )
    t.add("10:31:32.0", "recording_stopped", text="end of the transcript")
    return t.data()


def transcript_truncated() -> bytes:
    """A conversation longer than the size cap: strings clipped, then a truncation line."""
    t = Transcript()
    t.add("10:15:30.1", "recording_started", text="start of the transcript")
    t.entry("10:15:30.1", "user_prompt", text="refactor the parser")
    t.reply(
        "10:15:42.0",
        "tool_call",
        tool="Read",
        toolUseId="toolu_01",
        input={"file_path": "parser.go"},
        usage=(4, 20, 900, 1000),
        stop="tool_use",
    )
    t.entry(
        "10:15:42.3",
        "tool_result",
        tool="Read",
        toolUseId="toolu_01",
        output="package p" + "x" * 11 + "…[clipped 16384 bytes]",
        clipped={"output": 24576},
    )
    t.reply("10:15:50.0", "tool_call", tool="Bash", toolUseId="toolu_02", input={"command": "make"})
    t.add(
        "11:02:44.0",
        "recording_truncated",
        text="the transcript reached its size cap of 16 MiB and ended here",
    )
    return t.data()


def transcript_minimal() -> bytes:
    """No title, no tools, no permission lines: one question and one answer."""
    t = Transcript()
    t.add("10:15:30.1", "recording_started", text="start of the transcript")
    t.entry("10:15:30.1", "user_prompt", text="what does the retry setting do?")
    t.reply(
        "10:15:36.0",
        "assistant_message",
        text="It sets how many times the client tries again.",
        usage=(3, 18, 500, 2000),
        stop="end_turn",
    )
    t.add("10:15:36.0", "recording_stopped", text="end of the transcript")
    return t.data()


def empty() -> bytes:
    return b""


def all_fixtures() -> dict[str, bytes]:
    return {
        "transcript_full.jsonl": transcript_full(),
        "transcript_truncated.jsonl": transcript_truncated(),
        "transcript_minimal.jsonl": transcript_minimal(),
        "claude_full.jsonl": claude_full(),
        "truncated.jsonl": truncated(),
        "cut_off_last_line.jsonl": cut_off_last_line(),
        "unknown_types_and_fields.jsonl": unknown_types_and_fields(),
        "wrong_version.jsonl": wrong_version(),
        "missing_tool_result.jsonl": missing_tool_result(),
        "start_stop_only.jsonl": start_stop_only(),
        "chat_client.jsonl": chat_client(),
        "empty.jsonl": empty(),
    }


def main() -> int:
    for name, data in all_fixtures().items():
        (HERE / name).write_bytes(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
