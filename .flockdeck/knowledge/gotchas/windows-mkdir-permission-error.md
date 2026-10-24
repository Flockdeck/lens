---
type: Gotcha
title: Windows reports access denied when a directory is being created
description: _mkdirs swallows PermissionError if the directory exists afterwards.
resource: src/lens/storage/filesystem.py
tags: [windows, race]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/storage/filesystem.py]
---
When two uploads create the same `YYYY/MM` directory at once, Windows may raise "access denied" rather than "exists" in the loser. `_mkdirs` catches `PermissionError` and re-raises only if the path is still not a directory. See [filesystem store](../packages/storage-filesystem.md).
