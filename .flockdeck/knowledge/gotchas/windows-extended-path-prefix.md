---
type: Gotcha
title: Windows extended path prefix
description: Path.resolve() can return a prefixed path on Windows, so the store strips the prefix before comparing paths.
resource: src/lens/storage/filesystem.py
tags: [windows, storage]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/storage/filesystem.py]
---
On Windows the same place can be spelled with a plain drive path or with a double-backslash, question mark, backslash prefix (and a UNC variant). `Path.resolve()` returns the second form for a path under a directory another thread is creating at that moment, so comparing it with the first would say the key escapes the root. `strip_extended_prefix` normalises both. The root is also created before it is resolved, because an existing directory resolves to its long name while one that does not exist yet keeps a short 8.3 name (for example on CI runners). See [filesystem store](../packages/storage-filesystem.md).
