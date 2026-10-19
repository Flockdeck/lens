---
type: Environment Variable
title: ENRICHER
description: Which enricher analyses sessions, one of mock, ollama or anthropic.
resource: src/lens/config.py
tags: [config, env]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py]
---
Default: `mock`.

Read by `Settings` ([settings class](../packages/config-settings.md)) from the environment or the `.env` file.

Allowed values `mock`, `ollama`, `anthropic` (others fail validation). `mock` and `ollama` send nothing off the machine; `anthropic` sends the bounded digest to the Anthropic API ([egress](../security/anthropic-egress.md)). Can be overridden from the UI ([runtime settings](../packages/runtime-settings.md)). Chosen by [build_enricher](../packages/enrich.md). Reported by [GET /config](../api/config-get.md).
