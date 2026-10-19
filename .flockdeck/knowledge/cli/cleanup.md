---
type: CLI Command
title: lens cleanup
description: Runs retention cleanup once, on demand; serve already does this on a timer.
resource: src/lens/cli.py
tags: [cli, retention]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/cli.py, src/lens/worker/cleanup.py]
---
`lens cleanup` migrates the database, builds the file store, runs [run_cleanup](../packages/worker-cleanup.md) with [RAW_RETENTION_DAYS](../config/raw-retention-days.md), then closes the store and the engine. It prints `expired N raw recordings, deleted M batches`, or `cleanup skipped: another run is in progress` when the in-process lock is held (only possible in the same process, so a standalone run does not detect a running `serve`). Exit code 0.
