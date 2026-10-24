---
type: CLI Command
title: lens check-storage
description: Writes, reads back and deletes a small probe file in the data directory to prove it is usable.
resource: src/lens/cli.py
tags: [cli, storage]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/cli.py]
---
`lens check-storage` prints `data directory: <path>`, calls `store.ping()`, puts `{"probe":true}` under `<STORE_PREFIX>probe/<uuid>.jsonl`, reads it back, compares and deletes it. Output `probe ok: put, get and delete work` and exit 0; `probe failed: read back different bytes` or `probe failed (<ExceptionType>)` with exit 1. The error message text is not printed, only the type.

Uses the [filesystem store](../packages/storage-filesystem.md) and [DATA_DIR](../config/data-dir.md).
