# Packages

* [FastAPI app factory](api-app.md) - create_app builds the FastAPI application, its middleware, metrics and optional in-process worker.
* [Date range query parameters](api-dates.md) - range_conditions turns from and to query strings into SQL conditions, treating bare dates as whole UTC days.
* [API dependencies](api-deps.md) - FastAPI dependencies for settings, per-request database sessions, and lazily built store, queue and enricher providers.
* [Request body size limit](api-limits.md) - BodySizeLimit is an ASGI middleware that rejects POST /batches bodies over MAX_REQUEST_BYTES with 413.
* [LocalOnly middleware](api-local.md) - ASGI middleware that checks the Host header on every request and the Origin of every write.
* [JSON logging](api-logging.md) - JsonFormatter and setup_logging write one JSON object per log record with ids, counts and timings only.
* [API response models](api-schemas.md) - Pydantic models for the HTTP API responses.
* [Upload file validation](api-uploads.md) - check_file validates one multipart part by name, extension, size and emptiness.
* [Settings class](config-settings.md) - pydantic-settings class that reads every runtime option from the environment and an optional .env file.
* [Alembic migration runner](db-migrate.md) - upgrade_async runs alembic upgrade head on every start of serve and cleanup.
* [Database engine and sessions](db-session.md) - make_engine builds the SQLite async engine with WAL, foreign keys and BEGIN IMMEDIATE write transactions.
* [Anthropic enricher](enrich-anthropic.md) - Calls the Anthropic Messages API with a JSON-schema output format and validates the reply.
* [Mock enricher](enrich-mock.md) - Deterministic heuristic enricher over the computed metrics; the default; needs no key and sends nothing.
* [Ollama enricher](enrich-ollama.md) - Calls a local Ollama server over /api/chat with a JSON schema format; never talks to a non-local host.
* [Enrichment prompt and output schema](enrich-prompt.md) - Versioned system prompt, the LLMEnrichment answer schema and the bounded user message built from an Analysis.
* [Enricher protocol and factory](enrich.md) - Enricher.enrich turns an Analysis into an EnrichmentResult; build_enricher picks mock, ollama or anthropic.
* [lens entry point and CLI parser](entrypoint.md) - python -m lens and the packaged binary both call lens.cli.main, which defaults to the serve command.
* [Parent process watch](parent-watch.md) - Stops the server when the launcher process that started it is killed outright.
* [Session digest](recording-digest.md) - build_digest compacts a session into a size-bounded set of prompts, final messages, failures and risks for the LLM.
* [Files touched extraction](recording-files.md) - extract_files_touched lists distinct files read and edited and the Bash commands run.
* [Recording format detection](recording-format.md) - detect_format tells transcript files from live-hook files and is_agent_prompt filters agent-generated prompts.
* [Recording metrics](recording-metrics.md) - compute_metrics and completeness derive deterministic counts, permission stats and timings from events.
* [Recording models](recording-models.md) - Pydantic models for a parsed event line and for the Analysis, Metrics and Digest computed from a recording.
* [Recording parser](recording-parser.md) - Tolerant reader for Flockdeck recording format v1 that turns bytes into events and computes an Analysis.
* [Risky action rules](recording-risk.md) - Rule-based heuristics that flag risky tool calls such as force pushes, rm -rf, destructive SQL and secret files.
* [Runtime settings overrides](runtime-settings.md) - Settings changed in the UI are stored in app_settings and override the environment for both API and worker.
* [Filesystem recording store](storage-filesystem.md) - FilesystemStore keeps raw recordings as files under the data directory with atomic writes and path-escape checks.
* [Recording store protocol](storage.md) - RecordingStore is the async interface for raw recording bytes; build_store returns the filesystem implementation.
* [Web UI API client](web-api-client.md) - js/api.js is the only UI module that calls fetch; it wraps the HTTP API and normalises errors.
* [Web UI helpers](web-lib.md) - Pure helper functions and the glossary used by the UI, testable under node.
* [Web UI](web-ui.md) - Static single-page UI served from the package; hash routes for submit, batches, sessions, insights and settings.
* [Web UI views](web-views.md) - One module per page of the UI, each rendering into the main region.
* [Retention cleanup](worker-cleanup.md) - run_cleanup deletes raw recording files past retention and removes old finished batches.
* [Worker claim loop](worker-loop.md) - run_worker claims due items, runs them with bounded concurrency, sweeps stale claims and drains on shutdown.
* [Item processor](worker-processor.md) - ItemProcessor turns one claimed batch item into a session and an enrichment in two phases.
* [Batch queue helpers](worker-queue.md) - Shared functions to store raw files, create, retry and cancel batches, and roll item statuses up into the batch status.
* [Failure classification and backoff](worker-retry.md) - classify decides whether an item failure is retryable; backoff_seconds spaces retries with exponential delay and jitter.
