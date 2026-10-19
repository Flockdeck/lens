---
type: Module
title: Batch queue helpers
description: Shared functions to store raw files, create, retry and cancel batches, and roll item statuses up into the batch status.
resource: src/lens/worker/queue.py
tags: [worker, queue]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/worker/queue.py]
---
- `new_object_key(prefix)` gives `<prefix>YYYY/MM/<uuid>.jsonl` ([object key](../tables/object-key.md)).
- `store_raw` computes the SHA-256, puts the file first and only then adds and flushes the [raw_recordings](../tables/table-raw-recordings.md) row, so a row never points at a missing file. A failure after the put leaves an unreferenced file, which is harmless.
- `read_raw` returns the bytes; for an expired or missing row, or a missing object, it raises `RecordingExpired` (setting `expired_at` in the missing-object case).
- `create_batch` makes a queued batch with one queued item per `(filename, content)`; filenames are cut to 255.
- `refresh_batch_status`: `cancelled` is sticky; else no queued or running items means `done`, all items queued means `queued`, anything else `running`.
- `retry_failed` re-queues failed items (attempts 0, error and backoff cleared) and recomputes the batch status, which also lifts a sticky `cancelled`. Returns the count.
- `cancel_batch` cancels queued items only, leaves running ones to finish, and marks the batch cancelled.
- `delete_raws_for_session` deletes the objects (best effort) and rows of the session's own raw and of every batch item raw that produced it.

Lock order comment: item rows first, then the batch row. See [claims and fencing](../gotchas/claim-fencing-and-lock-order.md).
