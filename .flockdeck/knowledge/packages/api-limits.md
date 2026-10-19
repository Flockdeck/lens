---
type: Module
title: Request body size limit
description: BodySizeLimit is an ASGI middleware that rejects POST /batches bodies over MAX_REQUEST_BYTES with 413.
resource: src/lens/api/limits.py
tags: [api, middleware, limits]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/limits.py]
---
`BodySizeLimit(app, max_bytes, path="/batches")` only acts on `POST` to that path (trailing slash ignored). A declared `Content-Length` over the limit is refused before reading. Otherwise it wraps `receive` and counts the bytes of each `http.request` message, raising `RequestTooLarge` once the total passes the limit, so chunked bodies without a length are stopped too. `request_too_large_handler` maps that exception to 413 `{"detail": "request too large"}`.

`create_app` adds it first, so it sits innermost. The limit is [MAX_REQUEST_BYTES](/config/max-request-bytes.md). See [upload limits](/security/upload-limits.md).
