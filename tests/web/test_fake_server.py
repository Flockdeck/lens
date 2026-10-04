# ruff: noqa: E501  (canned JSON fixtures read better on one line)
"""Checks the fake API serves the contract shapes the UI relies on, plus the static files."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.web.fake_server import WEB_ROOT, FakeServer


@pytest.fixture
def server() -> Iterator[FakeServer]:
    srv = FakeServer(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()
    srv.server_close()


def call(
    srv: FakeServer,
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    h = dict(headers or {})
    req = urllib.request.Request(srv.url + path, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req) as res:  # noqa: S310
            raw = res.read()
            return res.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, (json.loads(raw) if raw else None)


def multipart(files: list[tuple[str, bytes]]) -> tuple[bytes, dict[str, str]]:
    boundary = uuid.uuid4().hex
    out = b""
    for name, data in files:
        out += (
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{name}"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n"
            ).encode()
            + data
            + b"\r\n"
        )
    out += f"--{boundary}--\r\n".encode()
    return out, {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def test_static_ui_is_served(server: FakeServer) -> None:
    with urllib.request.urlopen(server.url + "/") as res:  # noqa: S310
        assert b"lens" in res.read()
    with urllib.request.urlopen(server.url + "/js/main.js") as res:  # noqa: S310
        assert "javascript" in res.headers["Content-Type"]


def test_batch_lifecycle_with_rejections_and_retry(server: FakeServer) -> None:
    body, headers = multipart(
        [("a.jsonl", b"{}"), ("bad1.jsonl", b"{}"), ("notes.txt", b"x"), ("empty.jsonl", b"")]
    )
    status, created = call(server, "POST", "/batches", body=body, headers=headers)
    assert status == 202
    assert created["accepted"] == ["a.jsonl", "bad1.jsonl"]
    assert {r["filename"] for r in created["rejected"]} == {"notes.txt", "empty.jsonl"}

    seen: dict[str, Any] = {}
    for _ in range(4):
        _, seen = call(server, "GET", f"/batches/{created['id']}")
    assert seen["status"] == "done"
    assert set(seen["counts"]) == {"queued", "running", "done", "failed", "cancelled"}
    assert seen["counts"]["failed"] == 1
    assert {"id", "filename", "status", "attempts", "error", "session_id"} <= set(seen["items"][0])

    call(server, "POST", f"/batches/{created['id']}/retry")
    _, after = call(server, "GET", f"/batches/{created['id']}")
    assert after["counts"]["failed"] == 0


def test_upload_with_nothing_acceptable_is_422(server: FakeServer) -> None:
    body, headers = multipart([("notes.txt", b"x")])
    status, data = call(server, "POST", "/batches", body=body, headers=headers)
    assert status == 422
    assert data["rejected"][0]["filename"] == "notes.txt"


def test_sessions_filter_and_paginate(server: FakeServer) -> None:
    _, page1 = call(server, "GET", "/sessions?limit=25&offset=0")
    _, page3 = call(server, "GET", "/sessions?limit=25&offset=50")
    assert page1["total"] == 60 and len(page1["items"]) == 25 and len(page3["items"]) == 10
    _, mine = call(server, "GET", "/sessions?project=vael&outcome=done")
    assert mine["items"] and all(
        s["project"] == "vael" and s["outcome"] == "done" for s in mine["items"]
    )


def test_session_detail_events_enrich_delete(server: FakeServer) -> None:
    _, s = call(server, "GET", "/sessions/4")
    assert {"metrics", "risky_actions", "files_touched", "warnings", "enrichment"} <= set(s)
    _, evs = call(server, "GET", "/sessions/4/events?after_seq=100&limit=50")
    assert [e["seq"] for e in evs["items"]][:2] == [101, 102] and len(evs["items"]) == 50
    assert evs["next_after_seq"] == 150
    _, last = call(server, "GET", "/sessions/4/events?after_seq=300&limit=100")
    assert len(last["items"]) == 50 and last["next_after_seq"] is None
    assert s["raw_available"] is True
    assert call(server, "GET", "/sessions/60")[1]["raw_available"] is False
    assert call(server, "GET", "/sessions/60/events")[0] == 410
    assert call(server, "POST", "/sessions/60/enrich")[0] == 410
    _, listing = call(server, "GET", "/sessions?limit=2")
    assert [i["raw_available"] for i in listing["items"]] == [False, True]  # newest is expired
    assert call(server, "POST", "/sessions/4/enrich")[0] == 200
    assert call(server, "DELETE", "/sessions/4")[0] == 204
    assert call(server, "GET", "/sessions/4")[0] == 404


def test_stats_shapes(server: FakeServer) -> None:
    _, trends = call(server, "GET", "/stats/trends?interval=week")
    assert {"bucket", "sessions", "outcomes", "avg_frustration", "tool_error_rate"} <= set(
        trends[0]
    )
    _, compare = call(server, "GET", "/stats/compare?by=model")
    assert {
        "key",
        "sessions",
        "outcomes",
        "tool_error_rate",
        "permission_denial_rate",
        "avg_frustration",
    } <= set(compare[0])
    _, usage = call(server, "GET", "/stats/usage")
    assert set(usage) == {"input_tokens", "output_tokens", "enrichments"}


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.parametrize("name", ["helpers.test.mjs", "modules.test.mjs"])
def test_js_helpers_under_node(name: str) -> None:
    script = Path(__file__).with_name(name)
    run = subprocess.run(["node", str(script)], capture_output=True, text=True, check=False)  # noqa: S603, S607
    assert run.returncode == 0, run.stdout + run.stderr


def test_config_shape_and_no_store(server: FakeServer) -> None:
    req = urllib.request.Request(server.url + "/config")
    with urllib.request.urlopen(req) as res:  # noqa: S310
        assert res.headers["Cache-Control"] == "no-store"
        cfg = json.loads(res.read())
    assert set(cfg) == {
        "storage",
        "enricher",
        "raw_retention_days",
        "cleanup_interval_seconds",
        "version",
    }


def web_files() -> list[Path]:
    return [
        p
        for p in WEB_ROOT.rglob("*")
        if p.is_file() and p.suffix in {".html", ".js", ".css", ".mjs"}
    ]


def test_web_files_make_no_external_requests() -> None:
    """No CDN, font or analytics: the only absolute URLs allowed are XML namespaces."""
    allowed = ("http://www.w3.org/",)
    offenders = []
    for path in web_files():
        for url in re.findall(
            r"(?:https?:)?//[A-Za-z0-9.-]+\.[A-Za-z]{2,}[^\s\"'`)<>]*", path.read_text("utf-8")
        ):
            if url.startswith("//") and not url.startswith("//www."):
                continue  # a JS comment, not a protocol-relative URL
            if not url.startswith(allowed):
                offenders.append(f"{path.name}: {url}")
    assert offenders == []
    assert web_files()


def test_index_sends_no_referrer_and_loads_only_local_assets() -> None:
    html = (WEB_ROOT / "index.html").read_text("utf-8")
    assert '<meta name="referrer" content="no-referrer">' in html
    for ref in re.findall(r'(?:src|href)="([^"]+)"', html):
        assert not re.match(r"^(?:[a-z]+:)?//", ref) or ref.startswith("data:"), ref


def test_the_ui_holds_no_credentials_and_filenames_never_go_into_urls() -> None:
    api_js = (WEB_ROOT / "js" / "api.js").read_text("utf-8")
    assert "Authorization" not in api_js and "sessionStorage" not in api_js
    assert "location.search" not in "".join(p.read_text("utf-8") for p in web_files())


def test_web_root_exists() -> None:
    assert (WEB_ROOT / "index.html").is_file()
