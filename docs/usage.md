# Using lens

## Running it

From a release, download the archive for your platform from the
[releases](https://github.com/Flockdeck/lens/releases): `lens_<tag>_<os>_<arch>`, such as
`lens_v0.1.0_linux_amd64.tar.gz`, for Windows, macOS and Linux on amd64 and arm64. Unpack it and run
the program:

```sh
./lens serve --open        # lens.exe on Windows
```

From source, see [development.md](development.md).

`lens serve` prints the version, its address (`http://localhost:8000/` by default) and the data
folder. `--open` opens the address in a browser, `--host` and `--port` change where it listens, and
Ctrl+C stops it. With no command, `lens` serves. One process is the whole service: the web UI, the
API, the enrichment worker and the retention timer. The other commands are `lens version`,
`lens cleanup` (delete raw recordings past retention now; `serve` also does this on a timer) and
`lens check-storage` (check that the data folder is writable and readable).

Releases are signed with Flockdeck's release key (Flockdeck checks that before installing one), but
the executables are not code-signed, so expect a SmartScreen or Gatekeeper warning if you download
one by hand.

If something kills the program from outside (the packaged program is a launcher that starts the
real one as a child), the server behind it exits too.

## Where data lives

Everything lens keeps is in one folder: `%LOCALAPPDATA%\lens` on Windows,
`~/Library/Application Support/lens` on macOS, `~/.local/share/lens` on Linux. Set `DATA_DIR` to
move it. The folder holds the SQLite database (`lens.db`), the raw recordings under `recordings/`,
and the log file.

## Logging

When standard output is a terminal, lens logs there. When it is not (another program started it),
lens logs to `lens.log` in the data folder instead, rotated at 5 MB with three backups, so a pipe
nobody reads cannot stall it. `LOG_FILE=-` forces standard output and `LOG_FILE=<path>` picks a
file. Logs hold ids, counts and timings, never recording content, file names or query strings.

## Settings

Settings come from the Settings page, or from environment variables or a `.env` file in the working
directory (`lens serve --help`, and `src/lens/config.py` for the full list). A value saved on the
Settings page overrides the environment, and clearing it puts the environment's value back.

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATA_DIR` | the folder above | Where the database and recordings live |
| `DATABASE_URL` | `lens.db` in `DATA_DIR` | A SQLite URL (`sqlite+aiosqlite:///path`) |
| `HOST` | `127.0.0.1` | Bind address. `lens serve --host` wins. |
| `PORT` | `8000` | Port. `lens serve --port` wins. |
| `ALLOWED_HOSTS` | `127.0.0.1`, `localhost`, `::1` | Host names the server answers to: one name, names separated by commas or spaces, or a JSON list |
| `LOG_FILE` | blank | `-` is standard output; blank is standard output in a terminal and `lens.log` otherwise |
| `LOG_LEVEL` | `INFO` | Log level |
| `RAW_RETENTION_DAYS` | `30` | Days to keep raw recordings; `0` keeps them until you delete them |

The enricher settings (`ENRICHER`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `ANTHROPIC_WORKSPACE_ID`,
`OLLAMA_URL`, `OLLAMA_MODEL`) are in [enrichment.md](enrichment.md).

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
recorded, not as zero. [contracts.md](contracts.md) has the details.

What the parser has to cope with:

- Unreliable data. Delivery is at most once, so a `tool_call` can lack its `tool_result`; a crashed
  session ends with a half-written line or no stop line; a file can hit the 16 MiB cap.
- Forward compatibility. Unknown fields are ignored and unknown types skipped. Another `v` is
  refused. A hostile line (deeply nested JSON, huge integers) is counted as malformed instead of
  aborting the file.
- Redacted and clipped content. Secrets appear as `[redacted]`, long strings end in a
  `…[clipped N bytes]` marker. The original is not recoverable and lens does not try.
- Uneven coverage. Only Claude Code records fully. Other agents record only start and stop.

## What it computes

Computed in code (deterministic, no model): duration, turns, tool mix, error and interruption
rates, permission outcomes, time per pane status, completeness (clean, truncated, cut off), the
models used, files read and edited and commands run, and risky actions found by rules (force
pushes, `rm -rf` on broad targets, secret-file reads and so on) with a severity.

The model-written part is in [enrichment.md](enrichment.md).

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

[contracts.md](contracts.md) has the request and response shapes.

## How it works

[architecture.md](architecture.md) has the components, the data model and the flows as UML
diagrams. The parser is in section 2.2, the enrichers in 2.3, storage in 2.4, the data model
(including how a session is keyed, so resubmitting a recording is free) in 4, the worker in 5.3 to
5.5, and the database's locking in 7.
