---
type: Security Boundary
title: No CORS headers
description: The app adds no Access-Control headers, so other origins cannot read responses.
resource: src/lens/api/app.py
tags: [security, cors]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/app.py, tests/api/test_privacy.py]
---
No CORS middleware is installed. A preflight `OPTIONS` with a foreign `Origin` gets no `access-control-*` headers, and a simple GET with a foreign `Origin` gets no `access-control-allow-origin`. The same-origin UI needs none. Together with the [local-only guard](local-only-guard.md) this keeps recordings unreadable from other sites. Covered by `test_cors_is_closed`.
