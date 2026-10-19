---
type: CI Check
title: docs job
description: Renders every Mermaid diagram in a browser and checks that relative markdown links resolve.
resource: .github/workflows/ci.yaml
tags: [ci, docs]
timestamp: 2026-10-19T00:00:00Z
code_paths: [.github/workflows/ci.yaml, packaging/check_docs.py]
---
Installs Playwright Chromium and runs `packaging/check_docs.py` ([tool](/tools/check-docs.md)). Needs network access because Mermaid is loaded from a CDN.
