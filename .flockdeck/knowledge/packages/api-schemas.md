---
type: Module
title: API response models
description: Pydantic models for the HTTP API responses.
resource: src/lens/api/schemas.py
tags: [api, schema]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/schemas.py]
---
| Model | Used by | Fields |
|---|---|---|
| `RejectedFile` | batch submit | `filename`, `reason` |
| `BatchAccepted` | [POST /batches](../api/batches-submit.md) | `id`, `accepted` (names), `rejected` |
| `BatchItemOut` | batch views | `id`, `filename`, `status`, `attempts`, `error`, `session_id` |
| `BatchOut` | [batch endpoints](../api/batches-get.md) | `id`, `status`, `counts` (per item status), `items` |
| `EnrichmentOut` | session detail | all [enrichment](../tables/table-enrichments.md) fields plus `created_at` |
| `SessionSummary` | [list](../api/sessions-list.md) | session columns, `duration_seconds`, `tool_calls`, `raw_available`, and category, outcome, frustration, summary from the enrichment |
| `SessionList` | list | `total`, `items` |
| `SessionDetail` | [detail](../api/sessions-get.md) | summary plus `metrics`, `risky_actions`, `files_touched`, `warnings`, `enrichment` |
| `EventsPage` | [events](../api/sessions-events.md) | `items`, `next_after_seq` |
| `TrendPoint`, `ComparePoint`, `Usage` | [stats](../api/stats-trends.md) | see those endpoints |
| `RuntimeConfig` | [GET /config](../api/config-get.md) | `storage`, `enricher`, `raw_retention_days`, `cleanup_interval_seconds`, `version` |

Settings request and response models live in the settings router, see [PUT /settings](../api/settings-put.md).
