---
type: Security Boundary
title: Local-only guard
description: No API key exists; requests are accepted only for this machine's own host names and from same-origin writers.
resource: src/lens/api/local.py
tags: [security, dns-rebinding, csrf]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/local.py, src/lens/config.py, tests/api/test_local_only.py]
---
Threat: a web page open in the user's browser can send requests to `http://127.0.0.1:<port>`, by a plain form POST or by DNS rebinding (its own host name resolving to this machine). The service has no token, so two checks stand in for one, implemented by [LocalOnly](/packages/api-local.md):

| Check | Rule | Response |
|---|---|---|
| Host | host name (port ignored) must be in [ALLOWED_HOSTS](/config/allowed-hosts.md) | 421 `host not allowed` |
| Origin on writes | POST, PUT, PATCH, DELETE with an `Origin` whose host is not allowed | 403 `cross-origin request refused` |
| Null origin or `Sec-Fetch-Site: cross-site` on writes | refused | 403 |

A rebound page still sends its own host name, which defeats rebinding. curl and scripts send neither Origin nor Sec-Fetch-Site and are unaffected. The middleware is outermost, so even unmatched routes and the static UI are covered. Refusals never log the offending host or origin. Tests cover rejected hosts, foreign pages uploading, cancelling and deleting, IPv6 brackets and the three accepted forms of the setting. See also [CORS](/security/cors-closed.md) and [loopback bind](/security/loopback-bind.md).
