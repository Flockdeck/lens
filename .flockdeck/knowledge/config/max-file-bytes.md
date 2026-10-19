---
type: Environment Variable
title: MAX_FILE_BYTES
description: Largest accepted recording file, in bytes.
resource: src/lens/config.py
tags: [config, env]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py]
---
Default: 17825792 (17 MiB).

Read by `Settings` ([settings class](../packages/config-settings.md)) from the environment or the `.env` file.

The Flockdeck recorder caps a recording at 16 MiB; this leaves some room. Larger files are rejected per file with `too large` ([uploads](../packages/api-uploads.md)). The UI mirrors the default in `lib.js` ([web lib](../packages/web-lib.md)), so changing the server value does not change the UI pre-check.
