---
type: Environment Variable
title: SHUTDOWN_GRACE_SECONDS
description: How long the worker waits for in-flight items on shutdown before cancelling and re-queueing them.
resource: src/lens/config.py
tags: [config, env]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py]
---
Default: 25.0.

Read by `Settings` ([settings class](../packages/config-settings.md)) from the environment or the `.env` file.

The config comment says to set the process's termination grace period above it. Cancelled items go back to queued without using an attempt ([processor](../packages/worker-processor.md)).
