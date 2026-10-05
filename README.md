# lens

lens reads the recordings [Flockdeck](https://github.com/Flockdeck/flockdeck) makes of coding-agent
sessions, works out what happened in each one, and shows it in a web page on your own machine:
how long it ran, what the agent did, where it got stuck, which actions were risky, and what the
session cost. It can ask a model for a summary and a judgement (outcome, frustration, whether the
model suited the task), and by default it asks nothing and sends nothing anywhere.

It is one program with nothing to install: no database server, no separate worker, nothing to sign
in to. Flockdeck can install and run it for you; it also runs on its own.

## Install and run

Download the archive for your platform from the
[releases](https://github.com/Flockdeck/lens/releases): `lens_<tag>_<os>_<arch>`, such as
`lens_v0.1.0_linux_amd64.tar.gz`, for Windows, macOS and Linux on amd64 and arm64. Unpack it and
run the program:

```sh
./lens serve --open        # lens.exe on Windows
```

It prints its address (http://127.0.0.1:8000), opens it with `--open`, and stops on Ctrl+C. One
process is the whole service: the web UI, the API, the enrichment worker and the retention timer.
Releases are signed with Flockdeck's release key (Flockdeck checks that before installing one), but
the executables are not code-signed, so expect a SmartScreen or Gatekeeper warning if you download
one by hand.

Everything it keeps is in one folder: `%LOCALAPPDATA%\lens` on Windows,
`~/Library/Application Support/lens` on macOS, `~/.local/share/lens` on Linux (set `DATA_DIR` to
move it). That is the SQLite database, the raw recordings under `recordings/`, and the log file.
When its output is not a terminal (another program started it) it logs to `lens.log` there, rotated,
instead of standard output, so a pipe nobody reads cannot stall it. If something kills the program
from outside, the server behind it exits too.

Settings come from the Settings page, or from environment variables or a `.env` file
(`lens serve --help`, and `src/lens/config.py` for the list). To enrich with a model on your own
machine: `ollama pull llama3.1:8b`, then choose Ollama in Settings.

## What stays on your machine

A recording contains prompts, file contents and command output. Flockdeck's own policy is that this
stays on the machine, and lens keeps to it:

- **By default nothing is uploaded.** The default enricher is a deterministic mock. The optional
  local one talks to an [Ollama](https://ollama.com) server and refuses any URL that is not
  loopback; its HTTP client ignores proxy variables and does not follow redirects. With either, the
  program makes no outbound network calls.
- **Anthropic is an explicit opt-in.** Choose it in the Settings page, or set `ENRICHER=anthropic`
  and `ANTHROPIC_API_KEY` (the model is `ANTHROPIC_MODEL`, default `claude-haiku-4-5`). A key entered
  in Settings is stored in the local database in plain text, like the `.env` it stands in for. It is
  write-only: the API says only whether one is set and where it came from. Once chosen, each
  session's bounded digest (your prompts, the agent's final messages, trimmed failing output and the
  metrics, never the raw recording) is sent to `api.anthropic.com`. The log says so at start-up and
  the status bar changes to "Sends digests to Anthropic". The key is never logged.
- **Loopback, and no key.** The server binds `127.0.0.1` and warns if asked to bind anywhere else.
  There is no API key to manage because nothing outside the machine can reach it. What a key would
  also have stopped is a web page you have open talking to `127.0.0.1` for you (a form post, or DNS
  rebinding), so every request is checked: the `Host` must be one of this machine's names
  (`ALLOWED_HOSTS`: one name, names separated by commas or spaces, or a JSON list; default
  `127.0.0.1`, `localhost`, `::1`), and a write that carries a foreign `Origin` (or `null`, or
  `Sec-Fetch-Site: cross-site`) is refused. There are no CORS headers. `curl` and scripts, which send
  neither header, work as they are.
- **No residue.** Responses carry `Cache-Control: no-store`; logs hold ids and counts, never content,
  file names or query strings; the UI makes no external requests (a test enforces it) and sends no
  referrer.
- **Visible.** The footer says "Local only · storage: filesystem · enrichment: mock · raw kept 30
  days", built from `GET /config`, and says "Not verified as local-only" when a setting says
  otherwise.
- **Short-lived raw data.** Raw recordings are deleted after `RAW_RETENTION_DAYS` (30; 0 keeps them
  until you delete them), by the program itself. The metrics and enrichments derived from them stay.

## Input

Flockdeck writes one JSON Lines file per conversation (a transcript). Every line has an envelope
(`v`, `seq`, `time`, `session`, `pane`, `type`, and usually `agent`, `model` and `conversation`) and
is one of `recording_started`, `recording_stopped`, `recording_truncated`, `user_prompt`,
`assistant_message`, `tool_call`, `tool_result`, `conversation_title` or `conversation_compacted`.
The format is versioned and documented in Flockdeck's `docs/recording-format.md`, with a JSON Schema
beside it.

Two kinds of file share version 1, and both are accepted. Flockdeck 0.3.48 and later builds the
transcript from the agent's stored conversation: it has every assistant message and no permission or
status lines, `pane` holds the conversation's id, and the first line says `start of the transcript`.
Version 0.3.47 recorded the agent's live hook events, so its files also have `session`,
`permission_prompt`, `permission_outcome` and `status` lines, a pane id and name, and `turned on` in
the first line. For a transcript the permission split and the time per status are shown as not
recorded, not as zero. `docs/contracts.md` has the details.

What the parser has to cope with:

- **Unreliable data.** Delivery is at most once, so a `tool_call` can lack its `tool_result`; a
  crashed session ends with a half-written line or no stop line; a file can hit the 16 MiB cap.
- **Forward compatibility.** Unknown fields are ignored and unknown types skipped. Another `v` is
  refused. A hostile line (deeply nested JSON, huge integers) is counted as malformed instead of
  aborting the file.
- **Redacted and clipped content.** Secrets appear as `[redacted]`, long strings end in a
  `…[clipped N bytes]` marker. The original is not recoverable and lens does not try.
- **Uneven coverage.** Only Claude Code records fully. Other agents record only start and stop.

## What it produces

**Computed in code** (deterministic, no model): duration, turns, tool mix, error and interruption
rates, permission outcomes, time per pane status, completeness (clean, truncated, cut off), the
models used, files read and edited and commands run, and **risky actions** found by rules (force
pushes, `rm -rf` on broad targets, secret-file reads and so on) with a severity.

**Enriched** (behind the `Enricher` interface): a summary, task category, outcome (done, abandoned,
stuck), a frustration estimate, stuck points, feedback on the prompts, whether the agent's model
suited the task, and notes on the risky actions. The prompt is built from the computed facts plus the
user's prompts, the final assistant messages and trimmed failing results, never from the raw
transcript. Input is size-bounded, JSON-encoded so transcript text cannot close a prompt tag, and the
model's output may only refer to event numbers it was given.

## The web interface

Static HTML, CSS and ES modules (no build step) served by the program and calling its API with
`fetch`: submit with a multi-select file picker or drag and drop, batch progress by polling, a
filterable session list, a session page with tabs (the model's analysis, the metrics, risky actions,
files, a paged raw event view) where each block says whether the recording or a model produced it,
trends over time, agent and model comparisons, and a Settings page. It has no private endpoints, so
anything the UI can do a script can do.

The look is Flockdeck's, as flockdeck.ai and the Flockdeck phone client wear it: dark only, Archivo
and JetBrains Mono served from the program itself (no font service is ever asked), 44px tap targets,
and the rule that green, amber and red mean only what they mean in a pane header. Every status is a
glyph and a word as well as a colour. `tests/web/test_design.py` keeps the UI to those rules.

## API

All JSON, no credentials. A request addressed to a host name that is not one of this machine's is
refused with `421`, and a write from another origin with `403`.

- `POST /batches`: multipart, one `files` part per `.jsonl` recording. Returns `202` with the batch
  id and per-file rejections (too large, wrong type, empty); `422` if nothing is usable.
- `GET /batches/{id}`, `POST /batches/{id}/retry`, `POST /batches/{id}/cancel`.
- `GET /sessions` (filters, pagination), `GET /sessions/{id}`, `DELETE /sessions/{id}`.
- `GET /sessions/{id}/events?after_seq=&limit=`: the parsed events, paged. `POST
  /sessions/{id}/enrich` re-enriches. Both answer `410` once the raw recording is gone.
- `GET /stats/trends`, `GET /stats/compare?by=agent|model`, `GET /stats/usage`.
- `GET /settings`, `PUT /settings`, `GET /config`, `GET /healthz`, `GET /readyz`, `GET /metrics`.

## How it works

[docs/architecture.md](docs/architecture.md) has the components, the data model and the flows as UML
diagrams. In short:

- **Parser** (`recording/`): a tolerant reader for format v1, then `analyze` for the metrics, risk
  rules and the model's digest. Pure functions over bytes.
- **Storage** (`storage/`): a `RecordingStore` interface with a filesystem implementation (atomic
  writes, private permissions, keys that cannot escape the data directory). The file is written
  before its database row, so a row never points at a missing file.
- **Worker** (`worker/`): runs inside the server process. It claims batch items, runs a bounded
  number at once, retries with exponential backoff and jitter, and tells retryable failures
  (timeouts, a model still loading) from permanent ones (unsupported version, empty file, expired
  raw). A claim token fences a claim that was taken over, parsing runs off the event loop, no
  database connection is held while the model runs, and shutdown drains for a bounded time. One bad
  session never fails a batch.
- **Idempotency.** A session is keyed on its recording session id. Resubmitting identical content is
  free; a longer version of the same recording replaces the session and is enriched again.
- **Database.** SQLAlchemy 2.0 (async, `aiosqlite`) and one Alembic migration, run on every start, on
  a SQLite file in WAL mode with foreign keys on. Writers begin with `BEGIN IMMEDIATE` so they queue
  instead of failing with "database is locked"; GET requests read through sessions that never take
  the write lock, so polling the UI cannot hold up the worker.
- **Enricher** (`enrich/`): the interface, the mock (default), the local Ollama implementation and the
  opt-in Anthropic one, all with schema-constrained output and a bounded retry on malformed JSON. The
  one in use is read from the stored settings before each item, so changing it needs no restart.

## Development

```sh
uv sync                    # Python 3.12 or later
uv run lens serve --open   # run it from source
make check                 # ruff, mypy --strict, the test suite
make binary                # build the single executable for this machine
make smoke                 # build it, then drive it over HTTP
```

The tests use a real SQLite database built from the migration, a real browser for the end-to-end
flows (Edge, else Chromium: `uv run playwright install chromium`), and a fake S3 server for the
release scripts. CI (`.github/workflows/ci.yaml`) runs on every push and pull request: lint, types on
all three platforms, the docs, the whole suite on Linux, Windows and macOS, a dependency audit, a
check that a lens release is accepted by Flockdeck's own updater code, and a build and smoke test of
the executable on six platforms. `ci-ok` is the one check to require.

## Releases

Pushing a tag like `v0.2.0` runs all of CI, builds the program on six platforms, signs the release
with Flockdeck's release key, publishes it on GitHub, and uploads it to `https://dl.flockdeck.ai/lens/`,
the CDN Flockdeck downloads its own updates from. [docs/releasing.md](docs/releasing.md) has the steps,
the layout on the CDN, the trust model and what has to be set up outside this repository.

## Licence

lens is released under the [PolyForm Noncommercial licence](LICENSE): free to use, copy and change for
any noncommercial purpose, source included. Copyright Jim Wright.

The program is one executable that carries other people's code: Python, the libraries it depends on,
and two typefaces. All of the code is permissive (MIT, BSD, Apache 2.0, the Python licence) apart from
certifi, which is under the MPL 2.0 and is bundled unmodified; the typefaces are under the SIL Open
Font License 1.1. The notices each of those licences asks for are in
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md), which is generated from the packages themselves,
checked in CI, and ships inside every release archive beside the program.

The agents whose recordings lens reads, and the model services it can call, are separate programs and
services with their own licences and terms; none of them is part of lens.
