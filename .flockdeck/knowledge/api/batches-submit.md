---
type: HTTP Endpoint
title: POST /batches
description: Uploads one or more .jsonl recordings as a multipart batch and queues them for analysis.
resource: src/lens/api/routers/batches.py
tags: [api, upload]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/routers/batches.py, src/lens/api/uploads.py, src/lens/api/limits.py]
---
Request: `multipart/form-data` with repeated `files` parts. Limits: at most [MAX_FILES_PER_BATCH](/config/max-files-per-batch.md) files and 10 fields (more gives 400 `malformed multipart request`), each file under [MAX_FILE_BYTES](/config/max-file-bytes.md), whole body under [MAX_REQUEST_BYTES](/config/max-request-bytes.md) (413 `request too large`, see [limit](/packages/api-limits.md)).

Per file ([validation](/packages/api-uploads.md)): rejected files are listed with a reason and the others continue. Each accepted file is stored immediately, one in memory at a time, via [store_raw](/packages/worker-queue.md), then the batch and its items are created in one commit.

Responses:

| Status | Body |
|---|---|
| 202 | `{id, accepted: [filenames], rejected: [{filename, reason}]}` |
| 422 | `{detail: "no acceptable files", rejected: [...]}`; the transaction is rolled back |
| 503 | `object store unavailable` (store build or put failure) |
| 400 | malformed multipart |

If a later step fails after some files were put, those files stay in the store unreferenced (their rows roll back with the transaction). The accepted names are echoed back; request content is never logged. Models: [schemas](/packages/api-schemas.md).
