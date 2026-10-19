---
type: Environment Variable
title: WORKER_POLL_SECONDS
description: How long the worker waits for work before polling the queue again.
resource: src/lens/config.py
tags: [config, env]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py]
---
Default: 1.0.

Read by `Settings` ([settings class](/packages/config-settings.md)) from the environment or the `.env` file.

The loop also wakes early when an in-flight item finishes or stop is requested ([worker loop](/packages/worker-loop.md)). The smoke test sets 0.1.
