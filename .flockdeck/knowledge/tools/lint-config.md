---
type: Developer Tool
title: Lint and type-check configuration
description: ruff and mypy settings in pyproject.toml.
resource: pyproject.toml
tags: [tools, lint]
timestamp: 2026-10-19T00:00:00Z
code_paths: [pyproject.toml]
---
Ruff: line length 100, target `py312`, rules E, F, I, UP, B, ASYNC, excluding `docs` and `*.md`. mypy: `strict = true`, plugin `pydantic.mypy`, `mypy_path = src`. pytest: `asyncio_mode = "auto"`, `testpaths = ["tests"]`, marker `browser`. Runtime dependencies: fastapi, uvicorn[standard], python-multipart, sqlalchemy[asyncio], alembic, pydantic, pydantic-settings, httpx, anthropic, prometheus-client, aiosqlite, platformdirs. Python 3.12 or later. Build backend hatchling, wheel packages `src/lens`. Run by [static checks](../ci/static-checks.md) and the [Makefile](makefile.md).
