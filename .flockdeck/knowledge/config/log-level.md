---
type: Environment Variable
title: LOG_LEVEL
description: Root log level; case-insensitive.
resource: src/lens/config.py
tags: [config, env]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py]
---
Default: `INFO`.

Read by `Settings` ([settings class](../packages/config-settings.md)) from the environment or the `.env` file.

Applied with `level.upper()` in [logging setup](../packages/api-logging.md). `aiosqlite` and `sqlalchemy.engine` stay at WARNING whatever this is, and Alembic is pinned to WARNING by the CLI.
