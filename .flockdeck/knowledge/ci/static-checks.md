---
type: CI Check
title: static job
description: Lockfile, ruff, mypy strict on three platforms, actionlint, shellcheck and the notices check.
resource: .github/workflows/ci.yaml
tags: [ci, lint]
timestamp: 2026-10-19T00:00:00Z
code_paths: [.github/workflows/ci.yaml, pyproject.toml, Makefile]
---
Steps: `uv lock --check`; `ruff check .` and `ruff format --check .`; `mypy --strict --platform` for `linux`, `win32` and `darwin` over `src` (some code is platform specific, such as [parent watch](../packages/parent-watch.md)); `actionlint` through `uvx --from actionlint-py`; `shellcheck packaging/publish-downloads.sh`; and `third_party_notices.py --check` ([notices](../release/third-party-notices.md)). Ruff selects E, F, I, UP, B, ASYNC with line length 100 and target py312, excluding `docs` and `*.md`; mypy runs strict with the pydantic plugin. Timeout 15 minutes.
