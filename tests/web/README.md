# Web UI tests

The UI (`src/session_lens/web/`) talks only to the HTTP API in `docs/contracts.md`. These tests
use a stdlib fake of that API, so they need no database, worker or real API.

## Run

From the repo root:

```
uv run pytest tests/web
```

That is the supported way: it runs the fake-server contract tests and also runs the node unit
tests below (skipped if `node` is not installed). pytest is not installed globally in every
environment, so use `uv run`.

The node helper tests can be run alone, from any directory:

```
node --test tests/web/helpers.test.mjs
```

Point `node --test` at the file, not the `tests/web` directory (Node treats a bare directory
argument as a file and fails).

## Look at the UI

```
python tests/web/fake_server.py            # http://127.0.0.1:8765, token: dev-token
```

It serves the real static files plus canned data: a batch that advances on each poll, a file
named `bad*.jsonl` that fails, and one session (the highest id) whose raw recording has
expired (`raw_available: false`, events and enrich return 410).

## Filter semantics

`from` and `to` on `GET /sessions` are inclusive UTC calendar days sent as bare `YYYY-MM-DD`.
