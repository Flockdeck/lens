---
type: Gotcha
title: Logs go to a file when stdout is a pipe
description: With LOG_FILE unset and no terminal, logs are written to lens.log so an unread pipe cannot freeze the server.
resource: src/lens/api/logging.py
tags: [logging, launcher]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/logging.py, packaging/smoke.py]
---
The comment in `log_destination` explains: a program that starts lens and reads its output through a pipe it never empties would freeze lens once the pipe fills, since every request is logged. So the automatic choice is standard output only in a terminal. A launcher that wants logs on stdout sets `LOG_FILE=-` and must read the output ([LOG_FILE](../config/log-file.md)). The smoke test checks both: the default phase starts the binary with an unread pipe and expects `lens.log` to be non-empty; the Flockdeck-style phase sets `LOG_FILE=-` and drains the output in a thread.
