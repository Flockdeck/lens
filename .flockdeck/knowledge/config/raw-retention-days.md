---
type: Environment Variable
title: RAW_RETENTION_DAYS
description: Days to keep raw recording files; 0 keeps them forever.
resource: src/lens/config.py
tags: [config, env]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py]
---
Default: 30.

Read by `Settings` ([settings class](/packages/config-settings.md)) from the environment or the `.env` file.

After this age the stored file is deleted and the raw row marked expired; sessions, metrics and enrichments stay ([cleanup](/packages/worker-cleanup.md)). The UI shows the value and the expiry text ([web lib](/packages/web-lib.md)); the value is set on the server only.
