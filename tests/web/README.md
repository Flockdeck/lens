# Web UI tests

The UI (`src/lens/web/`) talks only to the HTTP API in [docs/contracts.md](../../docs/contracts.md). These tests
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
uv run python tests/web/fake_server.py     # http://127.0.0.1:8765
```

Flags change `GET /config`: `--retention-days 0`, `--enricher ollama` (or `anthropic`),
`--no-config` (makes it fail, to see the "Status unavailable" state). `--port` changes the port.

It serves the real static files plus canned data: a batch that advances on each poll, a file
named `bad*.jsonl` that fails, and one session (the highest id) whose raw recording has
expired (`raw_available: false`, events and enrich return 410).

## Filter semantics

`from` and `to` on `GET /sessions` are inclusive UTC calendar days sent as bare `YYYY-MM-DD`.

## Privacy checks

`test_web_files_make_no_external_requests` fails if any file under `src/lens/web/`
contains an absolute URL other than the W3C XML namespaces, so a CDN, web font or analytics
script cannot slip in. `index.html` sets `<meta name="referrer" content="no-referrer">`.
