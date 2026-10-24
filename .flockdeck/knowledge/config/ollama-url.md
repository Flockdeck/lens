---
type: Environment Variable
title: OLLAMA_URL
description: Base URL of the local Ollama server; must point at this machine.
resource: src/lens/config.py
tags: [config, env]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py]
---
Default: `http://127.0.0.1:11434`.

Read by `Settings` ([settings class](../packages/config-settings.md)) from the environment or the `.env` file.

Checked by `require_local_url` when the enricher is built and when set through the UI: only `127.0.0.1`, `::1`, `localhost` and `host.docker.internal` hosts. See [Ollama local URL](../security/ollama-local-url.md) and [OllamaEnricher](../packages/enrich-ollama.md).
