---
type: Module
title: JSON logging
description: JsonFormatter and setup_logging write one JSON object per log record with ids, counts and timings only.
resource: src/lens/api/logging.py
tags: [logging, privacy]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/logging.py]
---
`JsonFormatter` emits `ts` (UTC ISO, milliseconds), `level`, `logger`, `msg`, plus every extra attribute passed in `extra=`. For exceptions it logs `exc_type` and `frames` (`file:line function`) only; the message and source lines are left out because messages can echo recording content.

`log_destination(log_file, data_dir)`:

| LOG_FILE | stdout is a terminal | Destination |
|---|---|---|
| `-` | any | standard output |
| a path | any | that file |
| empty | yes | standard output |
| empty | no | `<DATA_DIR>/lens.log` |

File logs rotate at 5 MiB with 3 backups. See [LOG_FILE](/config/log-file.md) and [file logging when piped](/gotchas/log-file-when-piped.md).

`setup_logging(level, log_file, data_dir)` replaces the root handlers, sets the level, disables `uvicorn.access` (it logs query strings; the app logs its own request line) and calls `quiet_database_loggers`, which pins `aiosqlite` and `sqlalchemy.engine` to WARNING so statement parameters (an API key row, recording content) never reach a DEBUG log. See [log content policy](/security/log-content-policy.md).
