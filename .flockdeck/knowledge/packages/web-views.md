---
type: Module
title: Web UI views
description: One module per page of the UI, each rendering into the main region.
resource: src/lens/web/js/views/session.js
tags: [web, ui]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/web/js/views/submit.js, src/lens/web/js/views/batch.js, src/lens/web/js/views/sessions.js, src/lens/web/js/views/session.js, src/lens/web/js/views/insights.js, src/lens/web/js/views/settings.js]
---
| Module | Route | Behaviour |
|---|---|---|
| `submit.js` | `#/submit` | Drop zone or file picker for `.jsonl` files; checks files locally, uploads with `uploadBatch`, shows per-file rejections returned by the server (kept in `sessionStorage` per batch id). Listens for drag events on the whole document so a missed drop does not navigate the tab to the file. |
| `batch.js` | `#/batches/<id>` | Polls every 2 s while items are queued or running (and again when the tab becomes visible); buttons to retry failed items and cancel queued ones; shows files the server rejected at upload, read from `sessionStorage`. |
| `sessions.js` | `#/sessions` | Paged list from [GET /sessions](/api/sessions-list.md) with filters for project, agent, model, category, outcome and a from/to date range kept in the hash query. |
| `session.js` | `#/sessions/<id>` | Analysis, metrics, risky actions and raw events (paged, 100 at a time) with tabs; re-enrich and delete actions. A 410 from the API sets "raw gone" and shows the expiry text. |
| `insights.js` | `#/insights` | Token usage ([usage](/api/stats-usage.md)), trends by day or week with an optional project ([trends](/api/stats-trends.md)) and a comparison by agent or model ([compare](/api/stats-compare.md)). |
| `settings.js` | `#/settings` | Form for enricher, Anthropic model, key and workspace, Ollama URL and model; the key input is a password field and the server never returns it ([API key handling](/security/api-key-handling.md)). |
