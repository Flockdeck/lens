---
type: Module
title: Recording models
description: Pydantic models for a parsed event line and for the Analysis, Metrics and Digest computed from a recording.
resource: src/lens/recording/models.py
tags: [recording, schema]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/recording/models.py]
---
`Event`: the envelope fields `v`, `seq` (strict ints), `time`, `session`, `pane`, `type` are required; everything else is optional and read loosely, so a field with an unexpected shape becomes None and the line is kept. Extra fields are allowed and kept. `time` must be an RFC 3339 string (an integer is rejected); fractions beyond microseconds are truncated and a missing offset is read as UTC. Aliases: `paneName`, `toolUseId`, `isError`, `gitBranch`, `agentVersion`, `tokensBefore`, `tokensAfter`, `stopReason`. Field list in [recording line](/tables/recording-line.md).

`KNOWN_TYPES`: recording_started, recording_stopped, recording_truncated, session, user_prompt, assistant_message, tool_call, tool_result, permission_prompt, permission_outcome, status, conversation_title, conversation_compacted. `HOOK_ONLY_TYPES` (session, permission_prompt, permission_outcome, status) occur only in files made from live hooks. `RECORDER_TYPES` are the three recording_* types.

Computed models: `TokenUsage`, `PermissionStats`, `Metrics` (see [metrics](/tables/analysis-metrics.md)), `RiskyAction` (see [risky action](/tables/risky-action.md)), `FilesTouched`, `DigestMessage`, `DigestFailure`, `Digest`, and `Analysis` (everything computed from one file without an LLM). `Analysis.pane` holds the conversation id for transcript-format files, which have no pane name.
