---
type: HTTP Endpoint
title: GET /settings
description: Returns the effective enrichment settings; the Anthropic key is reported only as set or not set.
resource: src/lens/api/routers/settings.py
tags: [api, settings]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/routers/settings.py, src/lens/runtime_settings.py]
---
Returns `SettingsView`: `enricher`, `anthropic_api_key: {set: bool, source: "settings" | "environment" | null}`, `anthropic_model`, `anthropic_workspace_id`, `ollama_url`, `ollama_model`, and `overridden` (sorted names of settings changed in the UI). The key value is never returned ([API key handling](/security/api-key-handling.md)).
