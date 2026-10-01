"""`session-lens api|worker|cleanup|migrate`."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import uuid
from collections.abc import Sequence
from pathlib import Path

from session_lens.config import Settings, get_settings
from session_lens.storage.base import build_store
from session_lens.worker.cleanup import CleanupResult

API_APP = "session_lens.api.app:create_app"  # the api component's app factory

_STD_ATTRS = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Extras are ids and counts only, by convention."""

    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, object] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        out.update({k: v for k, v in vars(record).items() if k not in _STD_ATTRS})
        if record.exc_info:
            out["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        return json.dumps(out, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level.upper(), handlers=[handler], force=True)
    logging.getLogger("alembic").setLevel(logging.WARNING)


def cmd_api(args: argparse.Namespace) -> int:
    import uvicorn

    from session_lens.api.app import warn_if_not_loopback

    warn_if_not_loopback(args.host)
    uvicorn.run(API_APP, factory=True, host=args.host, port=args.port, log_config=None)
    return 0


def _install_signal_handlers(stop: asyncio.Event) -> None:
    """First SIGINT/SIGTERM starts a graceful drain; a second one exits immediately (claims
    left behind go stale and are recovered by the next worker)."""
    count = 0

    def handle(*_: object) -> None:
        nonlocal count
        count += 1
        if count == 1:
            stop.set()
        else:
            os._exit(1)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle)
        except NotImplementedError:  # Windows
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(handle))


async def _worker() -> None:
    from session_lens.db.session import dispose_engine, get_sessionmaker
    from session_lens.enrich.base import build_enricher
    from session_lens.storage.base import build_store
    from session_lens.worker.loop import run_worker

    settings = get_settings()
    stop = asyncio.Event()
    _install_signal_handlers(stop)
    store = build_store(settings)
    try:
        await run_worker(get_sessionmaker(), store, build_enricher(settings), settings, stop)
    finally:
        await store.aclose()
        await dispose_engine()


def cmd_worker(_: argparse.Namespace) -> int:
    asyncio.run(_worker())
    return 0


async def _cleanup() -> CleanupResult:
    from session_lens.db.session import dispose_engine, get_sessionmaker
    from session_lens.storage.base import build_store
    from session_lens.worker.cleanup import run_cleanup

    settings = get_settings()
    store = build_store(settings)
    try:
        return await run_cleanup(get_sessionmaker(), store, settings.raw_retention_days)
    finally:
        await store.aclose()
        await dispose_engine()


def cmd_cleanup(_: argparse.Namespace) -> int:
    result = asyncio.run(_cleanup())
    if result.skipped:
        print("cleanup skipped: another run holds the lock")
    else:
        print(
            f"expired {result.raws_expired} raw recordings, "
            f"deleted {result.batches_deleted} batches"
        )
    return 0


def _alembic_ini() -> Path:
    ini = Path(__file__).resolve().parents[2] / "alembic.ini"  # repo root
    return ini if ini.exists() else Path("alembic.ini")  # installed image: working directory


EXIT_OUTDATED = 1
EXIT_UNREACHABLE = 2


