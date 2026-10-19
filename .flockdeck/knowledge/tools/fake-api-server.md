---
type: Developer Tool
title: tests/web/fake_server.py
description: Stdlib fake of the lens HTTP API for developing and testing the UI without the real stack.
resource: tests/web/fake_server.py
tags: [tools, web, testing]
timestamp: 2026-10-19T00:00:00Z
code_paths: [tests/web/fake_server.py, tests/web/test_fake_server.py]
---
`python tests/web/fake_server.py [--port 8765]` serves the static UI from `src/lens/web` and canned deterministic JSON for the API. Behaviours for exercising the UI: batches advance on each GET (queued, running, done); a file named `bad*.jsonl` fails; non-`.jsonl`, empty and over-17-MiB files are rejected per file and no accepted files gives 422; the session with the highest id has an expired raw recording, so `raw_available` is false and events and enrich return 410. Contract-level behaviour is documented in the [API pages](/api/batches-submit.md).
