---
type: Security Boundary
title: Loopback bind and non-loopback warning
description: The server binds to 127.0.0.1 by default; any other bind address logs a warning.
resource: src/lens/api/app.py
tags: [security, network]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/app.py, src/lens/cli.py, tests/api/test_privacy.py]
---
`warn_if_not_loopback(host)` returns True and logs `listening on a non-loopback address; recordings are sensitive and must not be reachable from other machines` unless the host is `localhost` or a loopback IP. `lens serve` calls it before starting. The docstring says to pass `0.0.0.0` only where something else (a container network) limits who can connect. It does not stop the bind. See [HOST](/config/host.md) and the [local-only guard](/security/local-only-guard.md), which still applies to a wider bind but is not authentication.
