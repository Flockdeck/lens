---
type: Module
title: Session digest
description: build_digest compacts a session into a size-bounded set of prompts, final messages, failures and risks for the LLM.
resource: src/lens/recording/digest.py
tags: [recording, digest, privacy]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/recording/digest.py]
---
The digest is what an enricher sees instead of the raw recording. Limits:

| Item | Limit |
|---|---|
| user prompts | 20, keeping the first 5 and the latest 15; `omitted_prompts` counts the rest; 1200 chars each |
| final messages | last 5, 2000 chars each |
| failing results | latest 10 errors or interruptions, 400 chars of output each; `omitted_failures` counts the rest |
| risky actions | 10, ranked high before medium before low, then by seq |
| files edited | 30 paths; read and command counts are totals only |

`trim(text, limit)` appends `...[trimmed N chars]`. Prompts exclude subagent prompts and agent-generated text. Final messages are the last assistant message before each real user prompt (a transcript has every assistant message, hook files only the last of each turn), skipping subagents. The digest also carries project, agent, model, title (last `conversation_title`), source format, completeness and full [metrics](../tables/analysis-metrics.md). `redacted` and `clipped` flags on messages are copied from the event.
