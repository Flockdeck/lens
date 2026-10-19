---
type: HTTP Endpoint
title: PUT /settings
description: Changes or removes UI overrides for the enricher, Anthropic key and model, and Ollama URL and model.
resource: src/lens/api/routers/settings.py
tags: [api, settings, validation]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/routers/settings.py, src/lens/runtime_settings.py]
---
Body `SettingsUpdate` (unknown fields rejected, `extra="forbid"`): send only fields that change; `null` removes the override and restores the environment value. Limits: key 512 characters, names 128, Ollama URL 256.

Validation (422 on failure):

- A string value is stripped and may not become empty.
- The API key and the workspace id may not contain whitespace.
- `ollama_url` must pass `require_local_url` ([Ollama local URL](../security/ollama-local-url.md)); the stored value has no trailing slash.
- If the result would select the `anthropic` enricher with no key from either source: `the anthropic enricher needs an API key`.

Changes are saved to [app_settings](../tables/table-app-settings.md). The log line lists names only. Returns the new `SettingsView`. The worker picks the change up within about 2 seconds ([DynamicEnricher](../packages/runtime-settings.md)).
