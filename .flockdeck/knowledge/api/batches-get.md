---
type: HTTP Endpoint
title: GET /batches/{batch_id}
description: Returns a batch with per-status item counts and its items.
resource: src/lens/api/routers/batches.py
tags: [api, batches]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/routers/batches.py]
---
Returns `BatchOut`: `id`, `status` (`queued`, `running`, `done`, `cancelled`), `counts` (one key per item status: `queued`, `running`, `done`, `failed`, `cancelled`) and `items` ordered by id with `filename`, `status`, `attempts`, `error` (never recording content), `session_id`. 404 `batch not found` when missing. Read-only, so it uses a deferred database session ([API deps](/packages/api-deps.md)). The UI polls it while items are active ([batch view](/packages/web-views.md)).
