"""Telling the two kinds of file apart, and which prompts are the agent's own.

Both kinds are format version 1 (docs/recording-format.md, "Compatibility policy"), so `v` cannot
say which one a file is. The first line can.
"""

from lens.recording.models import (
    HOOK_ONLY_TYPES,
    HOOK_START_TEXTS,
    TRANSCRIPT_START_TEXT,
    Event,
    SourceFormat,
)

# Text Claude Code writes into the conversation for itself. A transcript leaves these out of
# `user_prompt` (only what the person typed is a prompt); a file made from hook events has them,
# since the agent counts them as prompts. They are not turns the person took.
_AGENT_PROMPT_PREFIXES = (
    "<task-notification",
    "<system-reminder",
    "<command-name>",
    "<command-message>",
    "<local-command-stdout",
    "<local-command-stderr",
    "<local-command-caveat",
    "[Request interrupted by user",
    "This session is being continued from a previous conversation",
)


def is_agent_prompt(event: Event) -> bool:
    return (event.text or "").lstrip().startswith(_AGENT_PROMPT_PREFIXES)


def detect_format(events: list[Event]) -> SourceFormat | None:
    """'transcript' (made from the agent's stored conversation), 'hooks' (0.3.47) or None.

    The reliable sign is the text of the first line. Where that is missing or unfamiliar, a line
    only one kind has decides. A file with neither sign is not labelled.
    """
    start = next((e for e in events if e.type == "recording_started"), None)
    if start is not None:
        if start.text == TRANSCRIPT_START_TEXT:
            return "transcript"
        if start.text in HOOK_START_TEXTS:
            return "hooks"
    if any(e.type in HOOK_ONLY_TYPES or e.pane_name for e in events):
        return "hooks"
    if any(
        e.type in ("conversation_title", "conversation_compacted")
        or e.usage
        or e.git_branch
        or e.cwd
        or e.agent_version
        for e in events
    ):
        return "transcript"
    return None
