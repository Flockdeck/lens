---
type: HTTP Endpoint
title: GET /metrics
description: Prometheus text metrics with process and platform collectors, request counters and queue depth by item status.
resource: src/lens/api/routers/health.py
tags: [api, metrics, prometheus]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/routers/health.py, src/lens/api/app.py]
---
Serves the app's private `CollectorRegistry` in the Prometheus text format. Before each response it refreshes the gauge `lens_queue_items{status}` for queued, running, done, failed and cancelled with a grouped count over [batch_items](../tables/table-batch-items.md), under a 3 second timeout; if the database is down it silently serves the process-level metrics only. Counters and histograms are defined in [API app](../packages/api-app.md). No authentication beyond the [local-only guard](../security/local-only-guard.md).
