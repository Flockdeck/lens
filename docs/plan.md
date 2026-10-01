# session-lens: feature set and build plan

## Context

`yantra-test` is the take-home for the Yantra technical deep dive (brief in `README.md`): a
FastAPI service that ingests batches, enriches them with an LLM behind an interface (with a
mock), stores results in a DB via an ORM, and lets a client submit and retrieve work. The idea,
already written up in the README's "My idea" section, is **session-lens**: it ingests Flockdeck
pane recordings (JSONL, format v1, documented in
`../../flockdeck-recording/docs/recording-format.md` and `recording-line.schema.json` on branch
`feat/pane-recording`), computes metrics, enriches with an LLM, and serves a web UI that uses
only the public API. It deploys like `vael` (see `../RunEscape/.github/workflows/ci.yaml` and
`../RunEscape/deploy/k8s-infra/vael/`): GitHub Actions → ghcr.io → Flux in `wost/k8s-infra`,
with infra from terrawost.

The repo today holds only the README, a PyCharm sample `main.py` and a bare `pyproject.toml`.

## Decisions from the Q&A

- **Name / host:** session-lens, `session-lens.jmwri.dev`, image `ghcr.io/jmwri/session-lens`.
- **Enrichment (LLM):** summary, category, outcome, frustration score, **stuck points**,
  **prompt feedback**. Re-enrichment **overwrites** (stores prompt version + model for info).
- **Computed (no LLM):** duration, turns, tool mix, error/interrupt rate, permission split,
  time per status, completeness flags, **files touched + commands run**, **risky actions**
  (rule-based: rm -rf, force push, DROP, secret-file reads; severity), whose explanation can be
  added by the LLM.
- **LLM:** `Enricher` protocol; deterministic mock + Anthropic implementation, default
  `claude-haiku-4-5`, configurable. Token usage stored per enrichment.
- **Auth:** single bearer API token from the terrawost secret; UI asks once, keeps it in
  `sessionStorage`. `/healthz`, `/readyz`, `/metrics` unauthenticated (cluster-internal).
- **Processing:** separate worker Deployment (same image, `session-lens worker`) claiming
  items with `SELECT … FOR UPDATE SKIP LOCKED`; bounded concurrency, backoff with jitter,
  retryable vs permanent errors, idempotency on session id + content hash.
- **Submission:** `POST /batches` multipart, multiple `.jsonl` files; per-file reject reasons,
  `202` + batch id; `422` if none accepted. Size caps per file/request, matched on ingress.
- **Raw storage:** compressed (zstd) LONGBLOB in its own MySQL table.
- **Retention:** raw recordings deleted after 30 days by a CronJob; metrics/enrichment kept.
- **UI (no-build ES modules, served by FastAPI):** submit (multi-select + drag-drop), batch
  progress by **polling**, session list with filters, session detail (metrics, enrichment,
  risky actions, stuck points, files), **raw event view** (paged), **trends over time**,
  **agent/model compare**, token/cost totals. Actions: **delete session**, **retry failed
  items**, **cancel batch**.
- **DB / ORM:** MySQL 8 everywhere (docker compose locally, service container in CI, managed
  in cluster). ORM is **SQLAlchemy 2.0** (async engine, declarative `Mapped[...]` models,
  `AsyncSession`) with the `asyncmy` driver; worker claims via
  `select(...).with_for_update(skip_locked=True)`. Alembic migrations (autogenerate, reviewed
  by hand), run as an init container.
- **Observability:** JSON logs (ids/counts only, never content), Prometheus `/metrics`
  (queue depth, item duration, retries, LLM latency/tokens; wiring documented since k8s-infra
  has no Prometheus), health endpoints.
- **Tooling:** uv, ruff, mypy --strict, pytest.

## Step 1: README

Update `README.md` "My idea" with everything above: name, host, enrichment and computed fields,
auth, worker Deployment, raw storage, retention CronJob, management endpoints, new endpoints
below, UI screens, observability, model default. Replace `<app>` placeholders.

API additions to document:
- `POST /batches/{id}/retry` (failed items), `POST /batches/{id}/cancel` (queued items)
- `DELETE /sessions/{id}` (session, raw blob, enrichment)
- `GET /sessions/{id}/events?after_seq=&limit=` (raw event view)
- `POST /sessions/{id}/enrich` (re-enrich, overwrites)
- `GET /stats/trends?project=&interval=day|week`, `GET /stats/compare?by=agent|model`

## Step 2: scaffold (after README is agreed)

```
src/session_lens/
  config.py            pydantic-settings (DATABASE_URL, API_TOKEN, ENRICHER=mock|anthropic, ...)
  api/                 FastAPI app, routers: batches, sessions, stats, health; auth dependency
  recording/           v1 parser (tolerant rules), models (pydantic events), metrics, risk rules
  enrich/              Enricher protocol, MockEnricher, AnthropicEnricher, prompt + schema
  worker/              claim loop (SKIP LOCKED), retries/backoff, run_item
  db/                  SQLAlchemy models, session factory; alembic/ migrations
  cli.py               `session-lens api|worker|cleanup`
  web/                 static index.html, css, ES modules
tests/                 fixtures from documented examples; parser, metrics, worker, API, e2e
docker-compose.yml     MySQL 8 (+ app/worker for full local run)
Dockerfile             uv-based multi-stage
.github/workflows/ci.yaml   ruff, mypy, pytest vs MySQL; image on v* tag (semver, no "v")
deploy/k8s-infra/session-lens/  deployment-api, deployment-worker, cronjob-cleanup, service,
                     ingress (body-size limit), networkpolicy (+ egress to api.anthropic.com),
                     registry (ImageRepository/ImagePolicy)
```
Delete the PyCharm sample `main.py`. Consult the `claude-api` skill before writing
`AnthropicEnricher`.

## Verification

- `docker compose up -d mysql`, `uv run alembic upgrade head`, `uv run pytest` (MySQL).
- `uv run ruff check`, `uv run mypy --strict src`.
- Run `session-lens api` + `session-lens worker` with `ENRICHER=mock`; in the browser, submit
  several fixture files, watch the batch finish, open a session, view raw events, delete it,
  retry/cancel a batch, check trends/compare and `/metrics`.
- `docker build` succeeds; `kubectl apply --dry-run=client -f deploy/k8s-infra/session-lens`.
