# Yantra Test

## Brief

This is the example brief for the technical deep dive.

This is, above all, a set of guidelines/suggestions. It was given to us for a more junior
candidate, so don't limit yourself; they're just a starting point.
As you said, you choosing/building something more personal is absolutely encouraged.

You don't need to worry about adhering to it super strictly.
It is literally anything you can talk about in depth for an hour, to showcase how you work.
If you have a project that is different, but that you are confident you can discuss for
an hour and that is interesting to look at as a developer, then feel free to send that in.

Build a small Python service (FastAPI) that accepts a batch of URLs,
fetches each page, extracts the text content, and enriches it via an
LLM (e.g. summary, category, sentiment). Store the results and let a client submit work
and retrieve results. Use a database with an ORM of your choice.
Since batches can be large and the network is unreliable, we're interested in how you
handle fetching and processing many items. Put the LLM call behind an interface and ship
a mock implementation so the whole thing runs without any API keys; wiring up a real
provider is optional.
(i'm quite flexible though so he can add bits if he wants or use e.g.
the OpenAI SDK directly and skip the mock implementation bit if he's happy consuming
tokens etc, don't want to mandate that he spends money on an OpenAI etc. subscription)

The most important thing is: it is in python, and showcases your skills as a
full-stack developer that has shipped software to production; and that you are able to
really talk about the code in a lot of detail at length. Send whatever you
are comfortable with! If you send it as a github repo, that's usually the easiest
way for them to look at it.

## My idea

**Agent session analyzer.** A FastAPI service that ingests batches of recorded coding-agent
sessions, enriches each one, stores the results, and lets a client submit work and retrieve
results by project, category or outcome.

It is the brief's shape (batch in, fetch, enrich with an LLM behind an interface, store,
query) with a different kind of item. Instead of web pages, the items are session recordings
written by [Flockdeck](https://github.com/Flockdeck/flockdeck), a desktop app I built that runs
several coding agents side by side. I wrote the producer, so I can talk about both ends of the
data.

### Input

Flockdeck's per-pane recording writes one JSON Lines file per session
(`<project>-<hash>/<start>-<pane>.jsonl`). Every line has an envelope (`v`, `seq`, `time`,
`session`, `pane`, `agent`, `model`, `type`) and one of these types: `session`, `user_prompt`,
`assistant_message`, `tool_call`, `tool_result`, `permission_prompt`, `permission_outcome`,
`status`, plus `recording_started`, `recording_stopped` and `recording_truncated`.
The format is versioned and documented in Flockdeck's `docs/recording-format.md`.

Properties the service has to cope with:

- **Unreliable data.** Delivery is at most once, so a `tool_call` can lack its `tool_result`.
  A crashed session ends with a half-written line or no stop line. A session can hit the
  16 MiB cap and end in `recording_truncated`.
- **Forward compatibility.** Unknown fields are ignored and unknown types are skipped. A file
  with a `v` other than 1 is refused.
- **Redacted and clipped content.** Secrets appear as `[redacted]` and long strings end in a
  `…[clipped N bytes]` marker. The original is never recoverable and the service does not try.
- **Uneven coverage.** Only Claude Code records fully. Other agents record only start and stop.

### What the service produces

Each session gets two kinds of fields.

**Computed in code** (deterministic, testable, no LLM):

- duration, number of turns, tool usage mix
- tool error and interruption rate
- permission prompts, and the denied / allowed / auto-approved split
- time spent in each pane status (working, waiting, blocked, idle)
- completeness flags: ended cleanly, truncated, or cut off

**Enriched by an LLM** (behind an interface):

- summary
- task category (bugfix, refactor, exploration, docs, ...)
- outcome (done, abandoned, stuck)
- frustration / sentiment score

The enrichment prompt is built from the computed facts plus the user prompts and final
assistant messages, not the raw transcript. That keeps token use bounded and means a
16 MiB session costs about the same as a small one.

### API (sketch)

- `POST /batches` takes a `multipart/form-data` request with one `files` part per recording
  (`.jsonl`), so a batch is any number of files in one request. It validates each file's size
  and extension, stores the accepted ones, queues an item for each, and returns `202` with the
  batch id straight away. Processing happens afterwards in the worker. The response lists any
  files it rejected, each with a reason (too large, wrong type, empty), and the rest of the
  batch goes ahead. A request with no acceptable files is a `422`.
- `GET /batches/{id}` gives per-item status (queued, running, done, failed) and counts.
  Partial results are available while the batch is still running.
- `GET /sessions` lists enriched sessions, filterable by project, agent, category, outcome
  and date.
- `GET /sessions/{id}` gives the full record: computed metrics, enrichment and parse warnings.

### Web interface

A browser UI that is a plain client of the JSON API above. It has no private endpoints and no
server-side rendering of data, so anything the UI can do, a script can do.

- **Submit.** Choose recordings with a multi-select file picker (`<input type="file"
  multiple accept=".jsonl">`) or drag and drop several files onto the page. The chosen files
  are listed with their sizes, files over the size limit are flagged before anything is sent,
  and a single click submits them all as one batch via `POST /batches`. The browser then moves
  to the batch page, which polls `GET /batches/{id}` and shows per-item status, retries and
  failures with their reasons, including any files the server rejected.
- **Browse.** A session list with filters for project, agent, category, outcome and date,
  with sorting and pagination.
- **Inspect.** A session page showing the computed metrics, the enrichment, a timeline of
  status and tool activity, and any parse warnings (truncated, cut-off, redacted or clipped).
- **Overview.** A small dashboard: outcomes by category, error and denial rates per agent and
  model, and sessions over time.

Implementation: static files (HTML, CSS and ES modules, no build step) served by FastAPI from
`/`, calling the API with `fetch`. The API is the contract, so the front end can be swapped
for a framework later without touching the backend. CORS stays closed, since the UI is served
from the same origin.

### Architecture

- **Sources.** A `TranscriptSource` interface so the parser does not care where bytes come
  from. The first implementation is the uploaded file, which is the only way in once the
  service runs in the cluster, because it cannot see files on the user's machine. A local
  folder source and a URL source can be added later behind the same interface.
- **Upload limits.** A recording is at most 16 MiB (Flockdeck's own cap), so the API accepts at
  most a little over that per file and rejects larger files individually. The request as a
  whole is also bounded (file count and total size), and the HAProxy ingress body limit is
  set to match. The API validates each file and writes it to the object store.
- **Raw storage.** The uploaded file goes to an S3-compatible bucket (DigitalOcean Spaces in
  the cluster, MinIO locally and in CI) through a small `RecordingStore` interface. MySQL keeps
  one `raw_recordings` row per file (hash, size, object key, created and expired times), and
  the worker and the events view fetch the file whole when they need it, since it is at most
  16 MiB. The object is written before the row, so a row never points at a missing file.
- **Retention and cleanup.** Raw recordings are sensitive, so they are kept for 30 days. A
  lifecycle rule on the bucket expires the objects, so the app never has to list or sweep the
  bucket. A daily `session-lens cleanup` CronJob only reconciles the database: it marks rows
  past retention as expired (the UI then disables the raw event view and re-enrich, and the API
  answers `410`) and prunes finished batch records older than 90 days. Sessions, metrics and
  enrichments are kept. Deleting a session also deletes its raw rows and objects. An orphan
  object (upload succeeded, database write failed) is removed by the lifecycle rule too.
- **Parser.** A tolerant reader for format v1: skips bad last lines and unknown types, rejects
  other versions, pairs calls with results on `toolUseId`, and reports warnings rather than
  failing.
- **Enricher.** An `Enricher` protocol with a deterministic mock (heuristics over the computed
  metrics) that needs no API key, and an optional real provider. Output is validated against a
  Pydantic model, with a bounded retry if the provider returns malformed JSON.
- **Worker.** Batches are processed concurrently with a bounded semaphore. Retries use
  exponential backoff with jitter and distinguish retryable failures (timeouts, rate limits)
  from permanent ones (unsupported version, empty file). Items are independent, so one bad
  session never fails a batch.
- **Idempotency.** A session is keyed on its session id plus a content hash. Resubmitting the
  same batch is free, and a session that grew since last time is re-processed.
- **Storage.** SQLAlchemy 2.0 with Alembic migrations, on MySQL 8 everywhere: locally, in CI
  and in the cluster (the shared managed MySQL that terrawost provisions). There is no SQLite
  path, so dev, CI and production share one dialect, one driver and one set of migrations.
  A `docker-compose.yml` starts a local MySQL and a MinIO (S3-compatible) with the same
  30-day lifecycle rule on its bucket, and `DATABASE_URL` and `S3_*` point the app at them.
  Tables: batches, batch items, sessions, metrics, enrichments.
- **Privacy.** Recordings are sensitive. The service logs ids and counts, never content.

### CI/CD and deployment

Same pattern as my other apps on the cluster (`vael`, `flockdeck-relay`): GitHub Actions builds
the image, Flux rolls it out from `k8s-infra`, and terrawost owns the infrastructure the app
depends on.

**GitHub Actions** (`.github/workflows/ci.yaml`):

- On every push and pull request: lint and type-check (ruff, mypy), then the test suite against
  a MySQL 8 service container and a MinIO container (started with `docker run`, since service
  containers cannot pass `server /data`), the same major version and driver as the cluster and the local
  compose file.
- On a `v*` tag, after tests pass: build the Docker image and push
  `ghcr.io/jmwri/<app>:<version>`. Tags are plain semver with no `v`, because Flux's
  `ImagePolicy` selects the highest semver tag.
- Releasing is `git tag v0.1.0 && git push --tags`. No separate deploy step and no cluster
  credentials in GitHub: the cluster pulls, CI never pushes to it.

**Flux** (`k8s-infra/<app>/`, manifests drafted in `deploy/k8s-infra/` here and copied across):

- `Deployment` and `Service`, with readiness and liveness probes on a `/healthz` endpoint.
- `ImageRepository` and `ImagePolicy` (semver), so a new tag is rolled out automatically.
- `Ingress` through HAProxy with `ssl-redirect` and cert-manager's `letsencrypt-prod`, which
  serves both the UI and the API from one host.
- `NetworkPolicy` allowing ingress only from `haproxy-ingress` and egress only to DNS, MySQL
  and the Spaces endpoint (HTTPS). The mock enricher needs no other egress. A real LLM provider
  would need a rule for it.
- Database migrations run as an init container (`alembic upgrade head`) before the app starts.
- One replica to begin with. Workers pull batch items from the database, so scaling out later
  means claiming rows with `SELECT ... FOR UPDATE SKIP LOCKED` (MySQL 8 supports it).

**terrawost** provisions what Flux assumes already exists:

1. the namespace,
2. a database and user on the shared managed MySQL cluster, with DDL rights for migrations,
3. a secret holding `DATABASE_URL` (and the CA for the TLS connection to MySQL),
4. a DNS record for the app's hostname,
5. a DigitalOcean Spaces bucket with a lifecycle rule that expires objects under `recordings/`
   after 30 days (it must match `RAW_RETENTION_DAYS`), and an access key scoped to that bucket
   in the same secret (`S3_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET`, `S3_ACCESS_KEY`,
   `S3_SECRET_KEY`),
6. the `ghcr.io` package set to public, or an `ImageRepository` `secretRef` and
   `imagePullSecrets` if it stays private.

Talking points: why pull-based GitOps instead of `kubectl apply` from CI, how a bad release is
rolled back (retag or revert in `k8s-infra`), and why migrations run as an init container
rather than inside the app on startup.

### Testing

- Fixtures generated from the documented examples and Flockdeck's JSON Schema, plus a real
  recording once the feature ships.
- Parser tests for each tolerance rule: truncated file, cut-off last line, unknown type and
  field, wrong version, missing `tool_result`.
- Worker tests with injected failures (flaky enricher, timeouts) to check retries, idempotency
  and partial results.
- An end-to-end test through the API using the mock enricher.
- The suite runs against MySQL both locally (docker compose) and in CI. Each test run uses its
  own throwaway database, and the schema is created by running the Alembic migrations, so the
  migrations are tested on every run.
- A browser test of the main flow (submit a batch, watch it finish, open a session) against
  the running service.

### Out of scope

Replaying sessions, live streaming of events, authentication and multiple users, and
recovering redacted text.

