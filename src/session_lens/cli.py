"""`session-lens [serve|cleanup|check-storage|version]`. With no command it serves."""

from __future__ import annotations

import argparse
import asyncio
import logging
import uuid
import webbrowser
from collections.abc import Sequence
from pathlib import Path

from session_lens._version import app_version
from session_lens.api.logging import setup_logging
from session_lens.config import Settings, get_settings
from session_lens.parent_watch import watch_parent
from session_lens.storage.base import build_store


def configure_logging(settings: Settings) -> None:
    setup_logging(settings.log_level, settings.log_file, settings.data_dir)
    logging.getLogger("alembic").setLevel(logging.WARNING)


def cmd_serve(args: argparse.Namespace) -> int:
    """The whole service in this process: web UI, API, enrichment worker and retention."""
    import uvicorn

    from session_lens.api.app import create_app, warn_if_not_loopback

    settings = get_settings()
    host = args.host or settings.host
    port = args.port or settings.port
    warn_if_not_loopback(host)
    url = f"http://{'localhost' if host in ('127.0.0.1', '::1') else host}:{port}/"
    print(f"session-lens {app_version()} at {url}", flush=True)
    print(f"data: {Path(settings.data_dir).expanduser()}", flush=True)
    if args.open:
        # Opened a moment after the server starts listening, not before.
        import threading

        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    server = uvicorn.Server(
        uvicorn.Config(create_app(settings, run_worker=True), host=host, port=port, log_config=None)
    )
    # If whatever launched this program is killed, stop too (see parent_watch).
    watch_parent(lambda: setattr(server, "should_exit", True))
    server.run()
    return 0


def cmd_version(_: argparse.Namespace) -> int:
    print(app_version())
    return 0


async def _cleanup() -> str:
    from session_lens.db.migrate import upgrade_async
    from session_lens.db.session import dispose_engine, get_sessionmaker
    from session_lens.worker.cleanup import run_cleanup

    settings = get_settings()
    await upgrade_async(settings)
    store = build_store(settings)
    try:
        result = await run_cleanup(get_sessionmaker(), store, settings.raw_retention_days)
    finally:
        await store.aclose()
        await dispose_engine()
    if result.skipped:
        return "cleanup skipped: another run is in progress"
    return f"expired {result.raws_expired} raw recordings, deleted {result.batches_deleted} batches"


def cmd_cleanup(_: argparse.Namespace) -> int:
    """Not needed day to day: `serve` runs this on a timer. For a manual run."""
    print(asyncio.run(_cleanup()))
    return 0


async def _check_storage() -> int:
    """Put, get and delete a tiny probe file in the data directory."""
    settings = get_settings()
    print(f"data directory: {settings.data_dir}")
    store = build_store(settings)
    key = f"{settings.store_prefix}probe/{uuid.uuid4()}.jsonl"
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="session-lens",
        description=(
            "Reads Flockdeck pane recordings, computes metrics, optionally enriches them with an "
            "LLM, and shows them in a web UI. With no command it serves. There is no API key: the "
            "service is for this machine only, and refuses requests addressed to any other host "
            "name or sent by a page on another origin (see ALLOWED_HOSTS)."
        ),
    )
    sub = parser.add_subparsers(dest="command")
    serve = sub.add_parser("serve", help="run the service (the default)")
    serve.add_argument("--host", help="bind address (default 127.0.0.1: this machine only)")
    serve.add_argument("--port", type=int, help="port (default 8000)")
    serve.add_argument("--open", action="store_true", help="open the web UI in a browser")
    serve.set_defaults(func=cmd_serve)
    sub.add_parser("version", help="print the version").set_defaults(func=cmd_version)
    sub.add_parser(
        "cleanup",
        help="delete raw recordings past retention now (serve also does this on a timer)",
    ).set_defaults(func=cmd_cleanup)
    sub.add_parser(
        "check-storage",
        help="verify the data directory is writable and readable (exit 0/1)",
    ).set_defaults(func=cmd_check_storage)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not hasattr(args, "func"):  # no command: serve
        args = build_parser().parse_args(["serve", *(argv or [])])
    configure_logging(get_settings())
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
