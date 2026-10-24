---
type: Gotcha
title: SQLite write transactions begin immediately
description: Writers use BEGIN IMMEDIATE and readers BEGIN deferred so writers queue and reads never hold the write lock.
resource: src/lens/db/session.py
tags: [database, sqlite, concurrency]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/db/session.py, src/lens/api/deps.py]
---
A deferred transaction that reads and then writes can fail at once with "database is locked" when another writer got in between, whatever the busy timeout (30 s). `make_engine` therefore issues `BEGIN IMMEDIATE` for all normal sessions so writers wait in line. Transactions must stay short: the LLM call and file reads happen outside them (see [processor](../packages/worker-processor.md) and [re-enrich](../api/sessions-enrich.md)). GET and HEAD requests use `read_sessionmaker` (`deferred=True`), so WAL lets them read while a writer works. The code comments about "locking" rows (`_get_batch_locked`, "lock order") describe ordering of statements; SQLite has no row locks, and the immediate transaction is what serialises writers ([claims](claim-fencing-and-lock-order.md)).
