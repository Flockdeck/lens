---
type: Module
title: Retention cleanup
description: run_cleanup deletes raw recording files past retention and removes old finished batches.
resource: src/lens/worker/cleanup.py
tags: [worker, retention]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/worker/cleanup.py]
---
- `expire_raws(sm, store, retention_days)`: when the days are 0 or less it does nothing. Otherwise, in chunks of 1000 by id, it takes raws created before the cutoff and not yet expired, skipping any raw that a queued or running item still needs, deletes each stored file (best effort, a missing file is fine) and sets `expired_at`. The session, metrics and enrichment are kept.
- `delete_old_batches`: deletes batches that are `done` or `cancelled`, older than 90 days (`BATCH_RETENTION_DAYS`) with no queued or running item, 1000 at a time; items go by cascade.
- `run_cleanup` holds a module-level `asyncio.Lock`; if it is already held it returns `CleanupResult(skipped=True)`. The lock is per process, not a database lock.

Triggered by the worker timer ([CLEANUP_INTERVAL_SECONDS](../config/cleanup-interval-seconds.md)) and by [lens cleanup](../cli/cleanup.md). The age is [RAW_RETENTION_DAYS](../config/raw-retention-days.md).
