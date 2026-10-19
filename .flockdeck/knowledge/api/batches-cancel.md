---
type: HTTP Endpoint
title: POST /batches/{batch_id}/cancel
description: Cancels the queued items of a batch and marks the batch cancelled.
resource: src/lens/api/routers/batches.py
tags: [api, batches]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/routers/batches.py, src/lens/worker/queue.py]
---
404 if missing. Queued items become `cancelled`; running items finish normally. The batch status is set to `cancelled` and stays so until a [retry](batches-retry.md) of failed items. Returns `BatchOut`.
