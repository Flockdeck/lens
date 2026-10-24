# HTTP, socket and WebSocket interface

* [POST /batches/{batch_id}/cancel](batches-cancel.md) - Cancels the queued items of a batch and marks the batch cancelled.
* [GET /batches/{batch_id}](batches-get.md) - Returns a batch with per-status item counts and its items.
* [POST /batches/{batch_id}/retry](batches-retry.md) - Re-queues the failed items of a batch.
* [POST /batches](batches-submit.md) - Uploads one or more .jsonl recordings as a multipart batch and queues them for analysis.
* [GET /config](config-get.md) - Non-secret runtime facts for the UI, covering enricher, retention, cleanup interval and version.
* [GET /healthz](healthz.md) - Unauthenticated liveness probe.
* [GET /metrics](metrics.md) - Prometheus text metrics with process and platform collectors, request counters and queue depth by item status.
* [GET /readyz](readyz.md) - Readiness probe that checks the database and the file store.
* [DELETE /sessions/{session_id}](sessions-delete.md) - Deletes a session, its enrichment and its raw recordings.
* [POST /sessions/{session_id}/enrich](sessions-enrich.md) - Re-runs enrichment for a session and overwrites the stored result.
* [GET /sessions/{session_id}/events](sessions-events.md) - Returns a page of parsed events from the stored raw recording.
* [GET /sessions/{session_id}](sessions-get.md) - Returns one session with metrics, risky actions, files touched, warnings and its enrichment.
* [GET /sessions](sessions-list.md) - Lists sessions with filters, a started_at date range, sorting and offset paging.
* [GET /settings](settings-get.md) - Returns the effective enrichment settings; the Anthropic key is reported only as set or not set.
* [PUT /settings](settings-put.md) - Changes or removes UI overrides for the enricher, Anthropic key and model, and Ollama URL and model.
* [GET /stats/compare](stats-compare.md) - Compares sessions grouped by agent or model.
* [GET /stats/trends](stats-trends.md) - Aggregates sessions per day or ISO week with outcome counts, average frustration and tool error rate.
* [GET /stats/usage](stats-usage.md) - Returns total enrichment tokens and the number of enrichments.
* [Static web UI at /](web-ui-files.md) - All other paths serve the bundled web UI files with revalidation and no Python sources.
