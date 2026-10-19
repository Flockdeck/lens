---
type: Module
title: Enricher protocol and factory
description: Enricher.enrich turns an Analysis into an EnrichmentResult; build_enricher picks mock, ollama or anthropic.
resource: src/lens/enrich/base.py
tags: [enrichment]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/enrich/base.py, src/lens/enrich/__init__.py]
---
`Enricher` is a Protocol with `async enrich(analysis) -> EnrichmentResult`. `build_enricher(settings)` imports the chosen implementation lazily so the mock path loads no SDK or HTTP client: `anthropic` gives [AnthropicEnricher](/packages/enrich-anthropic.md), `ollama` gives [OllamaEnricher](/packages/enrich-ollama.md), anything else [MockEnricher](/packages/enrich-mock.md).

`EnrichmentError(message, *, retryable, input_tokens=0, output_tokens=0)` carries whether a retry makes sense and the tokens spent on failed attempts. Messages never include recording content. Worker handling is in [retry classification](/packages/worker-retry.md).

Result types are described in [EnrichmentResult](/tables/enrichment-result.md). The wrapper used by the app is [DynamicEnricher](/packages/runtime-settings.md).
