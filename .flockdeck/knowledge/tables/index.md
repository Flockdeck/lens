# Data types, tables and file formats

* [Metrics JSON](analysis-metrics.md) - The deterministic metrics stored on each session and sent to the enricher.
* [Recording completeness values](completeness.md) - How a recording ended, derived from its last known event.
* [EnrichmentResult](enrichment-result.md) - The common result of every enricher, stored as an enrichments row.
* [Alembic migration 0001](migration-0001.md) - The single initial schema revision creating all six tables and their indexes.
* [Raw recording object key](object-key.md) - Format of the key under which a raw recording is stored in the data directory.
* [Flockdeck recording line, format v1](recording-line.md) - One JSON line of a Flockdeck pane recording as lens reads it, with the required envelope and optional fields.
* [checksums.txt](release-checksums.md) - Release file listing the SHA-256 and name of every archive, sorted, with a detached signature.
* [latest.json](release-latest-json.md) - Unsigned pointer naming the latest released version.
* [manifest.json](release-manifest.md) - Signed release manifest with version, date, notes and every file's URL, SHA-256 and size.
* [RiskyAction](risky-action.md) - A rule hit on one tool call, with seq, tool, summary, severity and rule name.
* [Table app_settings](table-app-settings.md) - Key and value rows for settings changed in the UI, including the Anthropic API key in plain text.
* [Table batch_items](table-batch-items.md) - One row per uploaded file; the unit of work claimed by the worker.
* [Table batches](table-batches.md) - One row per upload batch with a rolled-up status.
* [Table enrichments](table-enrichments.md) - The LLM or mock analysis of a session; at most one per session.
* [Table raw_recordings](table-raw-recordings.md) - One row per stored upload; the bytes are a file in the data directory.
* [Table sessions](table-sessions.md) - One row per recording session with identity, timing, completeness and computed JSON.
