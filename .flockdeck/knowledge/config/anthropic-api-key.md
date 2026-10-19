---
type: Environment Variable
title: ANTHROPIC_API_KEY
description: API key for the Anthropic enricher; held as a secret string and never logged or returned.
resource: src/lens/config.py
tags: [config, env]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py]
---
Default: none.

Read by `Settings` ([settings class](/packages/config-settings.md)) from the environment or the `.env` file.

Required when `ENRICHER=anthropic` (blank is treated as missing). Typed `SecretStr`. Can be set from the UI, which stores it in [app_settings](/tables/table-app-settings.md) and takes precedence. See [API key handling](/security/api-key-handling.md). The test setup pins it to empty so tests never call the API.
