---
type: Module
title: Settings class
description: pydantic-settings class that reads every runtime option from the environment and an optional .env file.
resource: src/lens/config.py
tags: [config]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py]
---
`Settings` (pydantic-settings `BaseSettings`) has no prefix: field names are the upper-case env var names. `.env` in the working directory is read too, `extra` is ignored, and environment variables win over `.env`. `get_settings()` caches one instance with `lru_cache`.

Fields and defaults:

| Field | Default | Page |
|---|---|---|
| `database_url` | empty, then `sqlite+aiosqlite:///<data_dir>/lens.db` | [DATABASE_URL](/config/database-url.md) |
| `allowed_hosts` | `127.0.0.1`, `localhost`, `::1` | [ALLOWED_HOSTS](/config/allowed-hosts.md) |
| `enricher` | `mock` | [ENRICHER](/config/enricher.md) |
| `anthropic_api_key`, `anthropic_model`, `anthropic_workspace_id` | none, `claude-haiku-4-5`, none | [key](/config/anthropic-api-key.md), [model](/config/anthropic-model.md), [workspace](/config/anthropic-workspace-id.md) |
| `ollama_url`, `ollama_model`, `ollama_timeout_seconds` | `http://127.0.0.1:11434`, `llama3.1:8b`, 120 | [URL](/config/ollama-url.md), [model](/config/ollama-model.md), [timeout](/config/ollama-timeout-seconds.md) |
| `max_file_bytes`, `max_files_per_batch`, `max_request_bytes` | 17 MiB, 100, 256 MiB | [file](/config/max-file-bytes.md), [files](/config/max-files-per-batch.md), [request](/config/max-request-bytes.md) |
| worker fields | see [worker config](/packages/worker-loop.md) | [concurrency](/config/worker-concurrency.md) and others |
| `data_dir`, `raw_retention_days`, `store_prefix` | per-user data dir, 30, `recordings/` | [DATA_DIR](/config/data-dir.md), [RAW_RETENTION_DAYS](/config/raw-retention-days.md), [STORE_PREFIX](/config/store-prefix.md) |
| `log_level`, `log_file` | `INFO`, empty | [LOG_LEVEL](/config/log-level.md), [LOG_FILE](/config/log-file.md) |
| `host`, `port` | `127.0.0.1`, 8000 | [HOST](/config/host.md), [PORT](/config/port.md) |

A model validator fills `database_url` from `data_dir` when blank. The anthropic key is a `SecretStr`. Six enrichment fields can be overridden from the UI, see [runtime settings](/packages/runtime-settings.md).
