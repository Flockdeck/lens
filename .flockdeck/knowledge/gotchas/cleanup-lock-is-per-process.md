---
type: Gotcha
title: Cleanup lock is per process
description: The code and docstrings disagree about a database lock; the guard is an in-process asyncio lock.
resource: src/lens/worker/cleanup.py
tags: [worker, retention]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/worker/cleanup.py, src/lens/worker/loop.py, src/lens/cli.py]
---
`run_cleanup` guards with a module-level `asyncio.Lock`, so a manual `lens cleanup` in another process does not see a running `serve` and both may run. Expiry is idempotent (a missing file is fine, rows are only set expired once), so overlap is harmless. The `cleanup_loop` docstring ("cleanup holds a database lock") and the comment on cancelling it ("its DB lock goes with the connection") describe a design the code does not have.
