---
type: Security Boundary
title: Anthropic API key handling
description: The key is a secret string, write-only through the API, never logged, and stored as plain text in the local database when set from the UI.
resource: src/lens/runtime_settings.py
tags: [security, secrets]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py, src/lens/db/session.py, src/lens/storage/filesystem.py, src/lens/runtime_settings.py, src/lens/api/routers/settings.py, src/lens/api/logging.py, src/lens/web/js/views/settings.js]
---
- Environment value: `SecretStr`, so it prints as masked.
- UI value: saved in [app_settings](/tables/table-app-settings.md) as plain text. The source comment justifies this because the database lives on the same machine as the `.env` it replaces. The SQLite file is created with default permissions: no code sets a mode on it. Only the recording files (0600, in directories 0700, where the OS supports it) are restricted, in `src/lens/storage/filesystem.py`.
- [GET /settings](/api/settings-get.md) returns only `{set, source}`; no endpoint returns the key.
- [PUT /settings](/api/settings-put.md): at most 512 characters, no whitespace, never echoed; the log line lists changed setting names only.
- Logs: aiosqlite and SQLAlchemy statement logging is pinned to WARNING because at DEBUG it would print statement parameters, including this row ([log policy](/security/log-content-policy.md)).
- The settings form uses a `password` input with `autocomplete="new-password"`.
- Anthropic errors surface the API's error type and a message clipped to 200 characters, not the request.
