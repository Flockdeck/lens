import pytest

from session_lens import cli
from session_lens.config import get_settings


def run(*argv):
    return cli.main(list(argv))


def test_check_storage_filesystem(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path / "data"))
    assert run("check-storage") == 0
    out = capsys.readouterr().out
    assert "filesystem" in out and "probe ok" in out
    assert list((tmp_path / "data").iterdir()) == []  # the probe object was removed


def test_check_storage_fails_when_the_directory_is_unusable(tmp_path, monkeypatch, capsys):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setattr(get_settings(), "data_dir", str(blocker / "data"))
    assert run("check-storage") == 1
    assert "probe failed" in capsys.readouterr().out


def test_no_command_means_serve(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "cmd_serve", lambda args: seen.setdefault("args", args) and 0)
    monkeypatch.setattr(
        cli.build_parser().__class__, "parse_args", cli.argparse.ArgumentParser.parse_args
    )
    parser = cli.build_parser()
    assert parser.parse_args([]).command is None  # main() then re-parses as `serve`
    assert parser.parse_args(["serve", "--port", "9"]).port == 9


def test_version_prints_something(capsys):
    assert run("version") == 0
    assert capsys.readouterr().out.strip()


def test_the_old_split_commands_are_gone():
    for old in ("api", "worker", "migrate", "check-bucket"):
        with pytest.raises(SystemExit):
            run(old)
