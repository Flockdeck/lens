---
type: HTTP Endpoint
title: POST /sessions/{session_id}/enrich
description: Re-runs enrichment for a session and overwrites the stored result.
resource: src/lens/api/routers/sessions.py
tags: [api, sessions, enrichment]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/routers/sessions.py, src/lens/worker/processor.py]
---
Loads and analyzes the raw recording (same 410 and 422 rules as [events](sessions-events.md)), calls the current enricher ([DynamicEnricher](../packages/runtime-settings.md)), then upserts the enrichment in a fresh transaction. No transaction is open while the file is fetched or the model runs.

Errors: 503 `enricher unavailable` if it cannot be built; `EnrichmentError` retryable gives 503 `enrichment failed`, non-retryable or any other crash gives 502 `enrichment failed`. If the upsert hits a unique-key conflict (a concurrent re-enrich) it retries once; a second conflict returns 409 `concurrent re-enrichment, try again`; if the session was deleted in the meantime, 404. Returns the updated `SessionDetail`. The previous enrichment row is unchanged when the call fails.
