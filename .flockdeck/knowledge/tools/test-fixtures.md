---
type: Developer Tool
title: Recording fixtures generator
description: tests/fixtures/build.py generates the .jsonl fixtures and a test checks the committed files match.
resource: tests/fixtures/build.py
tags: [tools, testing, recording]
timestamp: 2026-10-19T00:00:00Z
code_paths: [tests/fixtures/build.py, tests/fixtures/recording-line.schema.json, tests/recording/test_fixtures.py]
---
`python tests/fixtures/build.py` rewrites the fixtures next to it from a small `Recording` builder using the envelope of [format v1](/tables/recording-line.md): `claude_full`, `chat_client`, `transcript_full`, `transcript_minimal`, `transcript_truncated`, `truncated`, `cut_off_last_line`, `start_stop_only`, `missing_tool_result`, `unknown_types_and_fields`, `wrong_version` and `empty`. Edit the script, not the files. `.gitattributes` marks `*.jsonl` as `-text` so line endings are kept on every platform.
