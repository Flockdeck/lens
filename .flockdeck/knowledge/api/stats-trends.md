---
type: HTTP Endpoint
title: GET /stats/trends
description: Aggregates sessions per day or ISO week with outcome counts, average frustration and tool error rate.
resource: src/lens/api/routers/stats.py
tags: [api, stats]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/routers/stats.py, src/lens/api/dates.py]
---
Query: `interval` (`day` default or `week`), `project`, `from`, `to` ([date range](/packages/api-dates.md)). Sessions are placed by `started_at`, falling back to `created_at` when `started_at` is null; weeks start on Monday (UTC). The Monday bucket is computed in SQL as `date(moment, '-N days')` with `N = (strftime('%w') + 6) % 7`.

Each `TrendPoint`: `bucket` (ISO date), `sessions`, `outcomes` (counts by enrichment outcome, with `unenriched` for sessions that have none), `avg_frustration` (over enriched sessions only, else null) and `tool_error_rate` (tool errors / tool calls, null when there are no calls). Metrics are read from the JSON `metrics` column with missing keys counted as 0.
