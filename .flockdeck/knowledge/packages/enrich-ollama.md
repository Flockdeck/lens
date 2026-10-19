---
type: Module
title: Ollama enricher
description: Calls a local Ollama server over /api/chat with a JSON schema format; never talks to a non-local host.
resource: src/lens/enrich/ollama.py
tags: [enrichment, ollama, local]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/enrich/ollama.py]
---
`require_local_url(url)` accepts only http or https URLs whose host is `127.0.0.1`, `::1`, `localhost` or `host.docker.internal`, and returns the URL without a trailing slash; otherwise `ValueError`. It runs when the enricher is built and when [PUT /settings](../api/settings-put.md) receives an Ollama URL. See [Ollama local URL](../security/ollama-local-url.md).

The `httpx.AsyncClient` uses `trust_env=False` (ignores proxy variables) and `follow_redirects=False`, with the timeout from [OLLAMA_TIMEOUT_SECONDS](../config/ollama-timeout-seconds.md).

`enrich` mirrors the Anthropic loop (3 attempts, one doubling of `num_predict` when `done_reason == "length"`). Request: `POST {base}/api/chat` with `stream: false`, `format` set to the output schema, system and user messages, `options.temperature = 0`, `options.num_predict`. Token counts come from `prompt_eval_count` and `eval_count`.

Errors: timeout or transport error is retryable; 404 is permanent and says to run `ollama pull <model>`; status >= 500, 408, 429 retryable, other 4xx permanent; non-JSON or non-object body is permanent.
