---
type: Module
title: Failure classification and backoff
description: classify decides whether an item failure is retryable; backoff_seconds spaces retries with exponential delay and jitter.
resource: src/lens/worker/retry.py
tags: [worker, retry]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/worker/retry.py]
---
`classify(exc)` returns `Failure(message, retryable)`:

| Exception | Retryable | Stored message |
|---|---|---|
| `UnsupportedVersion`, `EmptyRecording` | no | type and text |
| `EnrichmentError` | its `retryable` flag | type and text |
| `RecordingExpired` | no | `raw recording expired` |
| `TimeoutError` | yes | `TimeoutError: processing timed out` |
| anything else | yes | the type name only |

Only exception types with controlled messages keep their text; others (such as validation errors) can echo recording content, so only the type name is stored. Messages are cut to 500 characters.

`backoff_seconds(attempt)`: delay = `min(300, 5 * 2^(attempt-1))` seconds, then half of it fixed plus a uniform random value up to the other half ("equal jitter"). Retries stop at [MAX_ATTEMPTS](/config/max-attempts.md).
