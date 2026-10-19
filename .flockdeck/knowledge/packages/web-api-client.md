---
type: Module
title: Web UI API client
description: js/api.js is the only UI module that calls fetch; it wraps the HTTP API and normalises errors.
resource: src/lens/web/js/api.js
tags: [web, client]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/web/js/api.js]
---
`request(method, path, {query, body, signal, json})` sends `Accept: application/json` (and `Content-Type: application/json` for JSON bodies), drops empty query values, parses the body (204 has none), and throws `ApiError(status, message, body)`. The message comes from `detail` as a string, a list of `msg` values, or an object `message`; a network failure gives status 0 `Could not reach the server`; an `AbortError` is rethrown unchanged.

Methods map one to one onto the endpoints: `uploadBatch` ([POST /batches](/api/batches-submit.md)), `getBatch`, `retryBatch`, `cancelBatch`, `listSessions`, `getSession`, `getEvents`, `enrichSession`, `deleteSession`, `trends`, `compare`, `usage`, `getSettings`, `putSettings`, `config`.
