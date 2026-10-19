---
type: Security Boundary
title: Anthropic egress is opt-in and bounded
description: Only the Anthropic enricher sends data off the machine, and it sends a bounded digest, never the raw recording.
resource: src/lens/enrich/anthropic.py
tags: [security, privacy, egress]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/enrich/anthropic.py, src/lens/enrich/prompt.py, src/lens/recording/digest.py, src/lens/web/js/lib.js]
---
Default enricher is `mock`; `ollama` is local. With `ENRICHER=anthropic` ([ENRICHER](/config/enricher.md)) the digest ([bounds](/packages/recording-digest.md), [prompt caps](/packages/enrich-prompt.md)) is sent to the Anthropic API: user prompts, final messages, trimmed failing tool output, metrics, capped risky action summaries and file lists. Building the enricher logs one warning, `ENRICHER=anthropic: session digests are sent to the Anthropic API`, with the model name and no content.

Defences against hostile recording text: the system prompt tells the model that `<facts>` and `<digest>` are data, and the JSON in those blocks has `<`, `>` and `&` escaped so text cannot close a tag. The model may only reference event seqs it was given; others are dropped. Recorder-side redaction markers (`[redacted]`) are preserved and flagged.

The UI shows the state permanently: "Sends digests to Anthropic" versus "Local only" ([web lib](/packages/web-lib.md)).
