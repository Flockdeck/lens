---
type: Data Type
title: Metrics JSON
description: The deterministic metrics stored on each session and sent to the enricher.
resource: src/lens/recording/models.py
tags: [recording, metrics]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/recording/models.py, src/lens/recording/metrics.py]
---
Fields of `Metrics`: `duration_seconds`, `turns`, `tool_calls`, `tool_mix` (count per tool), `tool_errors`, `tool_interrupted`, `unpaired_calls`, `permission` (`prompts`, `allowed`, `denied`, `auto_approved`, `abandoned`, `inferred`), `status_seconds`, `permissions_recorded`, `status_recorded` (both null in rows stored before they existed), `compactions`, `usage` (summed token usage or null), `redacted_lines`, `clipped_lines`, `models`.

Computation: [metrics](/packages/recording-metrics.md). The stats endpoints read `tool_errors`, `tool_calls`, `permission.denied` and `permission.prompts` straight from the JSON column with missing keys as 0 ([stats](/api/stats-trends.md)).
