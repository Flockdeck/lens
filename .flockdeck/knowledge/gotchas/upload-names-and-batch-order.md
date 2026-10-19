---
type: Gotcha
title: Upload response lists names, not ids
description: POST /batches echoes accepted file names; item ids come from GET /batches/{id}.
resource: src/lens/api/routers/batches.py
tags: [api, upload]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/routers/batches.py, src/lens/api/schemas.py]
---
`accepted` holds the cleaned filenames and `rejected` holds `{filename, reason}`. Two files may share a name; the batch items are told apart by id only. The UI keeps rejections in `sessionStorage` under `lens.rejected.<batch id>` so the batch page can show them after navigation ([submit view](/packages/web-views.md)).
