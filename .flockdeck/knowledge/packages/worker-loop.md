---
type: Module
title: Worker claim loop
description: run_worker claims due items, runs them with bounded concurrency, sweeps stale claims and drains on shutdown.
resource: src/lens/worker/loop.py
tags: [worker, queue]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/worker/loop.py]
---
Settings used: [WORKER_CONCURRENCY](../config/worker-concurrency.md), [WORKER_POLL_SECONDS](../config/worker-poll-seconds.md), [MAX_ATTEMPTS](../config/max-attempts.md), [CLAIM_TIMEOUT_SECONDS](../config/claim-timeout-seconds.md), [SHUTDOWN_GRACE_SECONDS](../config/shutdown-grace-seconds.md), [CLEANUP_INTERVAL_SECONDS](../config/cleanup-interval-seconds.md).

- `claim_items(sm, limit)` selects queued items that are due (`not_before` null or past), ordered by id, sets them `running` with `locked_at = now` and increments `attempts` (counted at claim, so an item that kills the process still runs out of attempts), refreshes batch statuses and commits. Returns `Claim` records.
- `recover_stale` runs every 30 s: running items whose `locked_at` is older than the claim timeout get error `claim timed out` and go back to queued, or to failed when attempts are used up.
- `run_worker` loop: sweep when due, claim `concurrency - inflight` items, start an [ItemProcessor](worker-processor.md) task per claim, then wait for a slot to free, the poll interval, or the stop event. Claim errors are logged and the loop continues.
- Item timeout is `0.9 * claim_timeout_seconds`, so an item ends before its claim can look stale.
- On stop: wait up to the grace period for in-flight tasks, then cancel the rest; each cancelled task re-queues its own item without costing an attempt. The cleanup task is cancelled last.
- `cleanup_loop` runs [retention cleanup](worker-cleanup.md) at start and then every interval until stopped; failures are logged and retried next interval. It only starts when the interval is above 0.
