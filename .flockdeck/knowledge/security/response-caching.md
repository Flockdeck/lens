---
type: Security Boundary
title: Response caching rules
description: Data endpoints are no-store; UI files are no-cache so an upgrade is never stale.
resource: src/lens/api/app.py
tags: [security, cache]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/app.py, src/lens/api/local.py, tests/api/test_privacy.py]
---
Paths starting with `/sessions`, `/batches`, `/stats`, `/config` or `/settings` get `Cache-Control: no-store`, as do guard refusals. Probes (`/healthz`, `/readyz`, `/metrics`) and UI files do not. UI files get `no-cache`, so each load revalidates ([WebFiles](../packages/api-app.md)).
