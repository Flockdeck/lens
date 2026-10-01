# Component contracts

session-lens is built as independent components. Each owns a directory and codes against the
interfaces below, so they can be written in parallel and joined later. The product is described
in `README.md`, the decisions in `docs/plan.md`, the input format in Flockdeck's
`docs/recording-format.md` (branch `feat/pane-recording` of the flockdeck repo; the key rules
are repeated in the README).

| Component | Owns | Depends on |
| --- | --- | --- |
| recording | `src/session_lens/recording/`, `tests/recording/`, `tests/fixtures/` | nothing |
| enrich | `src/session_lens/enrich/`, `tests/enrich/` | recording's `Analysis` type |
| worker | `src/session_lens/worker/`, `src/session_lens/db/` (except `models.py`), `alembic/`, `alembic.ini`, `src/session_lens/cli.py` | recording, enrich, `db/models.py` |
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
def iter_events(data: bytes, after_seq: int = 0, limit: int = 200) -> list[Event]: ...  # raw view
```

`Metrics` (stored in `sessions.metrics`): `duration_seconds`, `turns`, `tool_calls`,
`tool_mix: dict[str,int]`, `tool_errors`, `tool_interrupted`, `unpaired_calls`,
`permission: {prompts, allowed, denied, auto_approved, abandoned}`,
`status_seconds: dict[str,float]`, `redacted_lines`, `clipped_lines`.

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

def build_enricher(settings: Settings) -> Enricher: ...   # mock or anthropic
```

## worker

- `session-lens worker` runs the claim loop; `session-lens api` serves; `session-lens cleanup`
  deletes raw recordings older than `raw_retention_days` (used by a CronJob);
  `session-lens migrate` runs `alembic upgrade head`.
- Claiming uses `with_for_update(skip_locked=True)`; stale claims (`locked_at` older than
  `claim_timeout_seconds`) are re-queued. Backoff sets `not_before`.
- Processing one item: decompress the raw blob → `parse` → `analyze` → upsert `Session` keyed on
  `(recording_session, content_hash)` → `enrich` → upsert `Enrichment` → item `done`. A
  `Batch` becomes `done` when no item is queued or running.
- Exposes `worker/queue.py` helpers the API reuses: `create_batch(session, files)`,
  `retry_failed(session, batch_id)`, `cancel_batch(session, batch_id)`, and
  `store_raw(session, data) -> RawRecording` (hash + zstd).

## HTTP API (all JSON; everything except `/healthz`, `/readyz`, `/metrics` needs
`Authorization: Bearer <API_TOKEN>`)

- `POST /batches` (multipart, field `files`, repeated) → `202 {id, accepted: [...], rejected:
  [{filename, reason}]}`; `422` if nothing accepted
- `GET /batches/{id}` → `{id, status, counts: {queued, running, done, failed, cancelled},
  items: [{id, filename, status, attempts, error, session_id}]}`
- `POST /batches/{id}/retry`, `POST /batches/{id}/cancel`
- `GET /sessions?project=&agent=&model=&category=&outcome=&from=&to=&limit=&offset=` →
  `{total, items: [SessionSummary]}`
- `GET /sessions/{id}` → full record (metrics, risky actions, files touched, warnings, enrichment)
- `GET /sessions/{id}/events?after_seq=&limit=` → events from the raw blob (`410` once deleted)
- `POST /sessions/{id}/enrich` (overwrites), `DELETE /sessions/{id}`
- `GET /stats/trends?project=&interval=day|week` →
  `[{bucket, sessions, outcomes: {...}, avg_frustration, tool_error_rate}]`
- `GET /stats/compare?by=agent|model` →
  `[{key, sessions, outcomes: {...}, tool_error_rate, permission_denial_rate, avg_frustration}]`
- `GET /stats/usage` → `{input_tokens, output_tokens, enrichments}`
- `GET /healthz` (process up), `GET /readyz` (DB reachable), `GET /metrics` (Prometheus)
- The static UI is served from `/` by the API app (`StaticFiles` over `session_lens/web/`).

## Rules for every component

- Python 3.12, fully typed (`mypy --strict` clean), `ruff` clean, tests with `pytest`.
- Tests that need a database use MySQL via `DATABASE_URL` (docker compose), never SQLite.
- Logs carry ids and counts only. Never log recording content, prompts or messages.
- Commit on your own branch with clear messages. Do not push, merge, or touch other
  components' files.
