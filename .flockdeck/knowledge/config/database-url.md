---
type: Environment Variable
title: DATABASE_URL
description: SQLAlchemy URL of the database; only SQLite is accepted.
resource: src/lens/config.py
tags: [config, env]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py]
---
Default: empty (then a SQLite file in the data directory).

Read by `Settings` ([settings class](/packages/config-settings.md)) from the environment or the `.env` file.

When blank, the URL becomes `sqlite+aiosqlite:///<DATA_DIR>/lens.db` (path in POSIX form). Any other backend is refused by [make_engine](/packages/db-session.md) with `DATABASE_URL must be a SQLite URL`. The directory of the file is created. Used by the API, the worker, the CLI commands and Alembic ([migrations](/packages/db-migrate.md)).
