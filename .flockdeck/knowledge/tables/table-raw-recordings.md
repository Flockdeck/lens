---
type: Database Table
title: Table raw_recordings
description: One row per stored upload; the bytes are a file in the data directory.
resource: src/lens/db/models.py
tags: [database, table, storage]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/db/models.py, src/lens/migrations/versions/0001_initial_schema.py]
---
Columns: `id`, `content_hash` (SHA-256 hex, indexed), `size_bytes`, `object_key` (unique, up to 255, see [object key](object-key.md)), `created_at` (indexed), `expired_at` (indexed, null while the file should exist). Expiry is set by [cleanup](../packages/worker-cleanup.md) or when a read finds the file gone. `content_hash` of the newest raw is copied to the session so identical re-uploads skip re-enrichment ([processor](../packages/worker-processor.md)).
