---
type: Developer Tool
title: packaging/check_docs.py
description: Renders Mermaid diagrams and checks relative links in the repository's markdown files.
resource: packaging/check_docs.py
tags: [tools, docs]
timestamp: 2026-10-19T00:00:00Z
code_paths: [packaging/check_docs.py]
---
Walks all `*.md` files outside `.venv`, `node_modules`, `dist`, `build` and `.git`. Relative links (not URLs, not in-page anchors, outside code fences) must point to an existing file. Each fenced `mermaid` block is rendered with Mermaid 11 loaded from a CDN in Playwright's Chromium (Edge first, else Chromium) with `securityLevel: strict`. Prints the counts and `FAIL ...` lines; exit 1 on any failure. Run by the [docs job](../ci/docs-check.md).
