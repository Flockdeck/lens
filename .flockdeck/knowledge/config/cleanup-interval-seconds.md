---
type: Environment Variable
title: CLEANUP_INTERVAL_SECONDS
description: How often the worker runs retention cleanup; 0 turns the timer off.
resource: src/lens/config.py
tags: [config, env]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py]
---
Default: 3600.

Read by `Settings` ([settings class](../packages/config-settings.md)) from the environment or the `.env` file.

Reported as `cleanup_interval_seconds` by [GET /config](../api/config-get.md). The manual command is [lens cleanup](../cli/cleanup.md); the work is described in [cleanup](../packages/worker-cleanup.md).
