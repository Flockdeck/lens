---
type: Gotcha
title: Enricher construction runs in a thread
description: Building an HTTP client loads TLS certificates, which can take seconds and would freeze the UI on the event loop.
resource: src/lens/runtime_settings.py
tags: [enrichment, performance]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/runtime_settings.py, src/lens/db/migrate.py]
---
`DynamicEnricher` calls `build_enricher` through `asyncio.to_thread`; the comment notes this is slow on some machines and longer in a freshly unpacked binary. Similarly `upgrade_async` runs Alembic in a thread because Alembic's env starts its own event loop, and parse and analyze run in threads because they are CPU-bound on files up to 16 MiB.
