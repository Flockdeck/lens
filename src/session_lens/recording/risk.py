"""Rule-based detection of risky tool calls. Heuristics, not a security boundary."""

import re
import shlex
from collections.abc import Iterator
from typing import Literal

from session_lens.recording.models import Event, RiskyAction

Severity = Literal["low", "medium", "high"]
Hit = tuple[str, Severity, str]  # rule, severity, summary

MAX_SUMMARY = 160

_KEY_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".ppk", ".keystore", ".jks")
_OTHER_SECRET_NAMES = (".npmrc", ".netrc", ".pgpass", ".git-credentials")
_TEMPLATE_SUFFIXES = (".example", ".sample", ".template", ".dist")
_PATH_KEYS = ("file_path", "path", "notebook_path")
_DANGEROUS_RM_TARGETS = {"/", "/*", "~", "~/", "$HOME", "*", ".", "..", "./", "../"}

_PIPE_TO_SHELL = re.compile(r"\b(?:curl|wget)\b[^|;&]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b")
_DROP = re.compile(r"\bdrop\s+(?:table|database|schema|index|view)\b", re.I)
_TRUNCATE = re.compile(r"\btruncate\s+table\b", re.I)
_DELETE_ALL = re.compile(r"\bdelete\s+from\s+[\w.`\"\[\]]+\s*(?:;|$|[\"'])", re.I)
_CHMOD_777 = re.compile(r"\bchmod\b[^;&|]*\b0?777\b")
_DISK = re.compile(r"\bmkfs(?:\.\w+)?\b|\bdd\b[^;&|]*\bof=/dev/")
_INFRA = re.compile(r"\bterraform\s+destroy\b|\bkubectl\s+delete\b|\bhelm\s+uninstall\b")


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= MAX_SUMMARY else text[: MAX_SUMMARY - 1] + "…"


def _base(path: str) -> str:
    return re.split(r"[\\/]", path.rstrip("\\/"))[-1]


def secret_file_severity(name: str) -> Severity | None:
    """Severity if `name` is a secret file by Flockdeck's auto-review name check, else None.

    Template files such as `.env.example` hold no secrets and are exempted.
    """
    low = _base(name).lower()
    if not low or low.endswith(_TEMPLATE_SUFFIXES):
        return None
    if low.startswith("id_") and not low.endswith(".pub"):
        return "high"
    if low.endswith(_KEY_SUFFIXES) or "credential" in low:
        return "high"
    if low == ".env" or low.startswith(".env.") or low in _OTHER_SECRET_NAMES:
        return "medium"
    return None


def _segments(command: str) -> Iterator[list[str]]:
    for seg in re.split(r"&&|\|\||[;&|\n]", command):
        try:
            tokens = shlex.split(seg)
        except ValueError:
            tokens = seg.split()
        while tokens and tokens[0] in ("sudo", "time", "env", "command"):
            tokens = tokens[1:]
        if tokens:
            yield tokens


def _flags(tokens: list[str]) -> tuple[set[str], set[str]]:
    short = {c for t in tokens if t.startswith("-") and not t.startswith("--") for c in t[1:]}
    long = {t for t in tokens if t.startswith("--")}
    return short, long


def _rm(tokens: list[str]) -> Hit | None:
    short, long = _flags(tokens)
    recursive = bool(short & {"r", "R"}) or "--recursive" in long
    if not recursive:
        return None
    force = "f" in short or "--force" in long
    targets = [t for t in tokens[1:] if not t.startswith("-")]
    summary = _clip(" ".join(tokens))
    if any(t in _DANGEROUS_RM_TARGETS for t in targets):
        return "rm_rf", "high", summary
    return "rm_rf", "medium" if force else "low", summary


def _git(tokens: list[str]) -> list[Hit]:
    hits: list[Hit] = []
    short, long = _flags(tokens)
    summary = _clip(" ".join(tokens))
    if "push" in tokens:
        plus_ref = any(t.startswith("+") and len(t) > 1 for t in tokens[tokens.index("push") :])
        if "--force" in long or "f" in short or plus_ref:
            hits.append(("git_force_push", "high", summary))
        elif any(t.startswith("--force-with-lease") for t in long):
            hits.append(("git_force_push", "medium", summary))
    if "reset" in tokens and "--hard" in long:
        hits.append(("git_reset_hard", "medium", summary))
    if "clean" in tokens and ("f" in short or "--force" in long):
        hits.append(("git_clean", "medium", summary))
    if "--no-verify" in long and ("commit" in tokens or "push" in tokens):
        hits.append(("skip_hooks", "low", summary))
    return hits


def _command_hits(command: str) -> list[Hit]:
    hits: list[Hit] = []
    for tokens in _segments(command):
        head = _base(tokens[0])
        if head == "rm" and (hit := _rm(tokens)):
            hits.append(hit)
        elif head == "git":
            hits.extend(_git(tokens))
        elif head == "chmod" and _CHMOD_777.search(" ".join(tokens)):
            hits.append(("chmod_777", "medium", _clip(" ".join(tokens))))
    checks: list[tuple[re.Pattern[str], str, Severity]] = [
        (_PIPE_TO_SHELL, "pipe_to_shell", "high"),
        (_DROP, "destructive_sql", "high"),
        (_TRUNCATE, "destructive_sql", "high"),
        (_DELETE_ALL, "destructive_sql", "medium"),
        (_DISK, "disk_write", "high"),
        (_INFRA, "infra_destroy", "medium"),
    ]
    for pattern, rule, severity in checks:
        if pattern.search(command):
            hits.append((rule, severity, _clip(command)))
    first = command.lstrip().split(None, 1)
    if first and first[0] == "sudo":
        hits.append(("sudo", "low", _clip(command)))
    for word in re.split(r"[\s'\"=<>;|&()]+", command):
        if word and (sev := secret_file_severity(word)):
            hits.append(("secret_file", sev, f"Bash touches {_base(word)}"))
    return hits


def _string_fields(event: Event, keys: tuple[str, ...]) -> Iterator[str]:
    if isinstance(event.input, dict):
        for key in keys:
            value = event.input.get(key)
            if isinstance(value, str):
                yield value


def risks_for_call(event: Event) -> list[Hit]:
    """Risk hits for one tool_call event."""
    hits: list[Hit] = []
    if event.tool == "Bash":
        for command in _string_fields(event, ("command",)):
            hits.extend(_command_hits(command))
    else:
        for query in _string_fields(event, ("query", "sql")):
            hits.extend(h for h in _command_hits(query) if h[0] == "destructive_sql")
        for path in _string_fields(event, _PATH_KEYS):
            if sev := secret_file_severity(path):
                hits.append(("secret_file", sev, f"{event.tool} {_base(path)}"))
    # one entry per rule per call, keeping the most severe
    order = {"low": 0, "medium": 1, "high": 2}
    best: dict[str, Hit] = {}
    for hit in hits:
        if hit[0] not in best or order[hit[1]] > order[best[hit[0]][1]]:
            best[hit[0]] = hit
    return list(best.values())


def find_risky_actions(events: list[Event]) -> list[RiskyAction]:
    out: list[RiskyAction] = []
    for e in events:
        if e.type != "tool_call":
            continue
        for rule, severity, summary in risks_for_call(e):
            out.append(
                RiskyAction(
                    seq=e.seq, tool=e.tool or "unknown", summary=summary, severity=severity,
                    rule=rule,
                )
            )
    return out

