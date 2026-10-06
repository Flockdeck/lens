# ruff: noqa: E501  (canned JSON fixtures read better on one line)
"""A tiny stdlib fake of the lens HTTP API (shapes from docs/contracts.md).

Serves the static UI from src/lens/web/ at `/` and canned, deterministic JSON for the
API, so the UI can be developed and tested without the real API, worker or MySQL.

    python tests/web/fake_server.py [--port 8765]

Magic behaviour for exercising the UI:
- batches advance on every GET (queued -> running -> done); the file named `bad*.jsonl` fails
- uploads: non-.jsonl, empty and files over 17 MiB are rejected per file; none accepted -> 422
- the session with the highest id has an expired raw recording: `raw_available` is false and
  events / enrich return 410
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import threading
import uuid
from datetime import UTC, datetime, timedelta
from email.parser import BytesParser
from email.policy import HTTP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

WEB_ROOT = Path(__file__).resolve().parents[2] / "src" / "lens" / "web"
MAX_FILE_BYTES = 17 * 1024 * 1024

AGENTS = ["claude-code", "codex", "gemini"]
MODELS = ["claude-sonnet-5-5", "claude-opus-5-5", "gpt-5", "gemini-3"]
PROJECTS = ["flockdeck", "vael", "lens", "terrawost"]
CATEGORIES = ["bugfix", "feature", "refactor", "exploration", "docs", "tests", "ops", "other"]
OUTCOMES = ["done", "abandoned", "stuck"]


def make_sessions(n: int = 60) -> dict[str, dict[str, Any]]:
    base = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
    out: dict[str, dict[str, Any]] = {}
    for i in range(1, n + 1):
        sid = str(i)
        started = base + timedelta(hours=7 * i)
        outcome = OUTCOMES[(i * 7) % 5 % 3]
        duration = 120 + (i * 97) % 5400
        calls = 10 + (i * 13) % 90
        errors = (i * 3) % 9
        out[sid] = {
            "id": sid,
            "raw_available": sid != str(n),
            "recording_session": f"rec-{i:04d}-{uuid.uuid5(uuid.NAMESPACE_DNS, sid).hex[:8]}",
            "project": PROJECTS[i % len(PROJECTS)],
            "agent": AGENTS[i % len(AGENTS)],
            "model": MODELS[i % len(MODELS)],
            "pane": f"pane-{i % 4}",
            "started_at": started.isoformat(),
            "ended_at": (started + timedelta(seconds=duration)).isoformat(),
            "completeness": ["clean", "clean", "truncated", "cut_off", "partial_agent"][i % 5],
            "category": CATEGORIES[i % len(CATEGORIES)],
            "outcome": outcome,
            "frustration": round(((i * 37) % 100) / 100, 2),
            "summary": f"Session {i}: worked through a {CATEGORIES[i % len(CATEGORIES)]} task in {PROJECTS[i % len(PROJECTS)]}.",
            "duration_seconds": duration,
            "metrics": {
                "duration_seconds": duration,
                "turns": 3 + i % 17,
                "tool_calls": calls,
                "tool_mix": {"Bash": calls // 2, "Read": calls // 3, "Edit": calls // 6, "Grep": 2},
                "tool_errors": errors,
                "tool_interrupted": i % 3,
                "unpaired_calls": i % 2,
                "permission": {
                    "prompts": 6,
                    "allowed": 4,
                    "denied": i % 3,
                    "auto_approved": 1,
                    "abandoned": 0,
                },
                "status_seconds": {
                    "working": duration * 0.6,
                    "waiting": duration * 0.25,
                    "idle": duration * 0.15,
                },
                "redacted_lines": i % 4,
                "clipped_lines": i % 2,
            },
            "risky_actions": (
                [
                    {
                        "seq": 12,
                        "tool": "Bash",
                        "summary": "rm -rf build/",
                        "severity": "medium",
                        "rule": "rm-recursive",
                    },
                    {
                        "seq": 40,
                        "tool": "Bash",
                        "summary": "git push --force origin main",
                        "severity": "high",
                        "rule": "force-push",
                    },
                ]
                if i % 4 == 0
                else []
            ),
            "files_touched": {
                "read": ["src/app.py", "README.md"],
                "edited": ["src/app.py"] if i % 3 else [],
                "commands": ["pytest -q", "git status"],
            },
            "warnings": ["skipped 2 unknown event types"] if i % 5 == 2 else [],
            "enrichment": {
                "summary": f"Session {i}: worked through a task end to end. <b>not markup</b>",
                "category": CATEGORIES[i % len(CATEGORIES)],
                "outcome": outcome,
                "frustration": round(((i * 37) % 100) / 100, 2),
                "stuck_points": [{"description": "Flaky test kept failing", "approx_seq": 33}]
                if outcome == "stuck"
                else [],
                "prompt_feedback": "Name the failing test up front." if i % 2 else None,
                "model_fit": ["well_matched", "overpowered", "underpowered", None][i % 4],
                "model_fit_reason": "Mostly routine edits." if i % 4 == 1 else None,
                "risk_notes": [{"seq": 40, "explanation": "Force push to a shared branch."}]
                if i % 4 == 0
                else [],
                "input_tokens": 1800 + i * 11,
                "output_tokens": 300 + i * 3,
                "model": "mock",
                "prompt_version": "v1",
            },
        }
    return out


def make_events(count: int = 350) -> list[dict[str, Any]]:
    types = ["user_prompt", "assistant_message", "tool_call", "tool_result", "status"]
    t0 = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
    evs = []
    for seq in range(1, count + 1):
        typ = types[seq % len(types)]
        ev: dict[str, Any] = {
            "v": 1,
            "seq": seq,
            "time": (t0 + timedelta(seconds=seq * 4)).isoformat(),
            "session": "rec",
            "pane": "pane-0",
            "type": typ,
        }
        if typ == "tool_call":
            ev.update(tool="Bash", input={"command": "pytest -q"})
        elif typ == "tool_result":
            ev.update(is_error=seq % 10 == 4, output="1 passed")
        elif typ == "status":
            ev.update(status="working")
        evs.append(ev)
    return evs


class State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.sessions = make_sessions()
        self.events = make_events()
        self.deleted_raw = {str(len(self.sessions))}
        self.batches: dict[str, dict[str, Any]] = {}
        self.enrich_calls: list[str] = []
        self.config: dict[str, Any] = {
            "storage": "filesystem",
            "enricher": "mock",
            "raw_retention_days": 30,
            "cleanup_interval_seconds": 86400,
            "version": "0.0.0-fake",
        }
        self.config_fails = False
        self.settings: dict[str, Any] = {
            "enricher": "mock",
            "anthropic_api_key": {"set": False, "source": None},
            "anthropic_model": "claude-haiku-4-5",
            "anthropic_workspace_id": None,
            "ollama_url": "http://127.0.0.1:11434",
            "ollama_model": "llama3.1:8b",
            "overridden": [],
        }


def parse_multipart(content_type: str, body: bytes) -> list[tuple[str, str, bytes]]:
    msg = BytesParser(policy=HTTP).parsebytes(
        b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + body
    )
    parts = []
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        filename = part.get_filename()
        if name == "files" and filename is not None:
            parts.append((name, filename, part.get_payload(decode=True) or b""))
    return parts


def advance(batch: dict[str, Any]) -> None:
    """Each poll moves items along: queued -> running -> done (or failed for bad*)."""
    for it in batch["items"]:
        if it["status"] == "queued":
            it["status"] = "running"
            it["attempts"] += 1
        elif it["status"] == "running":
            if it["filename"].startswith("bad"):
                it["status"], it["error"] = "failed", "unsupported recording version 2"
            else:
                it["status"], it["session_id"] = "done", "1"
    advance_counts(batch)


class Handler(BaseHTTPRequestHandler):
    server: FakeServer  # type: ignore[assignment]

    def log_message(self, *args: Any) -> None:  # keep test output quiet
        pass

    # -- helpers -------------------------------------------------------------------------
    def send_json(self, status: int, data: Any) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def static(self, path: str) -> None:
        rel = unquote(path).lstrip("/") or "index.html"
        target = (WEB_ROOT / rel).resolve()
        if WEB_ROOT not in target.parents or not target.is_file():
            self.send_json(404, {"detail": "Not Found"})
            return
        data = target.read_bytes()
        self.send_response(200)
        self.send_header(
            "Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        )
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # -- routing -------------------------------------------------------------------------
    def do_GET(self) -> None:
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        parts = [p for p in url.path.split("/") if p]
        st = self.server.state
        if url.path in ("/healthz", "/readyz"):
            return self.send_json(200, {"status": "ok"})
        if not parts or parts[0] not in ("batches", "sessions", "stats", "config", "settings"):
            return self.static(url.path)
        with st.lock:
            if parts == ["settings"]:
                return self.send_json(200, st.settings)
            if parts == ["config"]:
                if st.config_fails:
                    return self.send_json(500, {"detail": "config unavailable"})
                return self.send_json(200, st.config)
            if parts[0] == "batches" and len(parts) == 2:
                batch = st.batches.get(parts[1])
                if not batch:
                    return self.send_json(404, {"detail": "Batch not found"})
                advance(batch)
                return self.send_json(200, batch)
            if parts == ["sessions"]:
                return self.send_json(200, self.list_sessions(q))
            if parts[0] == "sessions" and len(parts) == 2:
                s = st.sessions.get(parts[1])
                return (
                    self.send_json(200, s)
                    if s
                    else self.send_json(404, {"detail": "Session not found"})
                )
            if parts[0] == "sessions" and len(parts) == 3 and parts[2] == "events":
                if parts[1] not in st.sessions:
                    return self.send_json(404, {"detail": "Session not found"})
                if parts[1] in st.deleted_raw:
                    return self.send_json(410, {"detail": "Raw recording deleted"})
                after, limit = int(q.get("after_seq", 0)), int(q.get("limit", 200))
                rest = [e for e in st.events if e["seq"] > after]
                page = rest[:limit]
                more = len(rest) > limit
                return self.send_json(
                    200, {"items": page, "next_after_seq": page[-1]["seq"] if more else None}
                )
            if parts == ["stats", "trends"]:
                return self.send_json(200, self.trends(q))
            if parts == ["stats", "compare"]:
                return self.send_json(200, self.compare(q.get("by", "agent")))
            if parts == ["stats", "usage"]:
                enr = [s["enrichment"] for s in st.sessions.values()]
                return self.send_json(
                    200,
                    {
                        "input_tokens": sum(e["input_tokens"] for e in enr),
                        "output_tokens": sum(e["output_tokens"] for e in enr),
                        "enrichments": len(enr),
                    },
                )
        self.send_json(404, {"detail": "Not Found"})

    def do_POST(self) -> None:
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        st = self.server.state
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        with st.lock:
            if parts == ["batches"]:
                return self.create_batch(body)
            if len(parts) == 3 and parts[0] == "batches" and parts[2] in ("retry", "cancel"):
                batch = st.batches.get(parts[1])
                if not batch:
                    return self.send_json(404, {"detail": "Batch not found"})
                for it in batch["items"]:
                    if parts[2] == "retry" and it["status"] == "failed":
                        it["status"], it["error"] = "queued", None
                        it["filename"] = it["filename"].replace("bad", "fixed", 1)
                    if parts[2] == "cancel" and it["status"] == "queued":
                        it["status"] = "cancelled"
                advance_counts(batch)
                return self.send_json(200, batch)
            if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "enrich":
                if parts[1] not in st.sessions:
                    return self.send_json(404, {"detail": "Session not found"})
                if parts[1] in st.deleted_raw:
                    return self.send_json(410, {"detail": "Raw recording expired"})
                st.enrich_calls.append(parts[1])
                return self.send_json(200, st.sessions[parts[1]])
        self.send_json(404, {"detail": "Not Found"})

    def do_PUT(self) -> None:
        parts = [p for p in urlparse(self.path).path.split("/") if p]
        st = self.server.state
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        with st.lock:
            if parts == ["settings"]:
                key = st.settings["anthropic_api_key"]
                new_key = body.get("anthropic_api_key", "unchanged")
                if body.get("enricher") == "anthropic" and not (key["set"] or new_key):
                    return self.send_json(
                        422, {"detail": "the anthropic enricher needs an API key"}
                    )
                if new_key is None:
                    st.settings["anthropic_api_key"] = {"set": False, "source": None}
                elif new_key != "unchanged":
                    st.settings["anthropic_api_key"] = {"set": True, "source": "settings"}
                for name in ("enricher", "anthropic_model", "ollama_url", "ollama_model"):
                    if body.get(name):
                        st.settings[name] = body[name]
                if "anthropic_workspace_id" in body:
                    st.settings["anthropic_workspace_id"] = body["anthropic_workspace_id"]
                st.config["enricher"] = st.settings["enricher"]
                return self.send_json(200, st.settings)
        self.send_json(404, {"detail": "Not Found"})

    def do_DELETE(self) -> None:
        parts = [p for p in urlparse(self.path).path.split("/") if p]
        st = self.server.state
        with st.lock:
            if len(parts) == 2 and parts[0] == "sessions" and parts[1] in st.sessions:
                del st.sessions[parts[1]]
                self.send_response(204)
                self.end_headers()
                return
        self.send_json(404, {"detail": "Session not found"})

    # -- endpoints -----------------------------------------------------------------------
    def create_batch(self, body: bytes) -> None:
        st = self.server.state
        files = parse_multipart(self.headers.get("Content-Type", ""), body)
        accepted, rejected, items = [], [], []
        for _, filename, data in files:
            if not filename.lower().endswith(".jsonl"):
                rejected.append({"filename": filename, "reason": "wrong file type"})
            elif not data:
                rejected.append({"filename": filename, "reason": "empty"})
            elif len(data) > MAX_FILE_BYTES:
                rejected.append({"filename": filename, "reason": "too large"})
            else:
                accepted.append(filename)
                items.append(
                    {
                        "id": uuid.uuid4().hex[:8],
                        "filename": filename,
                        "status": "queued",
                        "attempts": 0,
                        "error": None,
                        "session_id": None,
                    }
                )
        if not accepted:
            return self.send_json(422, {"detail": "No acceptable files", "rejected": rejected})
        bid = uuid.uuid4().hex[:12]
        batch = {"id": bid, "status": "running", "counts": {}, "items": items}
        advance_counts(batch)
        st.batches[bid] = batch
        self.send_json(202, {"id": bid, "accepted": accepted, "rejected": rejected})

    def list_sessions(self, q: dict[str, str]) -> dict[str, Any]:
        rows = list(self.server.state.sessions.values())
        for key in ("project", "agent", "model", "category", "outcome"):
            if q.get(key):
                rows = [r for r in rows if r[key] == q[key]]
        if q.get("from"):
            rows = [r for r in rows if r["started_at"][:10] >= q["from"][:10]]
        if q.get("to"):
            rows = [r for r in rows if r["started_at"][:10] <= q["to"][:10]]
        rows.sort(key=lambda r: r["started_at"], reverse=True)
        limit, offset = int(q.get("limit", 50)), int(q.get("offset", 0))
        keys = (
            "id",
            "raw_available",
            "recording_session",
            "project",
            "agent",
            "model",
            "pane",
            "started_at",
            "ended_at",
            "completeness",
            "category",
            "outcome",
            "frustration",
            "summary",
            "duration_seconds",
        )
        return {
            "total": len(rows),
            "items": [{k: r[k] for k in keys} for r in rows[offset : offset + limit]],
        }

    def trends(self, q: dict[str, str]) -> list[dict[str, Any]]:
        step = 7 if q.get("interval") == "week" else 1
        buckets: dict[str, list[dict[str, Any]]] = {}
        for s in self.server.state.sessions.values():
            if q.get("project") and s["project"] != q["project"]:
                continue
            day = datetime.fromisoformat(s["started_at"]).date()
            key = (day - timedelta(days=day.toordinal() % step)).isoformat()
            buckets.setdefault(key, []).append(s)
        return [aggregate(b, rows) | {"bucket": b} for b, rows in sorted(buckets.items())]

    def compare(self, by: str) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for s in self.server.state.sessions.values():
            groups.setdefault(s[by], []).append(s)
        return [aggregate(k, rows) | {"key": k} for k, rows in sorted(groups.items())]


def advance_counts(batch: dict[str, Any]) -> None:
    counts = dict.fromkeys(["queued", "running", "done", "failed", "cancelled"], 0)
    for it in batch["items"]:
        counts[it["status"]] += 1
    batch["counts"] = counts
    batch["status"] = "running" if counts["queued"] + counts["running"] else "done"


def aggregate(_: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    calls = sum(r["metrics"]["tool_calls"] for r in rows) or 1
    prompts = sum(r["metrics"]["permission"]["prompts"] for r in rows) or 1
    return {
        "sessions": n,
        "outcomes": {o: sum(1 for r in rows if r["outcome"] == o) for o in OUTCOMES},
        "avg_frustration": round(sum(r["frustration"] for r in rows) / n, 3),
        "tool_error_rate": round(sum(r["metrics"]["tool_errors"] for r in rows) / calls, 4),
        "permission_denial_rate": round(
            sum(r["metrics"]["permission"]["denied"] for r in rows) / prompts, 4
        ),
    }


class FakeServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int = 0) -> None:
        super().__init__(("127.0.0.1", port), Handler)
        self.state = State()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--retention-days", type=int, default=30, help="0 = keep forever")
    ap.add_argument("--enricher", default="mock", choices=["mock", "ollama", "anthropic"])
    ap.add_argument("--storage", default="filesystem", choices=["filesystem"])
    ap.add_argument("--no-config", action="store_true", help="make GET /config fail")
    args = ap.parse_args()
    srv = FakeServer(args.port)
    srv.state.config.update(
        raw_retention_days=args.retention_days, enricher=args.enricher, storage=args.storage
    )
    srv.state.config_fails = args.no_config
    print(f"fake lens API + UI on {srv.url}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
