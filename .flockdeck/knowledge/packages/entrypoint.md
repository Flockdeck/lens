---
type: Module
title: lens entry point and CLI parser
description: python -m lens and the packaged binary both call lens.cli.main, which defaults to the serve command.
resource: src/lens/cli.py
tags: [cli, entrypoint]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/cli.py, src/lens/__main__.py, src/lens/_version.py, pyproject.toml]
---
`lens` is a Python 3.12 package (`src/lens`) built with hatchling. The console script `lens` points at `lens.cli:main` (`[project.scripts]` in `pyproject.toml`). `src/lens/__main__.py` runs the same `main` and calls `multiprocessing.freeze_support()` first, which matters for the frozen Windows binary.

`main(argv)` parses the arguments with argparse. When no sub-command is present it re-parses as `serve` plus the given arguments. It then calls `configure_logging` (see [logging](api-logging.md)) and runs the command.

Commands: [serve](../cli/serve.md), [cleanup](../cli/cleanup.md), [check-storage](../cli/check-storage.md), [version](../cli/version.md).

The version string comes from `src/lens/_version.py` (`__version__`, read with `app_version()`). The build rewrites that file from the release tag, see [version stamping](../release/version-stamp.md).

Package layout: `api/` (FastAPI app and routers), `db/` (SQLAlchemy models, engine, Alembic runner), `enrich/` (enrichers), `recording/` (parser and metrics), `storage/` (raw file store), `worker/` (queue, claim loop, cleanup), `web/` (static UI), `migrations/`, plus `config.py`, `runtime_settings.py` and `parent_watch.py`.
