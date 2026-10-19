---
type: Data Type
title: EnrichmentResult
description: The common result of every enricher, stored as an enrichments row.
resource: src/lens/enrich/base.py
tags: [enrichment]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/enrich/base.py, src/lens/enrich/prompt.py]
---
Fields: `summary`; `category` (bugfix, feature, refactor, exploration, docs, tests, ops, other); `outcome` (`done`, `abandoned`, `stuck`); `frustration` (0 to 1); `stuck_points` (`description`, `approx_seq`); `prompt_feedback`; `model_fit` (`well_matched`, `overpowered`, `underpowered`, `unclear`, or null) and `model_fit_reason`; `risk_notes` (`seq`, `explanation`); `input_tokens`, `output_tokens`; `model`; `prompt_version`. The model-written subset is the schema in [prompt](/packages/enrich-prompt.md); the caller adds tokens, model and version. Persisted in [enrichments](/tables/table-enrichments.md).
