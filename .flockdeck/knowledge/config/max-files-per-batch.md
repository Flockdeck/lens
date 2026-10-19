---
type: Environment Variable
title: MAX_FILES_PER_BATCH
description: Maximum number of files in one upload.
resource: src/lens/config.py
tags: [config, env]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py]
---
Default: 100.

Read by `Settings` ([settings class](/packages/config-settings.md)) from the environment or the `.env` file.

Passed to the multipart parser as `max_files`; exceeding it gives 400 `malformed multipart request` ([POST /batches](/api/batches-submit.md)). The UI pre-check uses a fixed 100.
