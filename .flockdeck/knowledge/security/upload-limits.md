---
type: Security Boundary
title: Upload limits
description: Caps on file size, file count, field count, request size and filename length for uploads.
resource: src/lens/api/uploads.py
tags: [security, upload, dos]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/uploads.py, src/lens/api/limits.py, src/lens/api/routers/batches.py, src/lens/config.py]
---
| Limit | Value | Where |
|---|---|---|
| request body | [MAX_REQUEST_BYTES](../config/max-request-bytes.md), declared or streamed | [BodySizeLimit](../packages/api-limits.md), 413 |
| files per batch | [MAX_FILES_PER_BATCH](../config/max-files-per-batch.md) | multipart parser, 400 |
| form fields | 10 | multipart parser |
| file size | [MAX_FILE_BYTES](../config/max-file-bytes.md), read in 1 MiB chunks | [check_file](../packages/api-uploads.md) |
| file name | 255 characters, basename only | `clean_filename` |
| type | `.jsonl` only | `check_file` |

Only one file's bytes are held in memory at a time. The filename is reduced to a basename (backslashes treated as separators) and is never used as a path: files are stored under generated UUID keys ([object key](../tables/object-key.md)).
