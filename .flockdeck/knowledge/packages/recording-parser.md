---
type: Module
title: Recording parser
description: Tolerant reader for Flockdeck recording format v1 that turns bytes into events and computes an Analysis.
resource: src/lens/recording/parser.py
tags: [recording, parser]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/recording/parser.py, src/lens/recording/__init__.py]
---
Input format: [recording line](../tables/recording-line.md).

- `parse_lines(lines)` skips blank lines; a line that is not JSON, or JSON that is not an object, or fails envelope validation counts as malformed. The last non-blank line failing is reported as `unterminated last line` instead of a malformed count. A leading byte-order mark is stripped from line 1. A `v` present and different from 1 (or a boolean) raises `UnsupportedVersion` (permanent failure). Safe on a page that starts mid-file.
- `parse(data)` splits bytes on `\n`, decodes each line with `errors="replace"` (invalid UTF-8 damages only its own line) and raises `EmptyRecording` when no events remain.
- `EventList` is a list subclass that carries `warnings`; copying or slicing it loses them.
- `analyze(events, parse_warnings=None)` computes [metrics](recording-metrics.md), [completeness](../tables/completeness.md), [risky actions](recording-risk.md), [files touched](recording-files.md) and the [digest](recording-digest.md), and returns an [Analysis](recording-models.md). The session id, pane and start time come from the first event; project, agent, model, pane name and conversation from the first event that has them.

Warnings (counts only): unknown event types, truncated at the size cap, cut off with no stop line, agent records only start and stop lines, tool calls without a result, file lists capped at 500, lines missing from the sequence, lines with redacted or clipped content.

`analyze_lines` is `parse_lines` plus `analyze`. Parsing and analysis run in `asyncio.to_thread` in the worker and API because files can reach 16 MiB.
