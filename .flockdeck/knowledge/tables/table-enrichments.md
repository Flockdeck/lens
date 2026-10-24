---
type: Database Table
title: Table enrichments
description: The LLM or mock analysis of a session; at most one per session.
resource: src/lens/db/models.py
tags: [database, table, enrichment]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/db/models.py, src/lens/migrations/versions/0001_initial_schema.py]
---
Columns: `session_id` (FK to sessions, unique, `ON DELETE CASCADE`), `prompt_version`, `model` (`mock` for the mock enricher), `summary`, `category` (indexed), `outcome` (indexed; `done`, `abandoned`, `stuck`), `frustration` (float 0 to 1), `stuck_points` (JSON), `prompt_feedback`, `model_fit` and `model_fit_reason` (null for rows made before they existed), `risk_notes` (JSON), `input_tokens`, `output_tokens`, `created_at`.

Written by the [processor](../packages/worker-processor.md) and by [re-enrich](../api/sessions-enrich.md); shape from [EnrichmentResult](enrichment-result.md).
