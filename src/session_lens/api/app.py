"""FastAPI app factory: `uvicorn session_lens.api.app:create_app --factory`."""

import asyncio
import ipaddress
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram
from prometheus_client.platform_collector import PlatformCollector
from prometheus_client.process_collector import ProcessCollector
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.responses import Response as StarletteResponse
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

import session_lens.web
from session_lens.api.limits import (
    BodySizeLimit,
    RequestTooLarge,
    request_too_large_handler,
)
from session_lens.api.local import LocalOnly
from session_lens.api.logging import setup_logging
from session_lens.api.routers import (
    batches,
    config,
    health,
    sessions,
    stats,
)
from session_lens.api.routers import (
    settings as settings_router,
)
from session_lens.config import Settings, get_settings
from session_lens.db.session import make_engine, read_sessionmaker

log = logging.getLogger("session_lens.api")

_HIDDEN_SUFFIXES = (".py", ".pyc")
# Responses under these prefixes carry recording-derived data: never cache them.
_NO_STORE_PREFIXES = ("/sessions", "/batches", "/stats", "/config", "/settings")


def warn_if_not_loopback(host: str) -> bool:
    """Log a warning when the API is about to listen beyond this machine. Returns True if it
    did. For `session-lens api --host`: the default should be 127.0.0.1; pass 0.0.0.0
    explicitly only where something else (e.g. a container network) limits who can connect."""
    try:
        loopback = host == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = False
    if not loopback:
        logging.getLogger("session_lens.api").warning(
            "listening on a non-loopback address; recordings are sensitive and must not be "
            "reachable from other machines",
            extra={"host": host},
        )
    return not loopback


class WebFiles(StaticFiles):
    """StaticFiles that never serves the package's Python sources."""

    async def get_response(self, path: str, scope: Scope) -> StarletteResponse:
        if path.endswith(_HIDDEN_SUFFIXES):
            return await super().get_response("\0not-found", scope)
        return await super().get_response(path, scope)


def create_app(settings: Settings | None = None, *, run_worker: bool = False) -> FastAPI:
    """`run_worker=True` (what `session-lens serve` does) migrates the database and runs the
    enrichment worker and retention cleanup inside the app's own event loop, so one process is
    the whole service. Tests leave it off and drive the worker themselves."""
    settings = settings or get_settings()
    setup_logging(settings.log_level, settings.log_file, settings.data_dir)

    engine = make_engine(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        stop = asyncio.Event()
        worker: asyncio.Task[None] | None = None
        if run_worker:
            from session_lens.db.migrate import upgrade_async
            from session_lens.runtime_settings import DynamicEnricher
            from session_lens.storage.base import build_store
            from session_lens.worker.loop import run_worker as worker_loop

            await upgrade_async(settings)
            app.state.store = build_store(settings)
            app.state.enricher = DynamicEnricher(app.state.sessionmaker, settings)
            worker = asyncio.create_task(
                worker_loop(
                    app.state.sessionmaker, app.state.store, app.state.enricher, settings, stop
                )
            )
        yield
        if worker is not None:
            stop.set()  # drains: in-flight items get `shutdown_grace_seconds`, then are re-queued
            try:
                await worker
            except Exception as exc:
                log.warning("worker stopped badly", extra={"exc_type": type(exc).__name__})
        store = getattr(app.state, "store", None)  # only set once the lazy provider built it
        try:
            if store is not None:
                await store.aclose()
        except Exception as exc:
            log.warning("store close failed", extra={"exc_type": type(exc).__name__})
        await engine.dispose()

    # No interactive docs: the stock page loads its scripts from a CDN, and nothing may call out.
    app = FastAPI(
        title="session-lens", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.add_exception_handler(RequestTooLarge, request_too_large_handler)
    # Added first, so innermost: counts streamed upload bytes (also for chunked bodies).
    app.add_middleware(BodySizeLimit, max_bytes=settings.max_request_bytes, path="/batches")
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = async_sessionmaker[AsyncSession](engine, expire_on_commit=False)
    app.state.read_sessionmaker = read_sessionmaker(engine)

    registry = CollectorRegistry()
    ProcessCollector(registry=registry)
    PlatformCollector(registry=registry)
    app.state.registry = registry
    app.state.queue_depth = Gauge(
        "session_lens_queue_items",
        "Batch items by status",
        ["status"],
        registry=registry,
    )
    requests_total = Counter(
        "session_lens_http_requests_total",
        "HTTP requests",
        ["method", "route", "status"],
        registry=registry,
    )
    request_seconds = Histogram(
        "session_lens_http_request_seconds",
        "HTTP request latency",
        ["method", "route"],
        registry=registry,
    )

    @app.middleware("http")
    async def observe(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = uuid.uuid4().hex
        started = time.perf_counter()
        status_code = 500
        response: Response
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            # Log the type and file:line frames only (see JsonFormatter); never the message.
            log.error(
                "unhandled exception",
                extra={"request_id": request_id, "method": request.method},
                exc_info=True,
            )
            response = JSONResponse(
                {"detail": "internal server error", "request_id": request_id}, status_code=500
            )
        response.headers["X-Request-ID"] = request_id
        if request.url.path.startswith(_NO_STORE_PREFIXES):
            response.headers["Cache-Control"] = "no-store"
        elapsed = time.perf_counter() - started
        route = getattr(request.scope.get("route"), "path", "unmatched")
        requests_total.labels(request.method, route, str(status_code)).inc()
        request_seconds.labels(request.method, route).observe(elapsed)
        extra: dict[str, Any] = {
            "request_id": request_id,
            "method": request.method,
            "route": route,
            "status": status_code,
            "duration_ms": round(elapsed * 1000, 1),
        }
        log.info("request", extra=extra)
        return response

    app.include_router(health.router)
    app.include_router(batches.router)
    app.include_router(sessions.router)
    app.include_router(stats.router)
    app.include_router(config.router)
    app.include_router(settings_router.router)
    # Added last, so outermost: a request for another host name, or a write from another site's
    # page, is turned away before anything else sees it. It stands in for an API token
    # (api/local.py).
    app.add_middleware(LocalOnly, allowed_hosts=settings.allowed_hosts)

    web_dir = Path(session_lens.web.__file__).parent
    app.mount("/", WebFiles(directory=web_dir, html=True), name="web")
    return app
