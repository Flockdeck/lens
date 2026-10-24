---
type: Module
title: LocalOnly middleware
description: ASGI middleware that checks the Host header on every request and the Origin of every write.
resource: src/lens/api/local.py
tags: [security, middleware]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/local.py]
---
Implements the [local-only guard](../security/local-only-guard.md). `normalise_hosts` lower-cases names and strips brackets and ports, so `[::1]` and `::1` match. `LocalOnly(app, allowed_hosts)` handles only `http` scopes, so it also sees requests no route matches.

Order of checks:

1. `Host` host name not in the allowed set: 421 `{"detail": "host not allowed"}`.
2. For POST, PUT, PATCH and DELETE: an `Origin` that is not `null` whose host is not allowed: 403 `cross-origin request refused`.
3. For the same methods: `Origin: null` or `Sec-Fetch-Site: cross-site`: 403 `cross-origin request refused`.

Refusals carry `Cache-Control: no-store`, are logged with reason, method and status only (never the offending host or origin), and ports are ignored in all comparisons. The allowed set comes from [ALLOWED_HOSTS](../config/allowed-hosts.md).
