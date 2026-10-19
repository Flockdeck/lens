---
type: File Format
title: Raw recording object key
description: Format of the key under which a raw recording is stored in the data directory.
resource: src/lens/worker/queue.py
tags: [storage, format]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/worker/queue.py, src/lens/storage/filesystem.py]
---
`<STORE_PREFIX>YYYY/MM/<uuid4>.jsonl`, for example `recordings/2026/10/<uuid>.jsonl`. The year and month are the upload time in UTC. The key is a relative path under [DATA_DIR](../config/data-dir.md); [store key validation](../security/store-key-validation.md) rejects anything else. Empty year and month directories are removed after a delete.
