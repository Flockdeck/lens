---
type: Database Table
title: Table batches
description: One row per upload batch with a rolled-up status.
resource: src/lens/db/models.py
tags: [database, table]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/db/models.py, src/lens/migrations/versions/0001_initial_schema.py]
---
Columns: `id`, `status` (enum `queued`, `running`, `done`, `cancelled`; default queued), `created_at` (naive UTC). Index on (`created_at`, `status`). Has many [batch_items](/tables/table-batch-items.md) (cascade). `done` means every item has finished, some possibly failed; `cancelled` is sticky until a retry ([queue](/packages/worker-queue.md)). Batches that are done or cancelled for more than 90 days are deleted by [cleanup](/packages/worker-cleanup.md).
