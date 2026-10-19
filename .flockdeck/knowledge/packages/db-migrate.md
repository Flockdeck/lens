---
type: Module
title: Alembic migration runner
description: upgrade_async runs alembic upgrade head on every start of serve and cleanup.
resource: src/lens/db/migrate.py
tags: [database, alembic]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/db/migrate.py, src/lens/migrations/env.py, src/lens/migrations/script.py.mako, alembic.ini]
---
`upgrade(settings)` runs `command.upgrade(config, "head")` with `script_location` set to the packaged `migrations` directory and the database URL passed through `cfg.attributes["url"]`. `upgrade_async` runs it in a thread, because Alembic's `env.py` starts its own event loop. `head_revision()` returns the current head.

`migrations/env.py` takes the URL from that attribute or else from `get_settings()`, builds the engine through `make_engine` (same pragmas), and configures `compare_type=True` and `render_as_batch=True` because SQLite cannot alter most things in place. Offline mode renders literal SQL.

There is a single revision, [0001](/tables/migration-0001.md). There is no separate migration command: [serve](/cli/serve.md) and [cleanup](/cli/cleanup.md) migrate on start. `alembic.ini` sets `script_location` to `src/lens/migrations` and `prepend_sys_path = src` for developer use.