async def _db_revision() -> str | None:
    """The revision in alembic_version, or None if the table does not exist yet. Raises
    OperationalError-family errors if the database is unreachable."""
    from sqlalchemy import text
    from sqlalchemy.exc import ProgrammingError

    from session_lens.db.session import dispose_engine, get_engine

    try:
        async with get_engine().connect() as conn:
            try:
                return (
                    await conn.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar()
            except ProgrammingError:  # no alembic_version table: never migrated
                return None
    finally:
        await dispose_engine()


def cmd_migrate(args: argparse.Namespace) -> int:
    ini = _alembic_ini()
    if args.check:
        # Exit 0 only when the database is at head; 1 if the schema is outdated or missing;
        # 2 if the database is unreachable. For init containers that wait for the schema.
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from sqlalchemy.exc import SQLAlchemyError

        head = ScriptDirectory.from_config(Config(str(ini))).get_current_head()
        try:
            current = asyncio.run(_db_revision())
        except (SQLAlchemyError, OSError) as exc:
            print(f"database unreachable ({type(exc).__name__})")
            return EXIT_UNREACHABLE
        if current == head:
            print(f"up to date at {head}")
            return 0
        print(f"outdated: database at {current}, head is {head}")
        return EXIT_OUTDATED
    return subprocess.call(
        [sys.executable, "-m", "alembic", "-c", str(ini), "upgrade", "head"], cwd=ini.parent
    )


async def _check_bucket(strict: bool) -> int:
    settings = get_settings()
    if settings.storage != "s3":
        print(f"not applicable: STORAGE={settings.storage} (this check is for the s3 store)")
        return 0
    from session_lens.storage.s3 import S3Store

    store = build_store(settings)
    assert isinstance(store, S3Store)
    try:
        days = await store.expiry_days(settings.s3_prefix)
    except Exception as exc:  # unreachable, bad credentials, no such bucket
        print(f"bucket check failed ({type(exc).__name__})")
        return 2
    finally:
        await store.aclose()
    if days is not None and days <= settings.raw_retention_days:
        print(f"ok: objects under {settings.s3_prefix} expire after {days} days")
        return 0
    found = "no expiry rule" if days is None else f"an expiry rule of {days} days"
    message = (
        f"bucket has {found} for prefix {settings.s3_prefix}; "
        f"expected one of at most {settings.raw_retention_days} days"
    )
    logging.getLogger(__name__).warning(message)
    print(f"warning: {message}")
    return 1 if strict else 0


def cmd_check_bucket(args: argparse.Namespace) -> int:
    return asyncio.run(_check_bucket(args.strict))


def _describe_store(settings: Settings) -> str:
    if settings.storage == "s3":
        return f"s3 endpoint={settings.s3_endpoint_url} bucket={settings.s3_bucket}"
    return f"filesystem dir={Path(settings.data_dir).resolve()}"


async def _check_storage() -> int:
    """Put, get and delete a tiny probe object in the configured store."""
    settings = get_settings()
    print(f"storage: {_describe_store(settings)}")
    store = build_store(settings)
    key = f"{settings.s3_prefix}probe/{uuid.uuid4()}.jsonl"
    probe = b'{"probe":true}'
    try:
        await store.ping()
        await store.put(key, probe)
        try:
            if await store.get(key) != probe:
                print("probe failed: read back different bytes")
                return 1
        finally:
            await store.delete(key)
    except Exception as exc:
        print(f"probe failed ({type(exc).__name__})")
        return 1
    finally:
        await store.aclose()
    print("probe ok: put, get and delete work")
    return 0


def cmd_check_storage(_: argparse.Namespace) -> int:
    return asyncio.run(_check_storage())


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="session-lens")
    sub = parser.add_subparsers(dest="command", required=True)
    api = sub.add_parser(
        "api",
        help="serve the HTTP API and web UI",
        description=(
            "Serve the HTTP API and web UI. The app refuses to start with an empty or default "
            "API_TOKEN unless ALLOW_INSECURE_DEV=1 is set (local development only)."
        ),
    )
    api.add_argument(
        "--host", default="127.0.0.1", help="bind address (default: this machine only)"
    )
    api.add_argument("--port", type=int, default=8000)
    api.set_defaults(func=cmd_api)
    sub.add_parser("worker", help="run the batch item worker").set_defaults(func=cmd_worker)
    sub.add_parser(
        "cleanup",
        help="delete raw recordings past retention and old finished batches (the worker also "
        "does this on a timer; use this for a manual run)",
    ).set_defaults(func=cmd_cleanup)
    sub.add_parser(
        "check-storage",
        help="show the configured store and verify put/get/delete of a probe object (exit 0/1)",
    ).set_defaults(func=cmd_check_storage)
    check_help = (
        "s3 store only: warn if the bucket has no expiry rule within raw_retention_days "
        "(the app deletes expired files itself; a rule only sweeps orphans from failed uploads)"
    )
    check = sub.add_parser("check-bucket", help=check_help, description=check_help)
    check.add_argument("--strict", action="store_true", help="exit 1 if the rule is missing")
    check.set_defaults(func=cmd_check_bucket)
    migrate = sub.add_parser("migrate", help="alembic upgrade head")
    migrate.add_argument(
        "--check",
        action="store_true",
        help="exit 0 only if the database is at head; change nothing",
    )
    migrate.set_defaults(func=cmd_migrate)
    args = parser.parse_args(argv)
    configure_logging(get_settings().log_level)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
