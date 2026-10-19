---
type: HTTP Endpoint
title: GET /sessions
description: Lists sessions with filters, a started_at date range, sorting and offset paging.
resource: src/lens/api/routers/sessions.py
tags: [api, sessions]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/routers/sessions.py, src/lens/api/dates.py]
---
Query parameters:

| Name | Values |
|---|---|
| `project`, `agent`, `model` | exact match on the session |
| `category`, `outcome` | exact match on the enrichment (an unenriched session never matches) |
| `from`, `to` | [date range](/packages/api-dates.md) on `started_at` |
| `sort` | `started_at` (default), `ended_at`, `created_at`, `project`, `frustration` |
| `order` | `desc` (default) or `asc` |
| `limit` | 1 to 200, default 50 |
| `offset` | 0 or more |

Sessions with a null `started_at` are excluded whenever `from` or `to` is given. NULLs sort last when descending and first when ascending; ties break on id descending. Response `SessionList`: `total` and `items` of `SessionSummary`, where `raw_available` is true while the raw row exists and is not expired. Sessions come from [sessions](/data/table-sessions.md) left-joined to [enrichments](/data/table-enrichments.md). Responses are `Cache-Control: no-store`.
