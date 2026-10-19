---
type: HTTP Endpoint
title: GET /sessions/{session_id}
description: Returns one session with metrics, risky actions, files touched, warnings and its enrichment.
resource: src/lens/api/routers/sessions.py
tags: [api, sessions]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/routers/sessions.py]
---
Returns `SessionDetail` ([schemas](../packages/api-schemas.md)). 404 `session not found`. `enrichment` is null until the session has been enriched. Metrics are the [Metrics](../tables/analysis-metrics.md) JSON stored on the session row.
