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


def test_check_bucket_ok_and_strict(capsys):
    assert run("check-bucket", "--strict") == 0  # s3-init applied a 30-day rule
    assert "ok" in capsys.readouterr().out


def test_check_bucket_warns_and_strict_fails(monkeypatch, capsys):
    monkeypatch.setattr(get_settings(), "s3_prefix", "unruled/")
    assert run("check-bucket") == 0
    assert "warning" in capsys.readouterr().out
    assert run("check-bucket", "--strict") == 1


def test_check_bucket_rule_longer_than_retention_is_a_warning(monkeypatch):
    monkeypatch.setattr(get_settings(), "raw_retention_days", 7)  # the rule is 30 days
    assert run("check-bucket", "--strict") == 1


def test_check_bucket_unreachable(monkeypatch):
    monkeypatch.setattr(get_settings(), "s3_endpoint_url", "http://127.0.0.1:1")
    assert run("check-bucket", "--strict") == 2


def test_api_help_mentions_the_token_guard(capsys):
    with pytest.raises(SystemExit):
        run("api", "--help")
    out = capsys.readouterr().out
    assert "ALLOW_INSECURE_DEV" in out and "API_TOKEN" in out


def test_api_uses_the_app_factory(monkeypatch):
    import uvicorn

    calls = {}
    monkeypatch.setattr(uvicorn, "run", lambda *a, **kw: calls.update(args=a, kw=kw))
    cli.cmd_api(argparse.Namespace(host="127.0.0.1", port=1234))
    assert calls["args"] == ("session_lens.api.app:create_app",)
    assert calls["kw"]["factory"] is True
