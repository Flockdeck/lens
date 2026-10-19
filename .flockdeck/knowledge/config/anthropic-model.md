---
type: Environment Variable
title: ANTHROPIC_MODEL
description: Model name the Anthropic enricher requests.
resource: src/lens/config.py
tags: [config, env]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py]
---
Default: `claude-haiku-4-5`.

Read by `Settings` ([settings class](/packages/config-settings.md)) from the environment or the `.env` file.

Free text up to 128 characters when set from the UI. Stored on each enrichment as `model`. Used by [AnthropicEnricher](/packages/enrich-anthropic.md).
