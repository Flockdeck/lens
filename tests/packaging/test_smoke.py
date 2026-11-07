"""packaging/smoke.py: the clean-up of a server the killed-launcher phase could not stop."""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

PACKAGING = Path(__file__).resolve().parents[2] / "packaging"
sys.path.insert(0, str(PACKAGING))

import smoke  # noqa: E402

NETSTAT = """
Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       1000
  TCP    127.0.0.1:8000         0.0.0.0:0              LISTENING       4242
  TCP    127.0.0.1:18000        0.0.0.0:0              LISTENING       5555
  TCP    127.0.0.1:8000         127.0.0.1:50000        ESTABLISHED     4242
  TCP    [::]:8000              [::]:0                 LISTENING       4343
"""


def test_listener_pids_reads_only_listeners_on_that_exact_port() -> None:
    assert smoke.listener_pids(8000, NETSTAT) == {4242, 4343}
    assert smoke.listener_pids(80, NETSTAT) == set()


def test_kill_listener_stops_a_server_holding_a_port() -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    code = (
        f"import socket,time;s=socket.socket();s.bind(('127.0.0.1',{port}));s.listen();"
        "print('up',flush=True);time.sleep(60)"
    )
    child = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE)  # noqa: S603
    try:
        assert child.stdout is not None
        assert child.stdout.readline().strip() == b"up"
        smoke.kill_listener(port)
        deadline = time.monotonic() + 10
        while child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.1)
        assert child.poll() is not None
    finally:
        child.kill()
        child.wait()
