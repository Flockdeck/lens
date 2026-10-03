# Component contracts

session-lens is built as independent components. Each owns a directory and codes against the
interfaces below, so they can be written in parallel and joined later. The product is described
in `README.md`, the decisions in `docs/plan.md`, the input format in Flockdeck's
`docs/recording-format.md` and `docs/recording-line.schema.json` (main branch of the flockdeck
repo; the key rules are repeated in the README and below, and the schema is copied to
`tests/fixtures/recording-line.schema.json`).

| Component | Owns | Depends on |
| --- | --- | --- |
| recording | `src/session_lens/recording/`, `tests/recording/`, `tests/fixtures/` | nothing |
| enrich | `src/session_lens/enrich/`, `tests/enrich/` | recording's `Analysis` type |
| worker | `src/session_lens/worker/`, `src/session_lens/storage/`, `src/session_lens/db/` (except `models.py`), `alembic/`, `alembic.ini`, `src/session_lens/cli.py` | recording, enrich, `db/models.py` |
| api | `src/session_lens/api/`, `tests/api/` | `db/models.py`, `config.py` |
| web | `src/session_lens/web/`, `tests/web/` | the HTTP API below |
| deploy | `Dockerfile`, `docker-compose.yml`, `.github/`, `deploy/`, `Makefile` | everything, by name only |

`src/session_lens/config.py` and `src/session_lens/db/models.py` are shared and already written.
Do not edit them without need; if you must, keep the change small and say so in your final
message. Do not edit `pyproject.toml` except to add a dependency your component needs.

## recording

```python
# recording/models.py
class Event(BaseModel):           # one parsed line; extra fields allowed, envelope typed
    v: int; seq: int; time: datetime; session: str; pane: str
    type: str                      # unknown types are kept as-is, not rejected
    # optional envelope + type-specific fields as in the format reference
    ...

class Analysis(BaseModel):         # everything computed from one file, no LLM
    recording_session: str
    project: str | None; agent: str | None; model: str | None; pane: str | None
    pane_name: str | None
    conversation: str | None       # the agent's conversation id, where the file has one
    title: str | None              # the last conversation_title line; None if the file has none
    source_format: Literal["transcript", "hooks"] | None
    started_at: datetime | None; ended_at: datetime | None
    completeness: Literal["clean", "truncated", "cut_off", "partial_agent"]
    metrics: Metrics               # see below
    risky_actions: list[RiskyAction]   # {seq, tool, summary, severity: low|medium|high, rule}
    files_touched: FilesTouched        # {read: [...], edited: [...], commands: [...]}
    warnings: list[str]            # e.g. "skipped 2 unknown event types", "unterminated last line"
    digest: Digest                 # compact input for the LLM: user prompts, final assistant
                                   # messages, failing tool results (trimmed), key metrics

# recording/parser.py
class UnsupportedVersion(Exception): ...      # permanent failure
class EmptyRecording(Exception): ...          # permanent failure
def parse(data: bytes) -> list[Event]: ...    # tolerant: skips bad last line / unknown types
def analyze(events: list[Event]) -> Analysis: ...
def parse_lines(lines: Iterable[str]) -> list[Event]: ...   # same tolerance as parse()
def analyze_lines(lines: Iterable[str]) -> Analysis: ...    # parse_lines + analyze
```

`parse(data)` splits on a newline and calls `parse_lines`. A page of lines from the middle of a
file parses fine (no `recording_started` line required). The events endpoint parses the whole
fetched file and slices by `seq`.

`Metrics` (stored in `sessions.metrics`): `duration_seconds`, `turns`, `tool_calls`,
`tool_mix: dict[str,int]`, `tool_errors`, `tool_interrupted`, `unpaired_calls`,
`permission: {prompts, allowed, denied, auto_approved, abandoned}`,
`status_seconds: dict[str,float]`, `redacted_lines`, `clipped_lines`, `models: list[str]` (every
model named, in order; absent in sessions stored before it was added), and, absent in sessions
stored before they were added: `permissions_recorded: bool`, `status_recorded: bool`,
`compactions: int`, `usage: {input_tokens, output_tokens, cache_creation_input_tokens,
cache_read_input_tokens} | None`.

### The two kinds of file

