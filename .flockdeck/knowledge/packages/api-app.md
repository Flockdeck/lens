---
type: Module
title: FastAPI app factory
description: create_app builds the FastAPI application, its middleware, metrics and optional in-process worker.
resource: src/lens/api/app.py
tags: [api, fastapi]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/app.py]
---
`create_app(settings=None, *, run_worker=False)` returns the app. It is also usable as `uvicorn lens.api.app:create_app --factory`.

## What it sets up

- `setup_logging` and one SQLAlchemy engine from [db session](db-session.md). The app state holds `settings`, `engine`, `sessionmaker` (writes), `read_sessionmaker` (GET and HEAD) and a Prometheus `registry`.
- Interactive docs are off: `docs_url`, `redoc_url` and `openapi_url` are `None` (see [no docs endpoints](../security/no-interactive-docs.md)).
- Middleware, innermost first: [BodySizeLimit](api-limits.md) for `POST /batches`, the `observe` HTTP middleware, then [LocalOnly](api-local.md) as the outermost layer.
- Routers: health, batches, sessions, stats, config, settings. The static web UI is mounted at `/` last, through `WebFiles`.

## Lifespan

With `run_worker=True` (what [serve](../cli/serve.md) passes) startup runs `upgrade_async` ([migrations](db-migrate.md)), builds the file store, creates a `DynamicEnricher` ([runtime settings](runtime-settings.md)) and starts the [worker loop](worker-loop.md) as an asyncio task. On shutdown it sets the stop event, awaits the worker (in-flight items get the grace period), closes the store if one was built, and disposes the engine. Tests leave `run_worker` off.

## observe middleware

Each request gets a random hex `X-Request-ID`. Unhandled exceptions are logged with type and frames only and answered with 500 `{"detail": "internal server error", "request_id": ...}`. Paths starting with `/sessions`, `/batches`, `/stats`, `/config` or `/settings` get `Cache-Control: no-store`. Metrics: `lens_http_requests_total{method,route,status}`, `lens_http_request_seconds{method,route}`, gauge `lens_queue_items{status}`; the route label is the matched route path or `unmatched`. One `request` log line per call, carrying route (not the URL), status and `duration_ms`.

## WebFiles

A `StaticFiles` subclass that returns 404 for `.py` and `.pyc` paths (the web directory is a Python package) and sets `Cache-Control: no-cache` on everything, so an upgraded binary never serves old scripts.

`warn_if_not_loopback(host)` logs a warning and returns True when the bind host is not loopback ([non-loopback bind](../security/loopback-bind.md)).
