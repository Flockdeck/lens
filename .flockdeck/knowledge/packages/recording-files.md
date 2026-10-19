---
type: Module
title: Files touched extraction
description: extract_files_touched lists distinct files read and edited and the Bash commands run.
resource: src/lens/recording/files.py
tags: [recording, files]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/recording/files.py]
---
Read tools: `Read`, `NotebookRead`. Edit tools: `Edit`, `MultiEdit`, `Write`, `NotebookEdit`. The path comes from the tool input keys `file_path`, `notebook_path` or `path`, whichever is a non-empty string first.

Paths are distinct and in first-seen order. A call whose `tool_result` has `isError` is left out of the file lists (it did not touch the file); Bash commands are kept either way, each clipped to 300 characters. Each list keeps the latest 500 entries (`MAX_ITEMS`); `read_total`, `edited_total` and `commands_total` count everything, and the parser adds a warning when a total passes 500. Shape: `FilesTouched` in [recording models](recording-models.md); stored as `files_touched` in [sessions](../tables/table-sessions.md).
