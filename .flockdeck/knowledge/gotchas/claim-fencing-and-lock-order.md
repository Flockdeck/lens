---
type: Gotcha
title: Claim fencing and statement order
description: Item updates are conditional on the claim token, and item rows are touched before the batch row.
resource: src/lens/worker/processor.py
tags: [worker, concurrency]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/worker/processor.py, src/lens/worker/queue.py, src/lens/worker/loop.py]
---
- `Claim.locked_at` is the claim token. `_settle` and `_release` add `WHERE status = running AND locked_at = <token>`; if a stale-claim sweep re-queued the item and another worker claimed it, the first worker's update matches nothing and logs `claim lost`.
- The item timeout is 0.9 times the claim timeout so an item ends before its claim looks stale.
- Attempts are incremented at claim time, so an item that crashes the process still runs out of attempts. Releasing on shutdown decrements it so a graceful stop costs nothing.
- `queue.py` notes the order used everywhere: item rows first, then the batch row; the reverse order can deadlock against a worker.
- `retry_failed` first sets the batch to running to clear a sticky `cancelled`, then recomputes.
