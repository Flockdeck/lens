---
type: Module
title: Anthropic enricher
description: Calls the Anthropic Messages API with a JSON-schema output format and validates the reply.
resource: src/lens/enrich/anthropic.py
tags: [enrichment, anthropic, remote]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/enrich/anthropic.py]
---
Opt-in and the only place data leaves the machine, see [Anthropic egress](/security/anthropic-egress.md).

`AnthropicEnricher.from_settings` needs a non-blank key (else `ValueError("ANTHROPIC_API_KEY is required when ENRICHER=anthropic")`), logs one warning that digests are sent, adds an `anthropic-workspace-id` header when a workspace id is set, and builds `anthropic.AsyncAnthropic`.

`enrich(analysis)`:

1. Builds the user message and the allowed seq set from [prompt](/packages/enrich-prompt.md).
2. Up to 3 attempts. Each call sends the system prompt, one user message and `output_config.format = json_schema` with `max_tokens` 4096.
3. Token usage is summed across attempts.
4. `stop_reason == "refusal"` fails (non-retryable). `max_tokens` retries once with double the budget, then fails (`output truncated at max_tokens=N`).
5. Text blocks are joined and parsed with `LLMEnrichment.model_validate_json`; a validation error is logged as counts only and the loop tries again. No valid output after the attempts is a non-retryable failure.
6. The result drops `risk_notes` with a seq the prompt did not contain and nulls `approx_seq` values outside that set.

API errors: rate limit and connection errors are retryable; `APIStatusError` is retryable for status >= 500, 408, 409 and 529. The message adds the API's error type and a message clipped to 200 characters.
