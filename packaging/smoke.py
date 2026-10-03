"""Run a built binary and use it: start it with a fresh data directory, upload a recording,
wait for the analysis, read it back, and stop it.

    python packaging/smoke.py dist/session-lens[.exe] [--keep]

stdlib only. Exit status 0 means it works. Used by CI for every platform the binary is built on.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "claude_full.jsonl"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def call(
    url: str, data: bytes | None = None, headers: dict[str, str] | None = None
) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=15) as res:  # noqa: S310
            return res.status, res.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()


def multipart(name: str, content: bytes) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{name}"\r\n'
            f"Content-Type: application/x-ndjson\r\n\r\n"
        ).encode()
        + content
        + f"\r\n--{boundary}--\r\n".encode()
    )
    return body, f"multipart/form-data; boundary={boundary}"


def check(ok: bool, what: str) -> None:
    print(("ok   " if ok else "FAIL ") + what, flush=True)
    if not ok:
        raise SystemExit(1)


def start(binary: Path, port: int, data: Path, extra: dict[str, str]) -> subprocess.Popen[bytes]:
    env = {
        **os.environ,
        "DATA_DIR": str(data / "my data"),  # a space in the path, as real ones have
        "PORT": str(port),
        "ENRICHER": "mock",
        "ANTHROPIC_API_KEY": "",
        "WORKER_POLL_SECONDS": "0.1",
        **extra,
    }
    # stdout is a pipe nobody reads, as when another program launches it: the app must cope.
    return subprocess.Popen(  # noqa: S603
        [str(binary), "serve"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )


def wait_ready(proc: subprocess.Popen[bytes], base: str) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            print(proc.stdout.read().decode(errors="replace") if proc.stdout else "")
            check(False, f"the binary stayed up (exit {proc.returncode})")
        try:
            if call(base + "/readyz")[0] == 200:
                return
        except OSError:
            time.sleep(0.2)
    check(False, "the binary became ready within 60 s")


def stop(proc: subprocess.Popen[bytes]) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        check(False, "it stopped when asked")


def upload_and_wait(base: str) -> tuple[dict[str, int], list[dict[str, object]]]:
    body, ctype = multipart("run.jsonl", FIXTURE.read_bytes())
    status, resp = call(base + "/batches", body, {"Content-Type": ctype})
    check(status == 202, "an upload is accepted")
    batch = json.loads(resp)["id"]
    for _ in range(300):
        detail = json.loads(call(f"{base}/batches/{batch}")[1])
        counts = detail["counts"]
        if counts["queued"] == 0 and counts["running"] == 0:
            break
        time.sleep(0.1)
    return counts, detail["items"]


def phase_normal(binary: Path) -> None:
    print("--- the default setup", flush=True)
    data, port = Path(tempfile.mkdtemp(prefix="session-lens-smoke-")), free_port()
    base = f"http://127.0.0.1:{port}"
    started = time.monotonic()
    proc = start(binary, port, data, {})
    try:
        wait_ready(proc, base)
        check(True, f"ready in {time.monotonic() - started:.1f} s")
        status, page = call(base + "/")
        check(status == 200 and b"session-lens" in page, "the web UI is served")
        status, css = call(base + "/css/app.css")
        check(status == 200 and len(css) > 1000, "its stylesheet and fonts are inside the binary")
        status, cfg = call(base + "/config")
        check(status == 200 and json.loads(cfg)["enricher"] == "mock", "/config answers")
        counts, _ = upload_and_wait(base)
        check(counts["done"] == 1, "the worker, inside the same process, analysed it")
        sessions = json.loads(call(base + "/sessions")[1])
        check(
            sessions["total"] == 1 and sessions["items"][0]["outcome"], "the session has an outcome"
        )
        sid = sessions["items"][0]["id"]
        status, events = call(f"{base}/sessions/{sid}/events?limit=3")
        check(
            status == 200 and len(json.loads(events)["items"]) == 3, "its raw events are readable"
        )
        check(call(base + "/settings")[0] == 200, "settings are readable")
        wrong = urllib.request.Request(base + "/healthz", headers={"Host": "evil.example"})
        try:
            urllib.request.urlopen(wrong, timeout=5)  # noqa: S310
            check(False, "a request for another host name is refused")
        except urllib.error.HTTPError as err:
            check(err.code == 421, "a request for another host name is refused")
        check(
            (data / "my data" / "session-lens.db").exists(), "the database is in the data directory"
        )
        check(
            (data / "my data" / "session-lens.log").stat().st_size > 0,
            "logs go to a file when stdout is a pipe",
        )
    finally:
        stop(proc)
    # Same data directory, new process: nothing is lost by stopping.
    proc = start(binary, port, data, {})
    try:
        wait_ready(proc, base)
        check(json.loads(call(base + "/sessions")[1])["total"] == 1, "it remembers after a restart")
    finally:
        stop(proc)


def phase_remote_enricher_is_bundled(binary: Path) -> None:
    """Choose the Anthropic enricher with the SDK aimed at a port nothing listens on: it proves
    the SDK is inside the binary and gets as far as trying to connect, and nothing is sent."""
    print("--- the Anthropic enricher, offline", flush=True)
    data, port = Path(tempfile.mkdtemp(prefix="session-lens-smoke-")), free_port()
    base = f"http://127.0.0.1:{port}"
    extra = {
        "ENRICHER": "anthropic",
        "ANTHROPIC_API_KEY": "sk-ant-smoke-not-real",
        "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{free_port()}",
        "MAX_ATTEMPTS": "1",
    }
    proc = start(binary, port, data, extra)
    try:
        wait_ready(proc, base)
        check(
            json.loads(call(base + "/config")[1])["enricher"] == "anthropic",
            "the choice is reported",
        )
        _, items = upload_and_wait(base)
        error = str(items[0].get("error"))
        check(
            "Anthropic" in error and "Import" not in error and "Module" not in error,
            f"the SDK is bundled and tried to connect ({error})",
        )
    finally:
        stop(proc)


def phase_killed_launcher_takes_the_server_with_it(binary: Path) -> None:
    """Something kills the program outright (Task Manager, or Flockdeck stopping it). The server
    behind the launcher must not be left running, holding the port and the database."""
    print("--- the program is killed from outside", flush=True)
    data, port = Path(tempfile.mkdtemp(prefix="session-lens-smoke-")), free_port()
    base = f"http://127.0.0.1:{port}"
    proc = start(binary, port, data, {})
    wait_ready(proc, base)
    proc.kill()  # the hard kill: no chance to pass it on
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        try:
            call(base + "/healthz")
        except OSError:
            check(True, "the server stopped listening after its launcher was killed")
            return
        time.sleep(0.5)
    check(False, "the server stopped listening after its launcher was killed")


def main() -> int:
    binary = Path(sys.argv[1]).resolve()
    phase_normal(binary)
    phase_remote_enricher_is_bundled(binary)
    phase_killed_launcher_takes_the_server_with_it(binary)
    print("smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
