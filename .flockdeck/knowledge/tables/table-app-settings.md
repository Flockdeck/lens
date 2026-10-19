---
type: Database Table
title: Table app_settings
description: Key and value rows for settings changed in the UI, including the Anthropic API key in plain text.
resource: src/lens/db/models.py
tags: [database, table, config]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/db/models.py, src/lens/runtime_settings.py]
---
Columns: `key` (primary key, up to 64), `value` (text), `updated_at`. Only the six keys in the whitelist are read ([runtime settings](/packages/runtime-settings.md)). The model comment states the key is stored as plain text on the grounds that the database sits on the same machine as the `.env` it replaces, and that the API never returns it; see [API key handling](/security/api-key-handling.md).
