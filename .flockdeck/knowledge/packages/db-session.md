---
type: Module
title: Database engine and sessions
description: make_engine builds the SQLite async engine with WAL, foreign keys and BEGIN IMMEDIATE write transactions.
resource: src/lens/db/session.py
tags: [database, sqlite]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/db/session.py]
---
`make_engine(settings)` is the only place an engine is built, so API, worker, CLI and tests behave the same.

- The URL must be SQLite (`sqlite+aiosqlite:///...`); any other backend raises `ValueError("DATABASE_URL must be a SQLite URL ...")`. The parent directory of the file is created.
- On connect: `PRAGMA journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON`, `busy_timeout=30000`; the driver's `isolation_level` is set to None so the app decides when a transaction begins.
- On begin: `BEGIN IMMEDIATE`, unless the connection has the `deferred` execution option, in which case plain `BEGIN`.

`make_sessionmaker` uses `expire_on_commit=False`. `read_sessionmaker` adds `deferred=True` for read-only use (GET requests, see [API deps](/packages/api-deps.md)). `get_engine`, `get_sessionmaker` (cached) and `dispose_engine` serve the CLI commands. Rationale in [SQLite transactions](/gotchas/sqlite-begin-immediate.md). Tables are in [data models](/tables/table-sessions.md).
