---
type: Gotcha
title: Timestamps are naive UTC
description: Database datetimes are stored without a timezone but always mean UTC.
resource: src/lens/db/models.py
tags: [database, time]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/db/models.py, src/lens/worker/processor.py, src/lens/api/dates.py]
---
`utcnow()` returns `datetime.now(UTC)` with the tzinfo removed. The processor strips tzinfo from recording times (`_naive`) before storing, so `started_at` and `ended_at` are UTC. Query parameters with an offset are converted to UTC and made naive ([dates](/packages/api-dates.md)). A new column must follow the same convention or range filters will be off.
