---
type: HTTP Endpoint
title: GET /stats/usage
description: Returns total enrichment tokens and the number of enrichments.
resource: src/lens/api/routers/stats.py
tags: [api, stats]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/routers/stats.py]
---
Returns `{input_tokens, output_tokens, enrichments}`: sums of the [enrichments](/tables/table-enrichments.md) token columns and the row count. These are the tokens spent analysing sessions (zero for the mock enricher), not what the recorded agents used.
