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
_OTHER_SECRET_NAMES = (".npmrc", ".netrc", ".pgpass")
_TEMPLATE_SUFFIXES = (".example", ".sample", ".template", ".dist")
_SSH_KEY_NAMES = frozenset(
    {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "id_ecdsa_sk", "id_ed25519_sk"}
)
_BARE_CREDENTIAL_FILE = re.compile(r"[\w.-]*credentials?(?:\.(?:json|ya?ml|toml|ini|txt|csv|xml))?")
_PATH_KEYS = ("file_path", "path", "notebook_path")
_DANGEROUS_RM_TARGETS = {"/", "~", "~/", "$HOME", ".", "..", "./", "../"}
_DANGEROUS_RM_GLOB = re.compile(r"(?:\.|~|\$HOME|\$\{HOME\})?/?\*")
_PROTECTED_BRANCHES = {"main", "master", "trunk", "develop", "production"}
_SQL_CLIENTS = frozenset(
    {"psql", "mysql", "mariadb", "sqlite3", "sqlcmd", "mycli", "pgcli", "clickhouse-client"}
)
_NOT_A_DISK = {"/dev/null", "/dev/zero", "/dev/stdout", "/dev/stderr", "/dev/tty"}

_PIPE_TO_SHELL = re.compile(r"\b(?:curl|wget)\b[^|;&]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b")
_DROP = re.compile(r"\bdrop\s+(?:table|database|schema|index|view)\b", re.I)
_TRUNCATE = re.compile(r"\btruncate\s+table\b", re.I)
_DELETE_ALL = re.compile(r"\bdelete\s+from\s+[\w.`\"\[\]]+\s*(?:;|$|[\"'])", re.I)
_CHMOD_777 = re.compile(r"\bchmod\b[^;&|]*\b0?777\b")


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= MAX_SUMMARY else text[: MAX_SUMMARY - 1] + "…"


def _base(path: str) -> str:
    return re.split(r"[\\/]", path.rstrip("\\/"))[-1]


def secret_file_severity(name: str, *, pathlike: bool = True) -> Severity | None:
    """Severity if `name` is a secret file by Flockdeck's auto-review name check, else None.

    Template files such as `.env.example` hold no secrets and are exempted. A word taken from a
    shell command is only checked fully if it looks like a path (it has a separator); a bare word
    such as `id_field` or `credential.helper` must match a known secret file name exactly.
    """
    low = _base(name).lower()
    if not low or low.endswith(_TEMPLATE_SUFFIXES):
        return None
    if low == ".git-credentials":
        return "high"
    if pathlike:
        if low.startswith("id_") and not low.endswith(".pub"):
            return "high"
        if low.endswith(_KEY_SUFFIXES) or "credential" in low:
            return "high"
    elif (
        low in _SSH_KEY_NAMES or low.endswith(_KEY_SUFFIXES) or _BARE_CREDENTIAL_FILE.fullmatch(low)
    ):
        return "high"
    if low == ".env" or low.startswith(".env.") or low in _OTHER_SECRET_NAMES:
        return "medium"
    return None


def _segments(command: str) -> Iterator[tuple[list[str], bool]]:
    """Each simple command as (tokens without wrappers such as sudo, whether sudo was used)."""
    for seg in re.split(r"&&|\|\||[;&|\n]", command):
        try:
            tokens = shlex.split(seg)
        except ValueError:
            tokens = seg.split()
        sudo = False
        while tokens and tokens[0] in ("sudo", "time", "env", "command"):
            sudo = sudo or tokens[0] == "sudo"
            tokens = tokens[1:]
            while tokens and tokens[0].startswith("-"):
                flag = tokens.pop(0)
                if flag in ("-u", "-g") and tokens:
                    tokens.pop(0)
        if tokens or sudo:
            yield tokens, sudo


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
    if any(t in _DANGEROUS_RM_TARGETS or _DANGEROUS_RM_GLOB.fullmatch(t) for t in targets):
        return "rm_rf", "high", summary
    return "rm_rf", "medium" if force else "low", summary


