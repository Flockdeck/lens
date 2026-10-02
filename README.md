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

## My idea: session-lens

**session-lens** analyses recordings of coding-agent sessions. It ingests batches of
[Flockdeck](https://github.com/Flockdeck/flockdeck) pane recordings, computes metrics from each
one, enriches it (summary, category, outcome, where the agent got stuck), stores the results in
MySQL and lets a client submit work and retrieve results through a FastAPI service and a small
web UI that uses only that API.

It is the brief's shape (a batch of items, fetched and processed with failures expected, an
LLM behind an interface with a mock, a database with an ORM, submit and retrieve) with a
different kind of item: instead of web pages, session recordings written by Flockdeck, a
desktop app I built that runs several coding agents side by side. I wrote the producer, so I
can talk about both ends of the data.

### Local-first by design

A recording contains prompts, file contents and command output. Flockdeck's own policy is that
this stays on the machine, and session-lens keeps to it:

- **By default nothing is uploaded.** The default enricher is a deterministic mock, and the optional
  local one talks to an [Ollama](https://ollama.com) server and refuses any URL that is not loopback
  (or `host.docker.internal` from a container); its HTTP client ignores proxy variables and does not
  follow redirects. With either, the service makes no outbound network calls.
- **Anthropic is an explicit opt-in.** Choose it in the UI's Settings page, or set `ENRICHER=anthropic`
  and `ANTHROPIC_API_KEY` in the git-ignored `.env` (the model is `ANTHROPIC_MODEL`, default
  `claude-haiku-4-5`). A key entered in Settings is stored in the local database (plain text, on this
  machine, like the `.env` it stands in for), is write-only (the API says only whether one is set and
  where it came from), and overrides the environment; the worker picks changes up within seconds, with
  no restart. Once chosen, each session's
  bounded digest (your prompts, the agent's final messages, trimmed failing output and the metrics,
  never the raw recording) is sent to `api.anthropic.com`. It is announced in the log at startup, the
  UI's status bar changes to "Sends digests to Anthropic", and the key is never logged or returned by
  the API. Without the key the service refuses to start with that enricher.
- **Loopback, and no key.** The API binds `127.0.0.1` and warns if asked to bind anywhere else, and
  compose publishes ports on `127.0.0.1` only. There is no API key to manage because nothing outside
  this machine can reach it. What a key would also have stopped is a web page you have open talking to
  `127.0.0.1` for you (a form post, or DNS rebinding), so every request is checked: the `Host` must be
  one of this machine's names (`ALLOWED_HOSTS`, default `127.0.0.1`, `localhost`, `::1`), and a write
  that carries a foreign `Origin` (or `null`, or `Sec-Fetch-Site: cross-site`) is refused. There are no
  CORS headers, so a page on another origin cannot read a response either. `curl` and scripts, which
  send neither header, work as they are.
- **No residue.** Responses carry `Cache-Control: no-store`; logs hold ids and counts, never
  content, filenames or query strings; the UI makes no external requests (a test enforces it) and
  sends no referrer.
- **Visible.** The UI footer says "Local only · storage: filesystem · enrichment: mock · raw kept
  30 days", built from `GET /config`, and says "Not verified as local-only" instead when a
  setting says otherwise.
- **Short-lived raw data.** Raw recordings are deleted after `RAW_RETENTION_DAYS` (30, or 0 to
  keep them until deleted), by the app itself. Metrics and enrichments, which are derived, stay.

### Run it

```sh
make up                        # mysql, migrations, api on http://127.0.0.1:8000, worker
make smoke                     # uploads a fixture, waits for it, prints the session count
```

Open http://127.0.0.1:8000. There is nothing to sign in to. To enrich with a local model:
`ollama pull llama3.1:8b`, then set `ENRICHER=ollama` (compose has the commented lines for
reaching Ollama on the host). Without Docker: `docker compose up -d --wait mysql`, then
`make migrate api` and `make worker` in two terminals. `make check` runs lint, types and tests.

### Input

Flockdeck's per-pane recording writes one JSON Lines file per session. Every line has an
envelope (`v`, `seq`, `time`, `session`, `pane`, `agent`, `model`, `type`) and one of
`session`, `user_prompt`, `assistant_message`, `tool_call`, `tool_result`, `permission_prompt`,
`permission_outcome`, `status`, `recording_started`, `recording_stopped`, `recording_truncated`.
The format is versioned and documented in Flockdeck's `docs/recording-format.md`.

What the service has to cope with:

- **Unreliable data.** Delivery is at most once, so a `tool_call` can lack its `tool_result`; a
  crashed session ends with a half-written line or no stop line; a file can hit the 16 MiB cap.
- **Forward compatibility.** Unknown fields are ignored and unknown types skipped. Another `v`
  is refused. A line that is hostile (deeply nested JSON, huge integers) is counted as malformed
  instead of aborting the file.
- **Redacted and clipped content.** Secrets appear as `[redacted]`, long strings end in a
  `…[clipped N bytes]` marker. The original is not recoverable and the service does not try.
- **Uneven coverage.** Only Claude Code records fully. Other agents record only start and stop.

### What the service produces

**Computed in code** (deterministic and testable, no LLM): duration, turns, tool mix, error and
interruption rates, permission outcomes, time per pane status, completeness (clean, truncated,
cut off), files read, edited and commands run, and **risky actions** found by rules (force pushes,
`rm -rf` on broad targets, secret-file reads, and so on) with a severity.

**Enriched** (behind the `Enricher` interface): summary, task category, outcome (done,
abandoned, stuck), frustration score, stuck points, feedback on the prompts, and notes on the
risky actions. The prompt is built from the computed facts plus the user's prompts, the final
assistant messages and trimmed failing results, never from the raw transcript. Input is
size-bounded, JSON-encoded so transcript text cannot close a prompt tag, and the model's output
may only refer to event numbers it was given.

### API

All JSON, no credentials. A request addressed to a host name that is not one of this machine's is
refused with `421`, and a write from another origin with `403` (see "Loopback, and no key").

- `POST /batches`: multipart, one `files` part per `.jsonl` recording. Returns `202` with the
  batch id and per-file rejections (too large, wrong type, empty); `422` if nothing is usable.
- `GET /batches/{id}`, `POST /batches/{id}/retry`, `POST /batches/{id}/cancel`.
- `GET /sessions` (filters, pagination), `GET /sessions/{id}`, `DELETE /sessions/{id}`.
- `GET /sessions/{id}/events?after_seq=&limit=`: the parsed events, paged. `POST
  /sessions/{id}/enrich` re-enriches. Both answer `410` once the raw recording is gone.
- `GET /stats/trends`, `GET /stats/compare?by=agent|model`, `GET /stats/usage`.
- `GET /config` (what the UI shows in its footer), `GET /healthz`, `GET /readyz`, `GET /metrics`.

### Web interface

Static HTML, CSS and ES modules (no build step) served by FastAPI, calling the API with
`fetch`: submit with a multi-select file picker or drag and drop, batch progress by polling,
a filterable session list, a session page (metrics, enrichment, risky actions, files, a paged
event view), trends over time, and agent and model comparisons. It has no private endpoints, so
anything the UI can do a script can do.

The look is Flockdeck's, as flockdeck.ai and the Flockdeck phone client wear it: dark only, Archivo and
JetBrains Mono served from the app itself (no font service is ever asked), their tokens and accent wash,
44px tap targets, and their rule that green, amber and red mean only what they mean in a pane header. Every
status is a glyph and a word as well as a colour, and running is the accent, never green. The tokens, fonts
and mark are copied from `flockdeck-remote` (`web/app`); `tests/web/test_design.py` keeps the UI to those
rules and, with `FLOCKDECK_REMOTE_DIR` set, checks the copies against the source.

### Architecture

- **Parser** (`recording/`): a tolerant reader for format v1, then `analyze` for the metrics,
  risk rules and the LLM digest. Pure functions over bytes, so they are easy to test.
- **Storage** (`storage/`): a small `RecordingStore` interface. The default is a local
  filesystem store (atomic writes, private permissions, keys that cannot escape the data
  directory); an S3-compatible store is an optional implementation. The object is written
  before its database row, so a row never points at a missing file.
- **Worker** (`worker/`): claims batch items with `SELECT ... FOR UPDATE SKIP LOCKED`, runs a
  bounded number at once, retries with exponential backoff and jitter, and tells retryable
  failures (timeouts, a model still loading) from permanent ones (unsupported version, empty
  file, expired raw). A claim token fences a worker that lost its claim; parsing runs off the
  event loop; no database connection is held while the model runs; shutdown drains for a
  bounded time and refunds the attempt of anything it had to cancel. One bad session never
  fails a batch.
- **Idempotency.** A session is keyed on its recording session id. Resubmitting identical
  content is free; a longer version of the same recording replaces the session and is
  re-enriched, so the list never shows duplicates.
- **Retention.** The worker runs cleanup in the background (and `session-lens cleanup` runs it
  by hand): raw files past `RAW_RETENTION_DAYS` are deleted and their rows marked expired (the
  UI then disables the event view and re-enrich), and finished batch records older than 90 days
  are pruned. A MySQL advisory lock keeps two cleanups from colliding. Deleting a session
  removes its raw files too.
- **Database.** SQLAlchemy 2.0 (async, `asyncmy`) and Alembic on MySQL 8 everywhere: dev, CI
  and compose share one dialect and one set of migrations. There is no SQLite path.
- **Enricher** (`enrich/`): the interface, a deterministic mock (the default, no setup), and the
  local Ollama implementation with schema-constrained output, a bounded retry on malformed JSON
  and an explicit truncation limit.

### Testing and CI

- Real MySQL for every test that touches the database, built from the Alembic migrations (so
  the migrations run on every test run), one throwaway database per run.
- Parser tests for each tolerance rule, risk-rule false positives and negatives, and a
  performance check on a pathological 90,000-line file.
- Worker tests for claims, fencing, retries and backoff, the claim-versus-cancel lock order,
  retention and the storage implementations.
- API tests against the real worker and storage modules, including the privacy headers and log
  contents; enrich tests with a scripted fake Ollama server, including that non-local URLs are
  refused; web tests that fail on any external URL in the UI.
- **End to end** (`tests/e2e`, `make e2e`): the real app, worker, MySQL, filesystem store and parser, with
  nothing faked between an upload and a result. They submit a mixed batch and read every view of it
  (sessions, metrics, risky actions, paged events, stats, config, privacy headers), resubmit the same and a
  longer recording, age a recording past retention and check the file is really gone and the endpoints
  answer `410`, delete, cancel and retry, per-file upload checks, and that every endpoint refuses a
  foreign `Host` and every write refuses a foreign `Origin`. `make e2e-browser` repeats the flow in a
  real browser (Edge, else Chromium): opening the app with nothing to sign in to, a multi-file upload
  with the empty file flagged, the batch page, filtering, the session page, raw events, re-enrich,
  delete, insights, phone width without sideways scrolling, keyboard focus, no external request and no
  console error. It also tries the two attacks a key would have stopped, from a real browser: another
  page's form post, which is refused, and a host name rebound to this machine, which gets `421`. I checked they can fail by breaking file deletion and the
  done glyph on purpose.
- GitHub Actions runs ruff, `mypy --strict` and pytest (end-to-end tests and a Chromium browser
  included) against a MySQL service container, and builds the image on pull requests without
  pushing it. There is no deployment: this stays on your machine.

### Decisions I would talk about

- Computing what can be computed, and only asking a model for judgement, so the mock is useful
  and the model's job is small and checkable.
- Treating the recording as untrusted input twice: once when parsing (hostile lines), once when
  prompting (tag break-out, invented event numbers).
- Moving from a database blob to per-line rows to object storage and finally to a local
  filesystem store as the privacy requirement became clear, and what each change cost.
- Why retention is enforced by the app rather than by a storage lifecycle rule once nothing is
  hosted.
- Out of scope: replaying sessions, live streaming, multiple users, recovering redacted text.
