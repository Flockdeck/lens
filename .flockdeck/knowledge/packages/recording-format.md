---
type: Module
title: Recording format detection
description: detect_format tells transcript files from live-hook files and is_agent_prompt filters agent-generated prompts.
resource: src/lens/recording/format.py
tags: [recording, format]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/recording/format.py]
---
Both file kinds are format version 1, so `v` cannot tell them apart.

`detect_format(events)` returns `transcript`, `hooks` or None:

1. The first `recording_started` event's text decides: `start of the transcript` means transcript; `turned on` or `resumed` means hooks.
2. Otherwise any hook-only event type or any `paneName` means hooks.
3. Otherwise any `conversation_title`, `conversation_compacted`, usage, git branch, cwd or agent version means transcript.
4. Else None.

`is_agent_prompt(event)` is true when the text, after left-stripping, starts with text Claude Code writes into the conversation itself: `<task-notification`, `<system-reminder`, `<command-name>`, `<command-message>`, `<local-command-stdout`, `<local-command-stderr`, `<local-command-caveat`, `[Request interrupted by user`, or `This session is being continued from a previous conversation`. Such prompts are not counted as turns and are left out of the digest.
