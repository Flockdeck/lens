---
type: File Format
title: Flockdeck recording line, format v1
description: One JSON line of a Flockdeck pane recording as lens reads it, with the required envelope and optional fields.
resource: src/lens/recording/models.py
tags: [recording, format]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/recording/models.py, tests/fixtures/recording-line.schema.json, tests/fixtures/build.py]
---
A recording is JSON Lines. Required envelope (strictly typed): `v` (must be 1), `seq`, `time` (RFC 3339 string), `session`, `pane`, `type`. Everything else is optional and tolerated: unknown fields are kept, unknown types are counted in a warning, wrong-shaped fields read as absent.

| Field group | Fields |
|---|---|
| context | `paneName`, `project`, `agent`, `model`, `conversation`, `subagent`, `redacted`, `clipped` |
| transcript only | `gitBranch`, `cwd`, `agentVersion`, `usage` (four token counts), `stopReason` |
| messages | `text`, `source`, `reason` |
| tools | `tool`, `toolUseId`, `input`, `output`, `isError`, `interrupted` |
| permissions | `outcome`, `inferred` |
| status | `status`, `previous`, `detail` |
| conversation | `title`, `trigger`, `tokensBefore`, `tokensAfter` |

Types: `recording_started`, `recording_stopped`, `recording_truncated`, `session`, `user_prompt`, `assistant_message`, `tool_call`, `tool_result`, `permission_prompt`, `permission_outcome`, `status`, `conversation_title`, `conversation_compacted`. Two producers exist, told apart by [format detection](/packages/recording-format.md). Parsing rules: [parser](/packages/recording-parser.md); model: [recording models](/packages/recording-models.md). `tests/fixtures/recording-line.schema.json` is a JSON Schema of one line, and `tests/fixtures/build.py` generates the `.jsonl` fixtures ([tools](/tools/test-fixtures.md)).