Both are format `v: 1`, so `v` cannot tell them apart; the first line can
(`Analysis.source_format`, also on the digest). Both are accepted.

| | `"transcript"` (Flockdeck 0.3.48 and later) | `"hooks"` (0.3.47) |
| --- | --- | --- |
| first line | `recording_started`, text `start of the transcript` | text `turned on` or `resumed` |
| made from | the agent's stored conversation | the events the agent reported while running |
| `pane` | the conversation's id (so `Analysis.pane` is one too) | the pane's id |
| `paneName` | not written (`pane_name` is None) | written |
| `time` | when the event happened | when Flockdeck wrote the line |
| `session` id | `<first event>-<conversation>` | `<start of recording>-<pane>` |
| `session`, `permission_prompt`, `permission_outcome`, `status` | never | written |
| `assistant_message` | every message, including those between tool calls | the last of each turn |
| `user_prompt` | only what the person typed | also the agent's own (reminders, task notifications, slash commands) |
| `model` | on `assistant_message` and `tool_call` only, the turn's own id (`claude-opus-5-5`) | on every line, the model the pane was asked for (`opus`) |
| `gitBranch`, `cwd`, `agentVersion`, `usage`, `stopReason`, `conversation_title`, `conversation_compacted` | written where the stored conversation has them (an older transcript may lack them) | never |
| subagents | left out: no line has `subagent`; the Task result is in the main agent's tool results | lines with `subagent` set |

How the reader handles that:

- A line type or field the reader does not know is skipped or kept as an extra. A field of a
  known name in an unexpected shape reads as absent and the line is kept. Only the envelope
  (`v`, `seq`, `time`, `session`, `pane`, `type`) is strict. This covers the newer fields too:
  `usage`, `stopReason`, `gitBranch`, `cwd`, `agentVersion`, `title`, `trigger`, `tokensBefore`
  and `tokensAfter`.
- `Analysis.title` is the `title` of the last `conversation_title` line (a line is written when
  the title first appears and when it changes). `Analysis.conversation` is the first
  `conversation` seen. The database has no column for either yet.
- **Permission and status lines are absent from a transcript, so the permission split and the time
  in each status are empty, not zero.** `permission` stays all zeros and `status_seconds` empty,
  and `permissions_recorded` / `status_recorded` say whether the file had any such line at all
  (false for every transcript). A consumer must not read `denied == 0` as "nothing was denied"
  when `permissions_recorded` is false. A tool the user refused is an error `tool_result`, so it
  counts under `tool_errors`, not `permission.denied`.
- `turns` and the digest's prompts count only prompts a person typed. A prompt that starts with
  `<system-reminder`, `<task-notification`, `<command-name>`, `<command-message>`,
  `<local-command-...`, `[Request interrupted by user` or `This session is being continued from a
  previous conversation` is the agent's own and is skipped (a transcript has none; a file from
  hooks has them). The prefixes are a heuristic: the format reference lists the kinds, not the
  markup.
- The digest's `final_messages` are the last assistant message of each turn (the last one before
  the next typed prompt), so a transcript's "Let me look at the client first" messages do not push
  the real answers out. A file from hooks has one per turn, so it gives the same list as before.
- `usage` is summed over every line that has one: Flockdeck writes a reply's usage on its first
  line only, so no deduplication is needed. The numbers are the agent's, for the main agent only,
  and not a cost. `None` if no line has one.
- `compactions` counts `conversation_compacted` lines. The summary itself is not in a transcript.
- `tool_calls` of a transcript do not include a subagent's own calls; those of a file from hooks do.
- `completeness`: a `recording_truncated` last line is `truncated` (the cap is 16 MiB either way),
  a missing stop line is `cut_off`, and a file whose only lines are the recorder's own is
  `partial_agent`. Unknown line types are ignored when looking for the ending.
- `seq` runs from 1 with no gaps in both kinds; a gap is reported as a warning.
- `duration_seconds` is last `time` minus first. In a transcript `time` is when the event
  happened, so a conversation resumed after a break includes the break.
- Redaction (`[redacted]`, `[withheld: a secret file]`) and clipping (`…[clipped N bytes]`, with
  the `clipped` object) are the same in both. `clipped` may also name `title`, `cwd` and
  `gitBranch`. In a file from before 0.3.48 a very large tool `input` can be the object
  `{"_omitted":"too large to record"}`; a call with it has no path or command to read.

