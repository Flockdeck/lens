---
type: Database Table
title: Alembic migration 0001
description: The single initial schema revision creating all six tables and their indexes.
resource: src/lens/migrations/versions/0001_initial_schema.py
tags: [database, migration]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/migrations/versions/0001_initial_schema.py]
---
Revision `0001`, no parent. Creates `app_settings`, `batches`, `raw_recordings`, `sessions`, `batch_items` and `enrichments` with the indexes listed on each table page ([batches](table-batches.md), [batch_items](table-batch-items.md), [raw_recordings](table-raw-recordings.md), [sessions](table-sessions.md), [enrichments](table-enrichments.md), [app_settings](table-app-settings.md)). Runs on every start ([migrate](../packages/db-migrate.md)); tests build their databases with it.
