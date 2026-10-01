"""FastAPI app factory: `uvicorn session_lens.api.app:create_app --factory`."""

import logging
import os
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram
from prometheus_client.platform_collector import PlatformCollector
from prometheus_client.process_collector import ProcessCollector
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.responses import Response as StarletteResponse
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

import session_lens.web
from session_lens.api.deps import require_token
from session_lens.api.limits import (
    BodySizeLimit,
    RequestTooLarge,
    request_too_large_handler,
)
from session_lens.api.logging import setup_logging
from session_lens.api.routers import batches, health, sessions, stats
from session_lens.config import Settings, get_settings

log = logging.getLogger("session_lens.api")

_HIDDEN_SUFFIXES = (".py", ".pyc")
_DEFAULT_TOKEN = "dev-token"  # the Settings default; never acceptable outside local dev


def insecure_dev_allowed() -> bool:
    return os.environ.get("ALLOW_INSECURE_DEV") == "1"


class WebFiles(StaticFiles):
    """StaticFiles that never serves the package's Python sources."""

    async def get_response(self, path: str, scope: Scope) -> StarletteResponse:
        if path.endswith(_HIDDEN_SUFFIXES):
            return await super().get_response("\0not-found", scope)
        return await super().get_response(path, scope)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)
    dev_mode = insecure_dev_allowed()
    if not settings.api_token or (settings.api_token == _DEFAULT_TOKEN and not dev_mode):
        raise RuntimeError(
            "API_TOKEN is unset or still the default 'dev-token'. Set a real API_TOKEN, or set "
            "ALLOW_INSECURE_DEV=1 to run locally with the default token."
        )

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        store = getattr(app.state, "store", None)  # only set once the lazy provider built it
        try:
            if store is not None:
                await store.aclose()
        except Exception as exc:
            log.warning("store close failed", extra={"exc_type": type(exc).__name__})
        await engine.dispose()

    # Interactive docs and the schema are only exposed in explicit dev mode.
    app = FastAPI(
        title="session-lens",
        lifespan=lifespan,
        docs_url="/docs" if dev_mode else None,
        redoc_url=None,
        openapi_url="/openapi.json" if dev_mode else None,
    )
    app.add_exception_handler(RequestTooLarge, request_too_large_handler)
    # Added first, so innermost: counts streamed upload bytes (also for chunked bodies).
    app.add_middleware(BodySizeLimit, max_bytes=settings.max_request_bytes, path="/batches")
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = async_sessionmaker[AsyncSession](engine, expire_on_commit=False)

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

    auth = [Depends(require_token)]
    app.include_router(health.router)
    app.include_router(batches.router, dependencies=auth)
    app.include_router(sessions.router, dependencies=auth)
    app.include_router(stats.router, dependencies=auth)

    web_dir = Path(session_lens.web.__file__).parent
    app.mount("/", WebFiles(directory=web_dir, html=True), name="web")
    return app
