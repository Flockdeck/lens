---
type: Module
title: Date range query parameters
description: range_conditions turns from and to query strings into SQL conditions, treating bare dates as whole UTC days.
resource: src/lens/api/dates.py
tags: [api, dates]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/api/dates.py]
---
Used by [GET /sessions](../api/sessions-list.md) and [GET /stats/trends](../api/stats-trends.md).

- A 10-character value is parsed as an ISO date at 00:00 UTC and marked date-only.
- Anything else goes through `datetime.fromisoformat`; a value with an offset is converted to UTC and stored naive. A value with no offset is taken as UTC.
- `from` becomes `column >= start`. `to` becomes `column < end + 1 day` when date-only, else `column <= end`.
- A value that does not parse raises HTTP 422 "invalid `from`: expected ISO date or datetime".

Because all timestamps are naive UTC (see [timestamps](../gotchas/naive-utc-timestamps.md)), the comparison is done on naive values.
