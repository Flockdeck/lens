---
type: Module
title: Filesystem recording store
description: FilesystemStore keeps raw recordings as files under the data directory with atomic writes and path-escape checks.
resource: src/lens/storage/filesystem.py
tags: [storage, filesystem, security]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/storage/filesystem.py]
---
- `_path(key)` rejects keys that are empty, contain NUL, a backslash or a colon, are not in canonical POSIX form (`//`, `/./`, trailing slash), are absolute, contain `.` or `..` parts, or resolve (symlinks included) outside the root. Failure raises `InvalidKey`. See [store key validation](../security/store-key-validation.md).
- `_put` writes to a temp file `.tmp-*` in the target directory, `fsync`s, sets mode 0600 (non-Windows) and `os.replace`s into place, so readers never see a partial file. Directories are created with mode 0700 where supported; on Windows the profile ACLs apply.
- `_get` raises `RecordingExpired` for a missing file or a directory.
- `_delete` unlinks (a missing file is fine) and then removes now-empty parent directories up to, not including, the root.
- `_ping` creates the root and checks it is writable.
- All operations run in `asyncio.to_thread`.

Windows handling: [extended path prefix](../gotchas/windows-extended-path-prefix.md) and [directory creation race](../gotchas/windows-mkdir-permission-error.md).
