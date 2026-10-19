---
type: Gotcha
title: Zero permission counts can mean not recorded
description: Transcript-format recordings have no permission or status lines, so their zero counts are not evidence.
resource: src/lens/recording/models.py
tags: [recording, metrics]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/recording/models.py, src/lens/recording/metrics.py, src/lens/recording/format.py]
---
Files made from the agent's stored conversation (transcript format) hold no `permission_prompt`, `permission_outcome` or `status` lines. `Metrics.permissions_recorded` and `status_recorded` say whether any exist; both are null on rows stored before the fields existed. Consumers such as [compare](/api/stats-compare.md) still compute denial rate from zeros. In transcript files `pane` is the conversation id and there is no pane name. Hook files, by contrast, include agent-written prompts that must be excluded from turns ([format detection](/packages/recording-format.md)).
