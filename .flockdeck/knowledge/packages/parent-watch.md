---
type: Module
title: Parent process watch
description: Stops the server when the launcher process that started it is killed outright.
resource: src/lens/parent_watch.py
tags: [process, windows, pyinstaller]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/parent_watch.py, tests/worker/test_parent_watch.py]
---
`watch_parent(on_gone)` is called by [serve](/cli/serve.md) with a callback that sets `server.should_exit`. It starts a daemon thread only when the parent process is the same program as this process, compared by lower-cased file name (`same_program`). This covers the PyInstaller one-file launcher, and a virtualenv `python.exe` on Windows, which run the real program as a child. Running lens from a shell or a script that exits early is unaffected. Returns whether it started.

- Windows: reads the parent's image path with `QueryFullProcessImageNameW` and waits on the parent handle (`SYNCHRONIZE`).
- Other systems: reads the parent command with `ps -o comm= -p <pid>` and polls `os.getppid()` once a second until it changes (reparented).
- Parent pid 1 or lower disables it.

Reason: killing the launcher does not signal the child, which would keep the port and the database open. See [launcher kill](/gotchas/launcher-kill-orphans-server.md). The smoke test covers it ([smoke test](/tools/smoke-test.md)).
