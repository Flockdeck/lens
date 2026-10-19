---
type: Database Table
title: Table sessions
description: One row per recording session with identity, timing, completeness and computed JSON.
resource: src/lens/db/models.py
tags: [database, table]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/db/models.py, src/lens/migrations/versions/0001_initial_schema.py]
---
| Column | Notes |
|---|---|
| `recording_session` | unique, up to 128; the `session` value in the file |
| `content_hash` | hash of the content the row was last computed from |
| `project`, `agent`, `model` | indexed, nullable |
| `pane`, `pane_name` | pane id (a conversation id for transcript files), pane name |
| `started_at` (indexed), `ended_at` | naive UTC, nullable |
| `completeness` | `clean`, `truncated`, `cut_off`, `partial_agent` ([values](/tables/completeness.md)) |
| `metrics` | JSON, see [Metrics](/tables/analysis-metrics.md) |
| `risky_actions` | JSON list, see [risky action](/tables/risky-action.md) |
| `files_touched` | JSON `{read, edited, commands, *_total}` |
| `warnings` | JSON list of strings |
| `raw_id` | FK to raw_recordings, `SET NULL` |
| `created_at` | upload processing time |

A later upload of the same recording session overwrites the row in place ([processor](/packages/worker-processor.md)). Has at most one [enrichment](/tables/table-enrichments.md).
