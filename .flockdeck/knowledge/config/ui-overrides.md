---
type: Setting
title: UI setting overrides
description: Six enrichment settings can be changed in the web UI and stored in the database, overriding the environment.
resource: src/lens/runtime_settings.py
tags: [config, ui]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/runtime_settings.py, src/lens/api/routers/settings.py, src/lens/web/js/views/settings.js]
---
Editable: [ENRICHER](/config/enricher.md), [ANTHROPIC_API_KEY](/config/anthropic-api-key.md), [ANTHROPIC_MODEL](/config/anthropic-model.md), [ANTHROPIC_WORKSPACE_ID](/config/anthropic-workspace-id.md), [OLLAMA_URL](/config/ollama-url.md), [OLLAMA_MODEL](/config/ollama-model.md). Nothing else (retention, limits, hosts) can be changed through the API. Precedence: UI override, then environment or `.env`, then default. Removing an override restores the lower level. Endpoints: [GET](/api/settings-get.md) and [PUT](/api/settings-put.md). Storage: [app_settings](/data/table-app-settings.md).
