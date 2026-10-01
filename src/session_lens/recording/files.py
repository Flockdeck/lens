"""Files read and edited and commands run, from tool calls."""

from session_lens.recording.models import Event, FilesTouched

READ_TOOLS = frozenset({"Read", "NotebookRead"})
EDIT_TOOLS = frozenset({"Edit", "MultiEdit", "Write", "NotebookEdit"})
_PATH_KEYS = ("file_path", "notebook_path", "path")

MAX_ITEMS = 500
MAX_COMMAND = 300


def _path(event: Event) -> str | None:
    if isinstance(event.input, dict):
        for key in _PATH_KEYS:
            value = event.input.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def extract_files_touched(events: list[Event]) -> FilesTouched:
    """Distinct paths in first-seen order, and every Bash command in order.

    A call whose result reports an error is left out of the files lists: it did not touch the
    file. Commands are kept regardless, since they were run (or tried) either way. The lists
    keep the latest MAX_ITEMS entries; the `*_total` fields count everything.
    """
    failed = {
        e.tool_use_id for e in events if e.type == "tool_result" and e.is_error and e.tool_use_id
    }
    read: dict[str, None] = {}
    edited: dict[str, None] = {}
    commands: list[str] = []
    for e in events:
        if e.type != "tool_call":
            continue
        if e.tool == "Bash":
            if isinstance(e.input, dict) and isinstance(e.input.get("command"), str):
                commands.append(e.input["command"][:MAX_COMMAND])
            continue
        if e.tool_use_id in failed:
            continue
        path = _path(e)
        if path is None:
            continue
        if e.tool in READ_TOOLS:
            read[path] = None
        elif e.tool in EDIT_TOOLS:
            edited[path] = None
    return FilesTouched(
        read=list(read)[-MAX_ITEMS:],
        edited=list(edited)[-MAX_ITEMS:],
        commands=commands[-MAX_ITEMS:],
        read_total=len(read),
        edited_total=len(edited),
        commands_total=len(commands),
    )
