---
type: Setting
title: .env file
description: Settings also read an optional .env file from the working directory; real environment variables win.
resource: src/lens/config.py
tags: [config, env]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py, tests/conftest.py]
---
`SettingsConfigDict(env_file=".env", extra="ignore")`: the file is looked up relative to the current working directory, unknown keys are ignored, and environment variables override file values. The test suite pins the enrichment variables in the environment so a developer's real `.env` (which may hold an Anthropic key) can never make a test call the API ([test suite](/tools/test-suite.md)). `.env` is in `.gitignore`. Variables are listed in [settings class](/packages/config-settings.md). Settings changed in the UI take precedence over both ([runtime settings](/packages/runtime-settings.md)).
