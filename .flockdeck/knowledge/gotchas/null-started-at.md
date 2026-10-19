---
type: Gotcha
title: Sessions without started_at
description: Date filters exclude them; trends fall back to created_at.
resource: src/lens/api/routers/sessions.py
tags: [api, sessions]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/routers/sessions.py, src/lens/api/routers/stats.py, src/lens/api/dates.py]
---
`started_at` can be null (for example a recording that never logged a start). [GET /sessions](/api/sessions-list.md) excludes such rows whenever `from` or `to` is given; sorting by a nullable column puts NULLs last when descending and first when ascending. [GET /stats/trends](/api/stats-trends.md) uses `coalesce(started_at, created_at)`, so the same session appears in trends but not in a ranged list.
