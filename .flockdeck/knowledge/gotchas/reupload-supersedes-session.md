---
type: Gotcha
title: Re-uploading a session overwrites it
description: A recording with an existing session id replaces the stored session in place, and identical content skips re-enrichment.
resource: src/lens/worker/processor.py
tags: [worker, sessions]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/worker/processor.py, src/lens/db/models.py]
---
`sessions.recording_session` is unique. A longer upload of the same session recomputes metrics and points `raw_id` at the newest raw file. If the stored `content_hash` equals the new raw hash and an enrichment already exists, the item finishes without calling the enricher. Otherwise the enrichment is regenerated and overwritten. Two workers inserting the same session at once are handled by a savepoint and retry ([processor](../packages/worker-processor.md)).
