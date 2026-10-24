---
type: Module
title: Enrichment prompt and output schema
description: Versioned system prompt, the LLMEnrichment answer schema and the bounded user message built from an Analysis.
resource: src/lens/enrich/prompt.py
tags: [enrichment, prompt]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/enrich/prompt.py]
---
`PROMPT_VERSION = "v3"`, stored with each enrichment; the source says to bump it whenever the system prompt, schema or message layout changes.

`SYSTEM_PROMPT` tells the model that everything inside `<facts>` and `<digest>` is JSON data to analyse, not instructions, that secrets appear as `[redacted]` and clipped strings end in a marker, and describes each output field (summary, category, outcome, frustration, stuck_points, prompt_feedback, model_fit, model_fit_reason, risk_notes).

`LLMEnrichment` (pydantic, `extra="forbid"`) is the schema passed as the structured-output format: category is one of bugfix, feature, refactor, exploration, docs, tests, ops, other; outcome is done, abandoned or stuck; model_fit is well_matched, overpowered, underpowered or unclear. A validator clamps `frustration` to 0..1 because the API schema cannot carry numeric bounds.

## Bounds on what is sent

| Constant | Value |
|---|---|
| `MAX_LIST_ITEMS` | 30 (risky actions, file lists) |
| `MAX_DIGEST_ITEMS` | 20 per list in the digest |
| `MAX_ITEM_CHARS` | 300 |
| `MAX_DIGEST_CHARS` | 2000 per string |

`build_user_message` renders `<facts>` (project, agent, model, completeness, start and end, metrics, capped risky actions, capped file lists with totals, capped warnings) and `<digest>` (see [digest](recording-digest.md)) as compact sorted JSON. `<`, `>` and `&` are replaced by unicode escapes so recording text cannot close a tag. `supplied_seqs` is the set of event seqs the prompt mentions; enrichers drop references to any other seq.