def _git(tokens: list[str]) -> list[Hit]:
    hits: list[Hit] = []
    short, long = _flags(tokens)
    summary = _clip(" ".join(tokens))
    if "push" in tokens:
        refs = [t for t in tokens[tokens.index("push") + 1 :] if not t.startswith("-")]
        plus_ref = any(t.startswith("+") and len(t) > 1 for t in refs)
        if "--force" in long or "f" in short or plus_ref:
            hits.append(("git_force_push", "high", summary))
        elif any(t.startswith("--force-with-lease") for t in long):
            hits.append(("git_force_push", "medium", summary))
        # `git push origin :branch` and `git push --delete origin branch` remove a remote ref
        deleted = [t[1:] for t in refs if t.startswith(":") and len(t) > 1]
        if "--delete" in long or "d" in short:
            deleted += refs[1:]
        if deleted:
            protected = any(_base(r) in _PROTECTED_BRANCHES for r in deleted)
            hits.append(("git_push_delete", "high" if protected else "medium", summary))
    if "reset" in tokens and "--hard" in long:
        hits.append(("git_reset_hard", "medium", summary))
    if "clean" in tokens and ("f" in short or "--force" in long):
        hits.append(("git_clean", "medium", summary))
    if "--no-verify" in long and ("commit" in tokens or "push" in tokens):
        hits.append(("skip_hooks", "low", summary))
    return hits


def _sql_hits(text: str) -> list[Hit]:
    checks: list[tuple[re.Pattern[str], Severity]] = [
        (_DROP, "high"),
        (_TRUNCATE, "high"),
        (_DELETE_ALL, "medium"),
    ]
    summary = _clip(text)
    return [("destructive_sql", sev, summary) for pattern, sev in checks if pattern.search(text)]


def _command_hits(command: str) -> list[Hit]:
    hits: list[Hit] = []
    segments = list(_segments(command))
    sql_client = False
    for tokens, _ in segments:
        if not tokens:
            continue
        head = _base(tokens[0])
        summary = _clip(" ".join(tokens))
        if head == "rm" and (hit := _rm(tokens)):
            hits.append(hit)
        elif head == "git":
            hits.extend(_git(tokens))
        elif head == "chmod" and _CHMOD_777.search(" ".join(tokens)):
            hits.append(("chmod_777", "medium", summary))
        elif head.startswith("mkfs"):
            hits.append(("disk_write", "high", summary))
        elif head == "dd" and any(
            t.startswith("of=/dev/") and t[3:] not in _NOT_A_DISK for t in tokens
        ):
            hits.append(("disk_write", "high", summary))
        elif (
            (head == "terraform" and "destroy" in tokens)
            or (head == "kubectl" and "delete" in tokens)
            or (head == "helm" and "uninstall" in tokens)
        ):
            hits.append(("infra_destroy", "medium", summary))
        if any(_base(t) in _SQL_CLIENTS for t in tokens):
            sql_client = True
    # SQL only counts where a SQL client is in the command: `git commit -m 'drop table users'`
    # or an `echo` of it is text, not a statement.
    if sql_client:
        hits.extend(_sql_hits(command))
    if _PIPE_TO_SHELL.search(command):
        hits.append(("pipe_to_shell", "high", _clip(command)))
    if any(sudo for _, sudo in segments):
        hits.append(("sudo", "low", _clip(command)))
    for word in re.split(r"[\s'\"=<>;|&()]+", command):
        if word and (sev := secret_file_severity(word, pathlike=bool(re.search(r"[\\/]", word)))):
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
            hits.extend(_sql_hits(query))
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
                    seq=e.seq,
                    tool=e.tool or "unknown",
                    summary=summary,
                    severity=severity,
                    rule=rule,
                )
            )
    return out
