---
type: Environment Variable
title: OLLAMA_MODEL
description: Model name requested from Ollama.
resource: src/lens/config.py
tags: [config, env]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py]
---
Default: `llama3.1:8b`.

Read by `Settings` ([settings class](/packages/config-settings.md)) from the environment or the `.env` file.

A 404 from Ollama is reported as a permanent failure that names `ollama pull <model>` ([OllamaEnricher](/packages/enrich-ollama.md)).
