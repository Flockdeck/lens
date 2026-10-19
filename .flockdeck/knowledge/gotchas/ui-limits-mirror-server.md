---
type: Gotcha
title: UI limits mirror server defaults
description: lib.js hard-codes 17 MiB and 100 files; changing the server settings does not change the UI pre-check.
resource: src/lens/web/js/lib.js
tags: [web, config]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/web/js/lib.js, src/lens/config.py]
---
`MAX_FILE_BYTES` and `MAX_FILES` in `lib.js` carry the comment "mirrors Settings". The server remains the authority; it rejects over-limit files per file regardless. See [MAX_FILE_BYTES](/config/max-file-bytes.md) and [MAX_FILES_PER_BATCH](/config/max-files-per-batch.md).
