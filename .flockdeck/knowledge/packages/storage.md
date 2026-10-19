---
type: Module
title: Recording store protocol
description: RecordingStore is the async interface for raw recording bytes; build_store returns the filesystem implementation.
resource: src/lens/storage/base.py
tags: [storage]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/storage/base.py, src/lens/storage/__init__.py, src/lens/storage/memory.py]
---
Protocol methods: `put(key, data)`, `get(key)` (raises `RecordingExpired` if missing), `delete(key)` (idempotent), `ping()` (used by [/readyz](/api/readyz.md)), `aclose()`.

`build_store(settings)` always returns a [FilesystemStore](/packages/storage-filesystem.md) rooted at `DATA_DIR` (home expanded). There is no other backend. `InMemoryStore` (`memory.py`) is a dict-backed test double with `fail_put` and `closed` flags.

Keys look like `recordings/YYYY/MM/<uuid>.jsonl`, see [object key](/tables/object-key.md).
