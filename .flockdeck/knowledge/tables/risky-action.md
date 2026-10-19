---
type: Data Type
title: RiskyAction
description: A rule hit on one tool call, with seq, tool, summary, severity and rule name.
resource: src/lens/recording/models.py
tags: [recording, risk]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/recording/models.py, src/lens/recording/risk.py]
---
Fields: `seq` (event number), `tool`, `summary` (at most 160 characters), `severity` (`low`, `medium`, `high`), `rule` (for example `rm_rf`, `git_force_push`). Produced by [risk rules](/packages/recording-risk.md), stored in `sessions.risky_actions`, and referenced by seq in enrichment risk notes.
