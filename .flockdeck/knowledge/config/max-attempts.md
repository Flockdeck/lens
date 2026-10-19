---
type: Environment Variable
title: MAX_ATTEMPTS
description: Attempts an item gets before it is marked failed.
resource: src/lens/config.py
tags: [config, env]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py]
---
Default: 4.

Read by `Settings` ([settings class](/packages/config-settings.md)) from the environment or the `.env` file.

Attempts are counted when an item is claimed. Applies to retryable failures ([retry](/packages/worker-retry.md)) and to stale claims ([recover_stale](/packages/worker-loop.md)). A manual retry resets the count.
