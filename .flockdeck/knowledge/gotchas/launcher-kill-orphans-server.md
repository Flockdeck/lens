---
type: Gotcha
title: Killing the launcher can orphan the server
description: The packaged program is a launcher plus a child; a hard kill of the launcher would leave the child holding the port and database.
resource: src/lens/parent_watch.py
tags: [pyinstaller, process]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/parent_watch.py, packaging/smoke.py, packaging/lens.spec]
---
PyInstaller's one-file mode unpacks itself and runs the real program as a child process; on Windows a virtualenv's `python.exe` does the same. Task Manager or another program stopping the launcher does not signal the child. [parent watch](/packages/parent-watch.md) asks the server to shut down gracefully when the parent dies. The smoke test's last phase kills the launcher with a hard kill and expects the port to stop answering; its `stop()` helper also waits until nothing listens, because on Windows the child can outlive the launcher briefly and a restart on the same port could hit the old process.
