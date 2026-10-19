---
type: Security Boundary
title: Ollama local URL rule
description: The Ollama base URL must be loopback or host.docker.internal, and the client ignores proxies and redirects.
resource: src/lens/enrich/ollama.py
tags: [security, privacy, ollama]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/enrich/ollama.py, src/lens/api/routers/settings.py]
---
`require_local_url` accepts only `http` or `https` URLs whose host name (case-insensitive) is `127.0.0.1`, `::1`, `localhost` or `host.docker.internal`. It runs in the constructor, so a mistyped setting fails when the enricher is built and a digest can never be sent to another host, and again in [PUT /settings](/api/settings-put.md) (422). The `httpx` client uses `trust_env=False` and `follow_redirects=False` so neither a proxy variable nor a redirect can send the request elsewhere. See [OLLAMA_URL](/config/ollama-url.md).
