"""Builds the compact digest the enricher prompts from, so cost does not grow with file size."""

from session_lens.recording.models import (
    Digest,
    DigestFailure,
    DigestMessage,
    Event,
    FilesTouched,
    Metrics,
    RiskyAction,
)

MAX_PROMPTS = 20
KEEP_FIRST_PROMPTS = 5
PROMPT_CHARS = 1200
MAX_FINAL_MESSAGES = 5
MESSAGE_CHARS = 2000
MAX_FAILURES = 10
FAILURE_CHARS = 400
MAX_RISKS = 10
MAX_FILES = 30

_SEVERITY = {"high": 0, "medium": 1, "low": 2}


def trim(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}…[trimmed {len(text) - limit} chars]"


def _message(e: Event, limit: int) -> DigestMessage:
    return DigestMessage(
        seq=e.seq,
        text=trim(e.text or "", limit),
        redacted=bool(e.redacted),
        clipped=bool(e.clipped and "text" in e.clipped),
    )


def build_digest(
    events: list[Event],
    *,
    completeness: str,
    metrics: Metrics,
    risky_actions: list[RiskyAction],
    files: FilesTouched,
) -> Digest:
    prompts = [e for e in events if e.type == "user_prompt" and not e.subagent]
    omitted = max(0, len(prompts) - MAX_PROMPTS)
    if omitted:
        # the opening request and the most recent steering matter most
        prompts = prompts[:KEEP_FIRST_PROMPTS] + prompts[-(MAX_PROMPTS - KEEP_FIRST_PROMPTS) :]

    finals = [e for e in events if e.type == "assistant_message" and not e.subagent]

    failing = [
        e for e in events if e.type == "tool_result" and (e.is_error or e.interrupted)
    ]
    # the latest failures are the ones closest to how the session ended
    shown_failures = failing[-MAX_FAILURES:]

    ranked_risks = sorted(risky_actions, key=lambda r: (_SEVERITY[r.severity], r.seq))

    return Digest(
        project=next((e.project for e in events if e.project), None),
        agent=next((e.agent for e in events if e.agent), None),
        model=next((e.model for e in events if e.model), None),
        completeness=completeness,
        metrics=metrics,
        user_prompts=[_message(e, PROMPT_CHARS) for e in prompts],
        omitted_prompts=omitted,
        final_messages=[_message(e, MESSAGE_CHARS) for e in finals[-MAX_FINAL_MESSAGES:]],
        failing_results=[
            DigestFailure(
                seq=e.seq,
                tool=e.tool or "unknown",
                output=trim(e.output or "", FAILURE_CHARS),
                interrupted=bool(e.interrupted),
            )
            for e in shown_failures
        ],
        omitted_failures=len(failing) - len(shown_failures),
        risky_actions=ranked_risks[:MAX_RISKS],
        files_edited=files.edited[:MAX_FILES],
        files_read_count=len(files.read),
        commands_count=len(files.commands),
    )
