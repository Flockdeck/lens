---
type: HTTP Endpoint
title: GET /sessions/{session_id}/events
description: Returns a page of parsed events from the stored raw recording.
resource: src/lens/api/routers/sessions.py
tags: [api, sessions, recording]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/routers/sessions.py]
---
Query: `after_seq` (0 or more, default 0) and `limit` (1 to 1000, default 200). Fetches the raw file from the store without holding a database transaction, parses it in a thread, keeps events with `seq > after_seq`, and returns `{items, next_after_seq}` where `next_after_seq` is the last seq of the page when more follow, else null. Events are serialised with their envelope aliases (for example `toolUseId`).

Errors: 404 unknown session; 410 `raw recording has expired or been deleted` when there is no raw, the row is expired, or the file is missing (a missing file also sets `expired_at` so `raw_available` turns false); 422 `recording could not be parsed`; 503 when the store fails.