## enrich

```python
# enrich/base.py
class EnrichmentResult(BaseModel):
    summary: str; category: str          # bugfix|feature|refactor|exploration|docs|tests|ops|other
    outcome: Literal["done", "abandoned", "stuck"]
    frustration: float                   # 0..1
    stuck_points: list[StuckPoint]       # {description, approx_seq: int | None}
    prompt_feedback: str | None
    risk_notes: list[RiskNote]           # {seq, explanation}
    input_tokens: int; output_tokens: int; model: str; prompt_version: str

class EnrichmentError(Exception):
    retryable: bool                      # rate limit / timeout / 5xx = True; bad output after
                                         # bounded retries = False

class Enricher(Protocol):
    async def enrich(self, analysis: Analysis) -> EnrichmentResult: ...

def build_enricher(settings: Settings) -> Enricher: ...   # mock (default), local ollama, or opt-in anthropic (needs ANTHROPIC_API_KEY)
```

## storage (owned by the worker component)

session-lens is local: **no recording data leaves the machine**. Raw recordings are files on the
local filesystem under `DATA_DIR` by default (`STORAGE=filesystem`). An S3-compatible store
(`STORAGE=s3`, a bucket you run yourself; `pip install session-lens[s3]`) is an optional
implementation behind the same interface. The database keeps **one `raw_recordings` row per
file** (hash, size, `object_key`, `created_at`, `expired_at`); the bytes are fetched whole when
needed (at most 16 MiB).

```python
# storage/base.py
class RecordingExpired(Exception): ...           # the file is gone (deleted by retention, or by hand)

class RecordingStore(Protocol):
    async def put(self, key: str, data: bytes) -> None: ...
    async def get(self, key: str) -> bytes: ...          # raises RecordingExpired if missing
    async def delete(self, key: str) -> None: ...        # idempotent
    async def ping(self) -> None: ...                    # for /readyz; raises if unusable
    async def aclose(self) -> None: ...                  # call once at shutdown

def build_store(settings: Settings) -> RecordingStore: ...   # filesystem (default) or s3
```

`FilesystemStore(root)` writes atomically (temp file in the same directory, then `os.replace`),
creates files 0600 and directories 0700 where the OS allows, removes empty parent directories on
delete, and rejects any key that is absolute, contains `..`, or resolves outside the root
(`InvalidKey`).

Keys are `{s3_prefix}YYYY/MM/<uuid4>.jsonl` (`s3_prefix` defaults to `recordings/` and applies to
both stores), one file per upload, never shared between rows. Helpers in `worker/queue.py` (all
take the store explicitly):

- `await store_raw(session, store, data: bytes) -> RawRecording`: hash the bytes, **put the file
  first**, then add the row (flushed, not committed). A failure after the put leaves an orphan
  file (harmless, and unreferenced); a row never points at a missing file.
- `await read_raw(session, store, raw_id) -> bytes`: raises `RecordingExpired` if the row has
  `expired_at` set or the file is gone (and then sets `expired_at`).
- `await delete_raws_for_session(session, store, session_id) -> int`: delete every raw row and
  file linked to the session (through `Session.raw_id` and `batch_items.session_id`; call it
  before deleting the session; files best effort, then rows).

### Retention and cleanup

- Retention is **enforced by the app**: raw files are kept `raw_retention_days` (default 30;
  `0` keeps them forever). Cleanup deletes the stored file of each raw row past retention (best
  effort; a missing file is fine) and then sets `expired_at`, in chunks. A raw that a queued or
  running item still needs is skipped. It also deletes finished batches (and their items) older
  than 90 days. Sessions, metrics and enrichments are kept.
- The **worker runs cleanup in-process** every `cleanup_interval_seconds` (default 3600; `0`
  disables) as a background task that logs and survives its own errors, so no CronJob is needed.
  Cleanup holds a MySQL named lock (`GET_LOCK`), so overlapping runs (several workers, or a
  manual run) skip instead of colliding. `session-lens cleanup` runs it once by hand.
- `session-lens check-storage` prints which store is in use and verifies put/get/delete of a
  probe object (exit 0/1). `session-lens check-bucket [--strict]` applies only to
  `STORAGE=s3` (an optional bucket expiry rule only sweeps orphans from failed uploads).
