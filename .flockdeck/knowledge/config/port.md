---
type: Environment Variable
title: PORT
description: Port `lens serve` listens on.
resource: src/lens/config.py
tags: [config, env]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py]
---
Default: 8000.

Read by `Settings` ([settings class](../packages/config-settings.md)) from the environment or the `.env` file.

Overridden by `--port` (a value of 0 on the flag falls back to this setting because the code uses `args.port or settings.port`). See [serve](../cli/serve.md).
