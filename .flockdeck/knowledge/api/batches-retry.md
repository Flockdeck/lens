---
type: HTTP Endpoint
title: POST /batches/{batch_id}/retry
description: Re-queues the failed items of a batch.
resource: src/lens/api/routers/batches.py
tags: [api, batches]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/routers/batches.py, src/lens/worker/queue.py]
---
404 if the batch does not exist. Otherwise runs `retry_failed` ([queue](../packages/worker-queue.md)): failed items return to `queued` with attempts reset to 0; a cancelled batch is brought back to a computed status. Returns the updated `BatchOut` ([GET](batches-get.md)). Items not failed are untouched.