- An item that references an expired recording fails permanently ("raw recording expired").
  `GET /sessions/{id}/events` and `POST /sessions/{id}/enrich` return `410` for an expired
  recording; session responses carry `raw_available: bool` so the UI can disable them.
- Deleting a session also deletes its raw rows and files. A longer upload of the same recording
  session supersedes the stored session in place.
- Never log recording content; object keys are random and safe to log.

## worker

- `session-lens worker` runs the claim loop; `session-lens api` serves; `session-lens cleanup`
  runs retention cleanup once (the worker also does it on a timer); `session-lens migrate` runs `alembic upgrade head`.
- Claiming uses `with_for_update(skip_locked=True)`; stale claims (`locked_at` older than
  `claim_timeout_seconds`) are re-queued. Backoff sets `not_before`.
- Processing one item: `read_raw` → `analyze(parse(data))` (in a thread) → upsert `Session`
  keyed on `recording_session` (superseded in place when the content differs) → `enrich` → upsert `Enrichment` → item `done`.
  A `Batch` becomes `done` when no item is queued or running.
- Exposes `worker/queue.py` helpers the API reuses: `create_batch(session, store, files)`,
  `retry_failed(session, batch_id)`, `cancel_batch(session, batch_id)`, plus the storage helpers
  above and `upsert_enrichment`.

## HTTP API (all JSON, no credentials: the service is for this machine only. A request for another
host name gets `421`, a write from another origin `403`; see `api/local.py`)

- `POST /batches` (multipart, field `files`, repeated) → `202 {id, accepted: [...], rejected:
  [{filename, reason}]}`; `422` if nothing accepted
- `GET /batches/{id}` → `{id, status, counts: {queued, running, done, failed, cancelled},
  items: [{id, filename, status, attempts, error, session_id}]}`
- `POST /batches/{id}/retry`, `POST /batches/{id}/cancel`
- `GET /sessions?project=&agent=&model=&category=&outcome=&from=&to=&limit=&offset=` →
  `{total, items: [SessionSummary]}`
- `GET /sessions/{id}` → full record (metrics, risky actions, files touched, warnings, enrichment)
- `GET /sessions/{id}/events?after_seq=&limit=` → a page of parsed events: fetch the file with `read_raw`,
  `parse` it, keep events with `seq > after_seq`, return `{items, next_after_seq}`; `410` once
  the raw recording has expired or been deleted
- `POST /sessions/{id}/enrich` (overwrites), `DELETE /sessions/{id}`
- `GET /settings` → `{enricher, anthropic_api_key: {set, source: settings|environment|null}, anthropic_model, ollama_url, ollama_model, overridden}`; the key is never returned
- `PUT /settings` — send only what changes; `null` removes an override (the environment's value applies again). `422` for an `anthropic` enricher with no key, an Ollama URL that is not this machine, or whitespace in the key. Stored in `app_settings`; `DynamicEnricher` (`runtime_settings.py`) re-reads it every 2 s in both the API and the worker
- `GET /stats/trends?project=&interval=day|week` →
  `[{bucket, sessions, outcomes: {...}, avg_frustration, tool_error_rate}]`
- `GET /stats/compare?by=agent|model` →
  `[{key, sessions, outcomes: {...}, tool_error_rate, permission_denial_rate, avg_frustration}]`
- `GET /stats/usage` → `{input_tokens, output_tokens, enrichments}`
- `GET /healthz` (process up), `GET /readyz` (DB and `store.ping()` reachable), `GET /metrics` (Prometheus)
- The static UI is served from `/` by the API app (`StaticFiles` over `session_lens/web/`).

## Rules for every component

- Python 3.12, fully typed (`mypy --strict` clean), `ruff` clean, tests with `pytest`.
- Tests that need a database use MySQL via `DATABASE_URL` (docker compose), never SQLite. Tests
  that need the object store use SeaweedFS from docker compose (`S3_ENDPOINT_URL`), never a mock of
  the S3 API; unit tests of other components may use an in-memory `RecordingStore` fake.
- Logs carry ids and counts only. Never log recording content, prompts or messages.
- Commit on your own branch with clear messages. Do not push, merge, or touch other
  components' files.
