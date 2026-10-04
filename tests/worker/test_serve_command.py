"""`lens serve` and `cleanup` as commands: what they ask of the pieces they start."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from lens import cli, parent_watch
from lens.config import get_settings
from lens.db.migrate import upgrade


class FakeServer:
    """Stands in for uvicorn.Server so no port is opened."""

    instances: list[FakeServer] = []

    def __init__(self, config: Any) -> None:
        self.config = config
        self.should_exit = False
        self.ran = False
        FakeServer.instances.append(self)

    def run(self) -> None:
        self.ran = True


@pytest.fixture
def fake_uvicorn(monkeypatch: pytest.MonkeyPatch) -> list[FakeServer]:
    import uvicorn

    FakeServer.instances = []
    monkeypatch.setattr(uvicorn, "Server", FakeServer)
    monkeypatch.setattr(cli, "watch_parent", lambda on_gone: False)
    return FakeServer.instances


def test_serve_runs_the_whole_service_on_loopback(
    fake_uvicorn: list[FakeServer], capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["serve"]) == 0
    (server,) = fake_uvicorn
    assert server.ran
    assert server.config.host == "127.0.0.1" and server.config.port == 8000
    assert server.config.app.router is not None  # the FastAPI app, with the worker enabled
    out = capsys.readouterr().out
    assert "http://localhost:8000/" in out and "data:" in out


def test_no_command_means_serve(fake_uvicorn: list[FakeServer]) -> None:
    assert cli.main([]) == 0
    assert fake_uvicorn and fake_uvicorn[0].ran


def test_host_and_port_can_be_chosen(fake_uvicorn: list[FakeServer]) -> None:
    cli.main(["serve", "--host", "::1", "--port", "9123"])
    assert (fake_uvicorn[0].config.host, fake_uvicorn[0].config.port) == ("::1", 9123)


def test_a_non_loopback_host_is_checked_for_a_warning(
    fake_uvicorn: list[FakeServer], monkeypatch: pytest.MonkeyPatch
) -> None:
    from lens.api import app as app_module

    seen: list[str] = []
    monkeypatch.setattr(app_module, "warn_if_not_loopback", lambda host: seen.append(host) or True)
    cli.main(["serve", "--host", "0.0.0.0", "--port", "9124"])  # noqa: S104
    assert seen == ["0.0.0.0"]  # noqa: S104


def test_open_asks_for_a_browser_a_moment_later(
    fake_uvicorn: list[FakeServer], monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []
    started: list[float] = []

    class FakeTimer:
        def __init__(self, delay: float, fn: Any, args: tuple[str, ...]) -> None:
            started.append(delay)
            self.fn, self.args = fn, args

        def start(self) -> None:
            self.fn(*self.args)

    import threading

    monkeypatch.setattr(threading, "Timer", FakeTimer)
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: opened.append(url) or True)
    cli.main(["serve", "--port", "9125", "--open"])
    assert opened == ["http://localhost:9125/"] and started == [1.0]


def test_the_server_is_told_to_stop_when_its_launcher_goes(
    fake_uvicorn: list[FakeServer], monkeypatch: pytest.MonkeyPatch
) -> None:
    callbacks: list[Any] = []
    monkeypatch.setattr(cli, "watch_parent", lambda on_gone: callbacks.append(on_gone) or True)
    cli.main(["serve"])
    assert not fake_uvicorn[0].should_exit
    callbacks[0]()
    assert fake_uvicorn[0].should_exit


def test_cleanup_command_reports_what_it_did(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = get_settings()
    url = f"sqlite+aiosqlite:///{(tmp_path / 'c.db').as_posix()}"
    monkeypatch.setattr(settings, "database_url", url)
    monkeypatch.setattr(settings, "data_dir", str(tmp_path / "data"))
    upgrade(settings)
    assert cli.main(["cleanup"]) == 0
    assert "expired 0 raw recordings, deleted 0 batches" in capsys.readouterr().out


class TestWatchParent:
    def test_it_leaves_alone_a_parent_that_is_some_other_program(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(parent_watch.os, "getppid", lambda: 4242)
        monkeypatch.setattr(
            parent_watch, "_windows_parent_image", lambda pid: r"C:\Windows\cmd.exe"
        )
        monkeypatch.setattr(parent_watch, "_unix_parent_image", lambda pid: "/bin/zsh")
        assert parent_watch.watch_parent(lambda: None) is False

    def test_it_does_nothing_without_a_parent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(parent_watch.os, "getppid", lambda: 1)
        assert parent_watch.watch_parent(lambda: None) is False

    def test_it_calls_back_when_a_launcher_of_the_same_program_goes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import sys
        import threading

        done = threading.Event()
        me = sys.executable
        monkeypatch.setattr(parent_watch.os, "getppid", lambda: 4242)
        monkeypatch.setattr(parent_watch, "_windows_parent_image", lambda pid: me)
        monkeypatch.setattr(parent_watch, "_unix_parent_image", lambda pid: me)
        monkeypatch.setattr(parent_watch, "_windows_wait_for_exit", lambda pid: None)
        # On Unix the watcher polls getppid(); make the parent disappear after the first look.
        calls = iter([4242, 1, 1, 1])
        real = parent_watch.os.getppid
        monkeypatch.setattr(parent_watch.os, "getppid", lambda: next(calls, 1))
        monkeypatch.setattr(parent_watch.time, "sleep", lambda s: None)
        assert parent_watch.watch_parent(done.set) is True
        assert done.wait(5)
        assert real is not None
