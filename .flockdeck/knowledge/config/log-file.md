---
type: Environment Variable
title: LOG_FILE
description: Where logs go, with `-` for standard output, a path for a file, or blank for an automatic choice.
resource: src/lens/config.py
tags: [config, env]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py]
---
Default: empty.

Read by `Settings` ([settings class](../packages/config-settings.md)) from the environment or the `.env` file.

Blank means standard output in a terminal and `<DATA_DIR>/lens.log` otherwise; files rotate at 5 MiB with 3 backups ([logging](../packages/api-logging.md)). The tests and the Flockdeck-style launch in the smoke test set `-`. See [file logging when piped](../gotchas/log-file-when-piped.md).
