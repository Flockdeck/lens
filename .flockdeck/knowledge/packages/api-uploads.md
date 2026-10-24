---
type: Module
title: Upload file validation
description: check_file validates one multipart part by name, extension, size and emptiness.
resource: src/lens/api/uploads.py
tags: [api, upload]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/uploads.py, src/lens/api/schemas.py]
---
Used by [POST /batches](../api/batches-submit.md).

- `clean_filename(raw)` turns backslashes into slashes, keeps the POSIX basename and strips whitespace; an empty result becomes `(unnamed)`.
- `read_limited(file, limit)` reads in 1 MiB chunks and returns None as soon as the total passes the limit (it first checks `file.size`).
- `check_file(file, settings)` returns `(name, bytes)` or `(name, RejectedFile)`. Checks in order: name longer than 255 characters (`filename too long`, name cut to 255), extension not `.jsonl` case-insensitively (`wrong type: only .jsonl files accepted`), size over [MAX_FILE_BYTES](../config/max-file-bytes.md) (`too large: limit is N bytes`), content empty after strip (`empty`).

Rejection reasons are returned per file in the `rejected` list; they never contain file content.
