---
type: Gotcha
title: status_seconds are upper bounds
description: Time in each pane status can overstate working and blocked time.
resource: src/lens/recording/metrics.py
tags: [recording, metrics]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/recording/metrics.py]
---
Each status lasts until the next status line or the last event. Flockdeck writes a status line only when an agent event causes the change, so a pane that goes idle on a timer or whose process ends changes status without a line and the old status keeps running. The docstring says to treat the values as upper bounds, not measurements. See [metrics](/packages/recording-metrics.md).
