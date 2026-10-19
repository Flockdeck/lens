---
type: Module
title: Item processor
description: ItemProcessor turns one claimed batch item into a session and an enrichment in two phases.
resource: src/lens/worker/processor.py
tags: [worker, processing]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/worker/processor.py]
---
`process(claim)` never raises item errors. It runs `_run` under `asyncio.timeout`, then settles the item.

## Phases in `_run`

1. Read the raw bytes ([read_raw](/packages/worker-queue.md)), parse and analyze in a thread, and upsert the session. This commits before any LLM call, so a flaky enricher still leaves a usable unenriched session. If the stored `content_hash` equals the raw hash and an enrichment exists, the item is done without calling the LLM.
2. Call the enricher with no database connection held, then upsert the enrichment in a new transaction.

## Upserts

`upsert_session` keys on `recording_session` (unique). A later upload of the same session overwrites the row in place and `raw_id` points at the newest raw. A concurrent insert is handled with a savepoint: the loser hits the unique key, reloads and updates the winner's row (two attempts). `upsert_enrichment` does the same on `session_id`, and is also used by [POST /sessions/{id}/enrich](/api/sessions-enrich.md).

## Settling

`_settle` and `_release` update the item only `WHERE status = running AND locked_at = <claim token>`; if the claim was taken over, the update matches nothing and logs `claim lost`. Failure handling: [classification](/packages/worker-retry.md). A retryable failure with attempts left goes back to queued with `not_before = now + backoff`; otherwise the item is failed. On cancellation (shutdown) `_release` re-queues the item and decrements `attempts` (not below 0). See [claims and fencing](/gotchas/claim-fencing-and-lock-order.md).
