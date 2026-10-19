---
type: Developer Tool
title: Test suite layout
description: pytest tests for API, worker, recording, enrichment, packaging and end-to-end flows, plus node tests for the UI.
resource: tests/conftest.py
tags: [tools, testing]
timestamp: 2026-10-19T00:00:00Z
code_paths: [tests/conftest.py, tests/dbutil.py, tests/api/conftest.py, tests/e2e/conftest.py, tests/web/helpers.test.mjs, tests/web/modules.test.mjs, pyproject.toml]
---
| Directory | Covers |
|---|---|
| `tests/api` | endpoints against an in-memory store: batches, sessions, settings, health, hardening (413 on chunked uploads, 503 and 502 mapping, re-enrich conflicts, date filters), privacy (no-store, no CORS, log content), local-only guard |
| `tests/recording` | parser, metrics, risk rules, digest, transcript and hooks fixtures |
| `tests/enrich` | mock, Anthropic (fake client), Ollama, prompt bounds, dynamic enricher |
| `tests/worker` | claim, queue, retry, processor, loop, cleanup, filesystem store, migrations, parent watch, CLI and serve commands |
| `tests/e2e` | real app, worker, SQLite and filesystem store in one process with the mock enricher; `test_browser.py` drives a real browser (marker `browser`) |
| `tests/packaging` | release signing and publish-script behaviour |
| `tests/web` | JS helpers and module parse checks under node, design-token checks, a fake API server |
| `tests/test_legal.py` | licence and notices consistency |

`tests/conftest.py` builds one throwaway SQLite database by running the real Alembic migration, and pins `LOG_FILE=-`, `ENRICHER=mock`, an empty `ANTHROPIC_API_KEY` and the Ollama and model defaults so a developer's `.env` cannot make tests call the API ([dotenv](/config/dotenv-file.md)). Fixtures: [test fixtures](/tools/test-fixtures.md). Run in CI by the [test job](/ci/test-matrix.md).
