# Configuration and environment variables

* [ALLOWED_HOSTS](allowed-hosts.md) - Host names this machine answers to; any other Host header is refused with 421.
* [ANTHROPIC_API_KEY](anthropic-api-key.md) - API key for the Anthropic enricher; held as a secret string and never logged or returned.
* [ANTHROPIC_MODEL](anthropic-model.md) - Model name the Anthropic enricher requests.
* [ANTHROPIC_WORKSPACE_ID](anthropic-workspace-id.md) - Workspace id sent as a header, only for a key that is not scoped to one workspace.
* [CLAIM_TIMEOUT_SECONDS](claim-timeout-seconds.md) - Age at which a running item's claim is treated as abandoned.
* [CLEANUP_INTERVAL_SECONDS](cleanup-interval-seconds.md) - How often the worker runs retention cleanup; 0 turns the timer off.
* [DATA_DIR](data-dir.md) - Directory holding the database, the raw recordings and the log file.
* [DATABASE_URL](database-url.md) - SQLAlchemy URL of the database; only SQLite is accepted.
* [DO_SPACES_BUCKET](do-spaces-bucket.md) - Name of the bucket the downloads are written to.
* [DO_SPACES_ENDPOINT](do-spaces-endpoint.md) - S3 endpoint the aws CLI talks to.
* [DO_SPACES_KEY](do-spaces-key.md) - Access key id of an account that can write the download bucket.
* [DO_SPACES_REGION](do-spaces-region.md) - Region of the bucket, also used to build the default endpoint.
* [DO_SPACES_SECRET](do-spaces-secret.md) - Secret for the access key; exported to the aws CLI as its secret key.
* [.env file](dotenv-file.md) - Settings also read an optional .env file from the working directory; real environment variables win.
* [ENRICHER](enricher.md) - Which enricher analyses sessions, one of mock, ollama or anthropic.
* [HOST](host.md) - Address `lens serve` binds to.
* [LENS_ALLOW_LISTABLE](lens-allow-listable.md) - Set to `1` only to try the script against a local store that lists its bucket; skips the check that the public bucket is not listable.
* [LENS_CHECK_WAIT](lens-check-wait.md) - Seconds between tries when reading an uploaded file back through the public address (six tries).
* [LENS_DL_URL](lens-dl-url.md) - Public base URL where the bucket is served; used to read an upload back and to check the bucket cannot be listed.
* [LENS_SIGNING_KEY](lens-signing-key.md) - Release signing key, read by release.py sign from the environment (a repository secret in the release environment).
* [LOG_FILE](log-file.md) - Where logs go, with `-` for standard output, a path for a file, or blank for an automatic choice.
* [LOG_LEVEL](log-level.md) - Root log level; case-insensitive.
* [MAX_ATTEMPTS](max-attempts.md) - Attempts an item gets before it is marked failed.
* [MAX_FILE_BYTES](max-file-bytes.md) - Largest accepted recording file, in bytes.
* [MAX_FILES_PER_BATCH](max-files-per-batch.md) - Maximum number of files in one upload.
* [MAX_REQUEST_BYTES](max-request-bytes.md) - Largest total upload body, in bytes.
* [OLLAMA_MODEL](ollama-model.md) - Model name requested from Ollama.
* [OLLAMA_TIMEOUT_SECONDS](ollama-timeout-seconds.md) - HTTP timeout for calls to Ollama, in seconds.
* [OLLAMA_URL](ollama-url.md) - Base URL of the local Ollama server; must point at this machine.
* [PORT](port.md) - Port `lens serve` listens on.
* [RAW_RETENTION_DAYS](raw-retention-days.md) - Days to keep raw recording files; 0 keeps them forever.
* [SHUTDOWN_GRACE_SECONDS](shutdown-grace-seconds.md) - How long the worker waits for in-flight items on shutdown before cancelling and re-queueing them.
* [STORE_PREFIX](store-prefix.md) - Subdirectory of the data directory for raw recordings.
* [UI setting overrides](ui-overrides.md) - Six enrichment settings can be changed in the web UI and stored in the database, overriding the environment.
* [WORKER_CONCURRENCY](worker-concurrency.md) - Number of batch items processed at once.
* [WORKER_POLL_SECONDS](worker-poll-seconds.md) - How long the worker waits for work before polling the queue again.
