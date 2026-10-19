---
type: HTTP Endpoint
title: GET /healthz
description: Unauthenticated liveness probe.
resource: src/lens/api/routers/health.py
tags: [api, health]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/routers/health.py]
---
Returns `{"status": "ok"}` with 200 and does no work. Subject to the same [Host check](../security/local-only-guard.md) as every route. Used by the smoke test to detect a stopped server.
