---
type: Environment Variable
title: OLLAMA_TIMEOUT_SECONDS
description: HTTP timeout for calls to Ollama, in seconds.
resource: src/lens/config.py
tags: [config, env]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py]
---
Default: 120.

Read by `Settings` ([settings class](../packages/config-settings.md)) from the environment or the `.env` file.

Passed to the `httpx.AsyncClient`; a timeout is a retryable enrichment failure ([OllamaEnricher](../packages/enrich-ollama.md)). Not editable in the UI.
