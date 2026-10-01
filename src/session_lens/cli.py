"""`session-lens api|worker|cleanup|migrate`."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from session_lens.config import get_settings
from session_lens.worker.cleanup import CleanupResult

API_APP = "session_lens.api.main:app"  # the api component's ASGI app

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

    uvicorn.run(API_APP, host=args.host, port=args.port, log_config=None)
    return 0


async def _worker() -> None:
    from session_lens.db.session import dispose_engine, get_sessionmaker
    from session_lens.enrich.base import build_enricher
    from session_lens.storage.base import build_store
    from session_lens.worker.loop import run_worker

    settings = get_settings()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))
    try:
        await run_worker(
            get_sessionmaker(), build_store(settings), build_enricher(settings), settings, stop
        )
    finally:
        await dispose_engine()


def cmd_worker(_: argparse.Namespace) -> int:
    asyncio.run(_worker())
    return 0


async def _cleanup() -> CleanupResult:
    from session_lens.db.session import dispose_engine, get_sessionmaker
    from session_lens.worker.cleanup import run_cleanup

    try:
        return await run_cleanup(get_sessionmaker(), get_settings().raw_retention_days)
    finally:
        await dispose_engine()


def cmd_cleanup(_: argparse.Namespace) -> int:
    result = asyncio.run(_cleanup())
    print(f"expired {result.raws_expired} raw recordings, deleted {result.batches_deleted} batches")
    return 0


def _alembic_ini() -> Path:
    ini = Path(__file__).resolve().parents[2] / "alembic.ini"  # repo root
    return ini if ini.exists() else Path("alembic.ini")  # installed image: working directory


async def _db_revision() -> str | None:
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from session_lens.db.session import dispose_engine, get_engine

    try:
        async with get_engine().connect() as conn:
            return (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar()
    except DBAPIError:  # unreachable DB or no alembic_version table yet
        return None
    finally:
        await dispose_engine()


def cmd_migrate(args: argparse.Namespace) -> int:
    ini = _alembic_ini()
    if args.check:
        # Exit 0 only when the database is at the head revision; for init containers that
        # wait for the schema.
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config(str(ini))
        head = ScriptDirectory.from_config(cfg).get_current_head()
        current = asyncio.run(_db_revision())
        print(f"head={head} current={current}")
        return 0 if current == head else 1
    return subprocess.call(
        [sys.executable, "-m", "alembic", "-c", str(ini), "upgrade", "head"], cwd=ini.parent
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="session-lens")
    sub = parser.add_subparsers(dest="command", required=True)
    api = sub.add_parser("api", help="serve the HTTP API and web UI")
    api.add_argument("--host", default="0.0.0.0")  # noqa: S104
    api.add_argument("--port", type=int, default=8000)
    api.set_defaults(func=cmd_api)
    sub.add_parser("worker", help="run the batch item worker").set_defaults(func=cmd_worker)
    sub.add_parser(
        "cleanup", help="mark raw recordings past retention expired; delete old batches"
    ).set_defaults(func=cmd_cleanup)
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
