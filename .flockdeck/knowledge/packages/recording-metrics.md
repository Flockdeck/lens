---
type: Module
title: Recording metrics
description: compute_metrics and completeness derive deterministic counts, permission stats and timings from events.
resource: src/lens/recording/metrics.py
tags: [recording, metrics]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/recording/metrics.py]
---
Output shape: [Metrics](../tables/analysis-metrics.md) and [completeness](../tables/completeness.md).

- Turns count `user_prompt` events that are not subagent prompts and not agent-generated text (see [format detection](recording-format.md)).
- Tool errors do not include interrupted results; interruptions are counted separately.
- Unpaired calls: tool-use ids with a call and no result, plus id-less calls beyond the id-less results of the same tool.
- Permission matching: `_PendingPrompts` pairs each `permission_outcome` with the oldest pending prompt with the same tool-use id, else an id-less prompt of the same tool, else the oldest at all, in amortised O(1). `auto_approved` outcomes never consume a prompt. Prompts still pending at the end count as abandoned.
- `permissions_recorded` and `status_recorded` say whether the file has any permission or status lines at all; transcript-format files have neither, so zeros there mean "not recorded" (see [transcript metrics](../gotchas/transcript-metrics-not-recorded.md)).
- `usage` sums the per-reply token usage; None when no line has any.
- `models` lists every model in order of first appearance.
- `duration_seconds` is last minus first event time, floored at 0, rounded to 3 places.
- `status_seconds`: each status lasts until the next status line or the last event; see [status upper bounds](../gotchas/status-seconds-upper-bound.md).
