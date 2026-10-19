---
type: Environment Variable
title: HOST
description: Address `lens serve` binds to.
resource: src/lens/config.py
tags: [config, env]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py]
---
Default: `127.0.0.1`.

Read by `Settings` ([settings class](/packages/config-settings.md)) from the environment or the `.env` file.

Overridden by `--host`. Anything not loopback logs a warning ([loopback bind](/security/loopback-bind.md)); there is no API key, so binding wider exposes recordings to the network.
