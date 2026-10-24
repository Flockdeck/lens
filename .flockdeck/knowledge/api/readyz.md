---
type: HTTP Endpoint
title: GET /readyz
description: Readiness probe that checks the database and the file store.
resource: src/lens/api/routers/health.py
tags: [api, health]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/routers/health.py]
---
Runs `SELECT 1` and then `store.ping()`, each under a 3 second timeout. 200 `{"status": "ok"}` on success; 503 `{"status": "unavailable", "check": "db" | "store"}` on any failure, with the exception type logged. The smoke test waits for 200 here before using the binary ([smoke test](../tools/smoke-test.md)).
