---
type: Module
title: Runtime settings overrides
description: Settings changed in the UI are stored in app_settings and override the environment for both API and worker.
resource: src/lens/runtime_settings.py
tags: [config, enrichment]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/runtime_settings.py, src/lens/api/routers/settings.py]
---
`EDITABLE` is the whitelist: `enricher`, `anthropic_api_key`, `anthropic_model`, `anthropic_workspace_id`, `ollama_url`, `ollama_model`. Values live as text rows in [app_settings](../tables/table-app-settings.md).

- `load_overrides` reads the rows (only whitelisted keys). `save_overrides(changes)` sets a key, or deletes the row when the value is None; a key outside the list raises `ValueError`.
- `apply_overrides(base, overrides)` returns a copy of `Settings` with the overrides applied; an unknown `enricher` value is dropped, and the key is wrapped in `SecretStr`.
- `key_source` reports `"settings"`, `"environment"` or None for the key in effect.
- `DynamicEnricher` implements the `Enricher` protocol. Before each call it re-reads the overrides at most every `ttl` (2 s), computes a fingerprint of the settings that matter to the chosen enricher, and rebuilds the inner enricher only when it changed. The rebuild runs in a thread because creating an HTTP client loads TLS certificates and can take seconds. A `ValueError` from the factory (missing key, non-local Ollama URL) is stored and every call raises a non-retryable `EnrichmentError("enricher is not configured: ...")` naming the problem; fixing the setting and retrying the item works without a restart.

The API process and the worker share one process under [serve](../cli/serve.md), but the design works across processes because the database is the shared store. Endpoints: [GET /settings](../api/settings-get.md), [PUT /settings](../api/settings-put.md).
