---
type: Security Boundary
title: No interactive API docs
description: docs, redoc and openapi endpoints are disabled so nothing loads scripts from a CDN.
resource: src/lens/api/app.py
tags: [security, privacy]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/app.py, tests/api/test_hardening.py]
---
`FastAPI(docs_url=None, redoc_url=None, openapi_url=None)`. The comment gives the reason: the stock docs page loads scripts from a CDN and the app must not call out. Requests for those paths fall through to the static mount and return 404 (`test_no_interactive_docs_or_schema`).
