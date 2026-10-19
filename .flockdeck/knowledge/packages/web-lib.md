---
type: Module
title: Web UI helpers
description: Pure helper functions and the glossary used by the UI, testable under node.
resource: src/lens/web/js/lib.js
tags: [web, ui]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/web/js/lib.js, tests/web/helpers.test.mjs]
---
No DOM access. Notable parts:

- `MAX_FILE_BYTES` (17 MiB) and `MAX_FILES` (100) mirror the server defaults ([MAX_FILE_BYTES](/config/max-file-bytes.md), [MAX_FILES_PER_BATCH](/config/max-files-per-batch.md)); the UI checks files against them before upload (`checkFiles`: must end in `.jsonl`, not empty, not over the limit, within the count).
- `mergeFiles` drops exact duplicates by name, size and modified time.
- `batchActive(batch)` is true while queued plus running items remain; the batch view polls while it is true.
- `parseHash` splits `#/a/b?x=y`.
- Status text from `GET /config`: `isLocalOnly` requires storage `filesystem` and enricher `mock` or `ollama`; `isRemoteEnrichment` is true for `anthropic`; `statusLine` and `statusDetails` word this ("Local only", "Sends digests to Anthropic", "Not verified as local-only"), plus retention text.
- `GLOSSARY` separates facts computed from the recording from judgements made by the LLM.
