---
type: HTTP Endpoint
title: Static web UI at /
description: All other paths serve the bundled web UI files with revalidation and no Python sources.
resource: src/lens/api/app.py
tags: [api, static]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/app.py, src/lens/web/index.html]
---
`WebFiles(directory=<lens.web package dir>, html=True)` is mounted at `/` after the routers. `/` serves `index.html`. Paths ending `.py` or `.pyc` return 404. Every response has `Cache-Control: no-cache`, so the browser revalidates (cheap 304) and never mixes old scripts with a new binary. UI responses are not `no-store` ([privacy test](/tools/test-suite.md)). See [web UI](/packages/web-ui.md).
