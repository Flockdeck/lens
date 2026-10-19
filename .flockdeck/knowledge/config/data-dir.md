---
type: Environment Variable
title: DATA_DIR
description: Directory holding the database, the raw recordings and the log file.
resource: src/lens/config.py
tags: [config, env]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py]
---
Default: the per-user data directory for the app named lens (platformdirs, no author).

Read by `Settings` ([settings class](../packages/config-settings.md)) from the environment or the `.env` file.

Contents: `lens.db` (and its WAL files), `recordings/YYYY/MM/*.jsonl`, `lens.log` when logging to a file. `~` is expanded. Created on demand. Printed by [serve](../cli/serve.md) at start. The smoke test uses a path containing a space on purpose. The file store is rooted here ([storage](../packages/storage-filesystem.md)).
