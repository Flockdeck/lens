---
type: Module
title: API dependencies
description: FastAPI dependencies for settings, per-request database sessions, and lazily built store, queue and enricher providers.
resource: src/lens/api/deps.py
tags: [api, dependency-injection]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/deps.py]
---
- `get_app_settings` returns `app.state.settings`.
- `get_db` yields one `AsyncSession` per request. GET and HEAD requests use `read_sessionmaker` (deferred transactions, never take the write lock); every other method uses the write sessionmaker. See [SQLite transactions](../gotchas/sqlite-begin-immediate.md).
- `QueueApi` is a Protocol with `create_batch`, `store_raw`, `retry_failed`, `cancel_batch`, `delete_raws_for_session` and `upsert_enrichment`. `_WorkerQueue` implements it by importing [worker queue](worker-queue.md) and [processor](worker-processor.md) lazily, so the API module loads without them. `get_queue` returns it.
- `get_store_provider` and `get_enricher_provider` return callables that build the [file store](storage.md) or the `DynamicEnricher` on first use and cache it on `app.state`. A bad configuration then fails only the handler that needs it.
- `provide_or_503(provider, what)` calls a provider; any exception is logged (type name only) and becomes HTTP 503 `"<what> unavailable"`.
