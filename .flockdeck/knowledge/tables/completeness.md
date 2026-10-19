---
type: Data Type
title: Recording completeness values
description: How a recording ended, derived from its last known event.
resource: src/lens/recording/metrics.py
tags: [recording, metrics]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/recording/metrics.py, src/lens/recording/parser.py]
---
| Value | Rule |
|---|---|
| `clean` | last known event is `recording_stopped` and the file has other events too |
| `truncated` | last known event is `recording_truncated` (the recorder hit its size cap) |
| `cut_off` | last known event is anything else, or there is no known event |
| `partial_agent` | last known is `recording_stopped` and every known event is a recorder line: the agent has no hooks and reports only start and stop |

Events of unknown types are ignored when finding the end, so a newer trailing line does not turn a clean file into a cut-off one. Each non-clean value adds a [warning](/packages/recording-parser.md). The mock enricher treats `cut_off` as abandoned ([mock](/packages/enrich-mock.md)). Stored in [sessions](/tables/table-sessions.md).
