---
type: Database Table
title: Table batch_items
description: One row per uploaded file; the unit of work claimed by the worker.
resource: src/lens/db/models.py
tags: [database, table, queue]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/db/models.py, src/lens/migrations/versions/0001_initial_schema.py]
---
| Column | Notes |
|---|---|
| `id` | primary key |
| `batch_id` | FK to batches, `ON DELETE CASCADE`, indexed |
| `filename` | up to 255 characters |
| `status` | `queued`, `running`, `done`, `failed`, `cancelled` |
| `attempts` | incremented at claim |
| `not_before` | backoff time; item is due when null or past |
| `locked_at` | claim time, doubles as the claim token |
| `error`, `error_retryable` | failure text without recording content |
| `raw_id` | FK to raw_recordings, `SET NULL` |
| `session_id` | FK to sessions, `SET NULL`; set when the item finishes |
| `created_at`, `updated_at` | naive UTC |

Index on (`status`, `not_before`) serves the claim query. Behaviour in [worker loop](../packages/worker-loop.md) and [processor](../packages/worker-processor.md).
