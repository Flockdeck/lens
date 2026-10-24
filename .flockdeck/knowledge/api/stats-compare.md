---
type: HTTP Endpoint
title: GET /stats/compare
description: Compares sessions grouped by agent or model.
resource: src/lens/api/routers/stats.py
tags: [api, stats]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/routers/stats.py]
---
Query: `by` (`agent` default or `model`), `project`. Returns `ComparePoint` per key: `sessions`, `outcomes`, `tool_error_rate`, `permission_denial_rate` (denied / permission prompts, null without prompts), `avg_frustration`. A null agent or model is grouped as `unknown`. Sorted by session count descending, then key. For transcript-format files permission counts are zero because they are not recorded ([note](../gotchas/transcript-metrics-not-recorded.md)).
