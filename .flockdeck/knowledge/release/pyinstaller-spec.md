---
type: Build Step
title: PyInstaller spec
description: packaging/lens.spec builds one self-contained console executable per platform.
resource: packaging/lens.spec
tags: [build, pyinstaller]
timestamp: 2026-10-19T00:00:00Z
code_paths: [packaging/lens.spec, Makefile]
---
Command: `uv run pyinstaller packaging/lens.spec --noconfirm --distpath dist --workpath build` (also `make binary`). Output `dist/lens`, or `dist/lens.exe` on Windows.

- Entry script: `src/lens/__main__.py`.
- Hidden imports: all `uvicorn` submodules (loop, protocol and websocket implementations are picked by name), `aiosqlite` and the SQLite dialects, `alembic.ddl` submodules and `alembic.operations.ops`, the three enricher modules (loaded lazily by [build_enricher](../packages/enrich.md)), and `anthropic` submodules except those mentioning aiohttp.
- Data files: `src/lens/web` as `lens/web` and `src/lens/migrations` as `lens/migrations`.
- Excludes: tkinter, pytest, playwright, mypy, ruff, aioboto3, botocore.
- `console=True` (a terminal program), `upx=False`, `strip=False`.

Notes in [frozen binary specifics](../gotchas/frozen-binary-startup.md) and [native runners](../gotchas/build-needs-native-runner.md). Used by the [build workflow](../ci/build-workflow.md).
