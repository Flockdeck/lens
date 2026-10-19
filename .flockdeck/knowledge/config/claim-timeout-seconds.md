---
type: Environment Variable
title: CLAIM_TIMEOUT_SECONDS
description: Age at which a running item's claim is treated as abandoned.
resource: src/lens/config.py
tags: [config, env]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py]
---
Default: 300.

Read by `Settings` ([settings class](../packages/config-settings.md)) from the environment or the `.env` file.

Stale claims are re-queued every 30 seconds. Each item is given 0.9 of this value as its processing timeout so it ends before its claim looks stale ([worker loop](../packages/worker-loop.md)).
