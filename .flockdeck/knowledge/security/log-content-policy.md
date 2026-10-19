---
type: Security Boundary
title: Log content policy
description: Logs carry ids, counts, timings and exception types only; never recording content, filenames, query strings or messages.
resource: src/lens/api/logging.py
tags: [security, logging, privacy]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/logging.py, src/lens/api/app.py, tests/api/test_privacy.py, tests/api/test_logging.py]
---
Rules visible in code:

- Exceptions are logged as type plus `file:line function` frames, not messages, because messages can echo recording content ([formatter](/packages/api-logging.md)).
- The request log line has method, matched route pattern, status and duration; uvicorn's access log (which includes query strings) is disabled. A test asserts logs contain no query strings or filenames.
- Refused requests log reason, method and status, not the Host or Origin ([guard](/security/local-only-guard.md)).
- Item errors stored in the database are built by [classify](/packages/worker-retry.md): text only for exception types whose messages the code controls.
- Enrichment parse failures log counts and stop reasons only.
- Database statement logging stays at WARNING.
