---
type: Environment Variable
title: WORKER_CONCURRENCY
description: Number of batch items processed at once.
resource: src/lens/config.py
tags: [config, env]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py]
---
Default: 4.

Read by `Settings` ([settings class](/packages/config-settings.md)) from the environment or the `.env` file.

Upper bound on in-flight items in the [worker loop](/packages/worker-loop.md).
