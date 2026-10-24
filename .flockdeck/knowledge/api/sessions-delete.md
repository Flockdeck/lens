---
type: HTTP Endpoint
title: DELETE /sessions/{session_id}
description: Deletes a session, its enrichment and its raw recordings.
resource: src/lens/api/routers/sessions.py
tags: [api, sessions, deletion]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/routers/sessions.py, src/lens/worker/queue.py]
---
404 if missing. Raw rows are found through the session (`sessions.raw_id` and `batch_items.session_id`), so `delete_raws_for_session` runs first ([queue](../packages/worker-queue.md)), then the enrichment and session rows, in one commit. Object deletion is best effort. Returns 204. Foreign keys to raw rows are `SET NULL`, so the order is safe.
