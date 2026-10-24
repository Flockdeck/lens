---
type: HTTP Endpoint
title: GET /config
description: Non-secret runtime facts for the UI, covering enricher, retention, cleanup interval and version.
resource: src/lens/api/routers/config.py
tags: [api, config]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/routers/config.py]
---
Returns `RuntimeConfig`: `storage` (always `filesystem`), `enricher` (after [UI overrides](../packages/runtime-settings.md)), `raw_retention_days` (0 keeps raw files forever), `cleanup_interval_seconds` and `version`. No keys or paths. The UI builds its always-visible "Local only" status from it ([web lib](../packages/web-lib.md)).
