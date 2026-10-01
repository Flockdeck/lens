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


def cmd_api(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(API_APP, host=args.host, port=args.port, log_config=None)
    return 0


async def _worker() -> None:
    from session_lens.db.session import dispose_engine, get_sessionmaker
    from session_lens.enrich.base import build_enricher
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
        await run_worker(get_sessionmaker(), build_enricher(settings), settings, stop)
    finally:
        await dispose_engine()


def cmd_worker(_: argparse.Namespace) -> int:
    asyncio.run(_worker())
    return 0


async def _cleanup() -> int:
    from session_lens.db.session import dispose_engine, get_sessionmaker
    from session_lens.worker.cleanup import cleanup_raw

    try:
        return await cleanup_raw(get_sessionmaker(), get_settings().raw_retention_days)
    finally:
        await dispose_engine()


def cmd_cleanup(_: argparse.Namespace) -> int:
    deleted = asyncio.run(_cleanup())
    print(f"deleted {deleted} raw recordings")
    return 0


def cmd_migrate(_: argparse.Namespace) -> int:
    root = Path(__file__).resolve().parents[2]  # alembic.ini lives at the repo root
    ini = root / "alembic.ini"
    if not ini.exists():  # installed image: fall back to the working directory
        ini = Path("alembic.ini")
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
    sub.add_parser("cleanup", help="delete raw recordings past retention").set_defaults(
        func=cmd_cleanup
    )
    sub.add_parser("migrate", help="alembic upgrade head").set_defaults(func=cmd_migrate)
    args = parser.parse_args(argv)
    configure_logging(get_settings().log_level)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
