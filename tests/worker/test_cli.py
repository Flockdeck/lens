import argparse

import pytest

from session_lens import cli
from session_lens.config import get_settings


def run(*argv):
    return cli.main(list(argv))


def test_migrate_check_up_to_date(monkeypatch, capsys):
    async def at_head():
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        return ScriptDirectory.from_config(Config(str(cli._alembic_ini()))).get_current_head()

    monkeypatch.setattr(cli, "_db_revision", at_head)
    assert run("migrate", "--check") == 0
    assert "up to date" in capsys.readouterr().out


def test_migrate_check_outdated(monkeypatch, capsys):
    async def stale():
        return None

    monkeypatch.setattr(cli, "_db_revision", stale)
    assert run("migrate", "--check") == cli.EXIT_OUTDATED == 1
    assert "outdated" in capsys.readouterr().out


def test_migrate_check_unreachable(monkeypatch, capsys):
    from sqlalchemy.exc import OperationalError

    async def down():
        raise OperationalError("select 1", {}, Exception("refused"))

    monkeypatch.setattr(cli, "_db_revision", down)
    assert run("migrate", "--check") == cli.EXIT_UNREACHABLE == 2
    assert "unreachable" in capsys.readouterr().out


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


def test_check_bucket_is_not_applicable_to_the_filesystem_store(capsys):
    assert run("check-bucket", "--strict") == 0
    assert "not applicable" in capsys.readouterr().out


def test_check_bucket_help_says_it_is_s3_only(capsys):
    with pytest.raises(SystemExit):
        run("check-bucket", "--help")
    assert "s3 store only" in capsys.readouterr().out


def test_check_bucket_s3_unreachable(monkeypatch):
    pytest.importorskip("aioboto3")
    monkeypatch.setattr(get_settings(), "storage", "s3")
    monkeypatch.setattr(get_settings(), "s3_endpoint_url", "http://127.0.0.1:1")
    assert run("check-bucket", "--strict") == 2


def test_check_bucket_s3_rule(s3_store_sync, monkeypatch, capsys):
    monkeypatch.setattr(get_settings(), "storage", "s3")
    assert run("check-bucket", "--strict") == 0  # s3-init applied a 30-day rule
    monkeypatch.setattr(get_settings(), "raw_retention_days", 7)  # the rule is 30 days
    assert run("check-bucket", "--strict") == 1
    assert run("check-bucket") == 0  # a warning only, without --strict


def test_api_help_mentions_the_token_guard(capsys):
    with pytest.raises(SystemExit):
        run("api", "--help")
    out = capsys.readouterr().out
    assert "ALLOW_INSECURE_DEV" in out and "API_TOKEN" in out


def test_api_binds_to_this_machine_by_default(monkeypatch):
    import uvicorn

    calls = {}
    monkeypatch.setattr(uvicorn, "run", lambda *a, **kw: calls.update(args=a, kw=kw))
    run("api")
    assert calls["args"] == ("session_lens.api.app:create_app",)
    assert calls["kw"]["factory"] is True
    assert calls["kw"]["host"] == "127.0.0.1"


def test_api_host_can_be_overridden(monkeypatch):
    import uvicorn

    calls = {}
    monkeypatch.setattr(uvicorn, "run", lambda *a, **kw: calls.update(kw=kw))
    cli.cmd_api(argparse.Namespace(host="0.0.0.0", port=9000))
    assert calls["kw"]["host"] == "0.0.0.0" and calls["kw"]["port"] == 9000
