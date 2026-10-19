---
type: Developer Tool
title: Makefile targets
description: Developer shortcuts for install, run, lint, typecheck, test, e2e, binary and smoke.
resource: Makefile
tags: [tools, dev]
timestamp: 2026-10-19T00:00:00Z
code_paths: [Makefile]
---
| Target | Runs |
|---|---|
| `install` | `uv sync` |
| `run` | `uv run lens serve --open` (the whole service on `http://127.0.0.1:8000`) |
| `lint` | `ruff check .` and `ruff format --check .` |
| `format` | `ruff check --fix .` and `ruff format .` |
| `typecheck` | `mypy --strict src` |
| `test` | `pytest` |
| `e2e` | `pytest tests/e2e -m "not browser"` |
| `e2e-browser` | `pytest tests/e2e -m browser` (needs Edge or `playwright install chromium`) |
| `check` | lint, typecheck, test |
| `binary` | PyInstaller build ([spec](/release/pyinstaller-spec.md)) |
| `smoke` | binary, then [smoke test](/tools/smoke-test.md) |
| `clean` | remove `dist` and `build` |
