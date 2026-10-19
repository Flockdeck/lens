---
type: Environment Variable
title: STORE_PREFIX
description: Subdirectory of the data directory for raw recordings.
resource: src/lens/config.py
tags: [config, env]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py]
---
Default: `recordings/`.

Read by `Settings` ([settings class](/packages/config-settings.md)) from the environment or the `.env` file.

Joined to the date path by plain concatenation (`<prefix>YYYY/MM/<uuid>.jsonl`), so a custom value needs its own trailing slash ([object key](/tables/object-key.md)). `lens check-storage` probes under `<prefix>probe/`.
