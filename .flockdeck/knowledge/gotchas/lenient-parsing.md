---
type: Gotcha
title: The parser is deliberately lenient
description: Bad lines, a cut last line, unknown fields and unknown event types are tolerated; only another version number or no events fails.
resource: src/lens/recording/parser.py
tags: [recording, parser]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/recording/parser.py, tests/recording/test_parser.py, tests/fixtures/build.py]
---
Failures that stop a file: `v` other than 1 (`UnsupportedVersion`, permanent) and no usable events (`EmptyRecording`, permanent). Everything else becomes a counted warning: malformed lines, an unterminated last line, unknown event types, sequence gaps. Invalid UTF-8 damages only its own line. JSON that is too deeply nested or has an oversized number is a bad line, not a crash (`RecursionError` and `ValueError` are caught). Fixtures cover wrong version, truncated, cut-off last line, unknown types and empty files. See [parser](/packages/recording-parser.md).
