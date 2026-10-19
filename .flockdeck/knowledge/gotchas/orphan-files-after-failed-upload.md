---
type: Gotcha
title: Failed uploads can leave unreferenced files
description: The file is stored before its row is written, so a later failure leaves an orphan file but never a dangling row.
resource: src/lens/worker/queue.py
tags: [storage, upload]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/worker/queue.py, src/lens/api/routers/batches.py]
---
`store_raw` puts the file and then adds the row. If the transaction later rolls back, the file remains with no row pointing at it. The code accepts this as harmless; cleanup works from rows, so such files are not expired. See [POST /batches](/api/batches-submit.md).
