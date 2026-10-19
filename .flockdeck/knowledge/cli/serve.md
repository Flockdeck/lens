---
type: CLI Command
title: lens serve
description: Runs the whole service in one process, with the web UI, HTTP API, enrichment worker and retention timer.
resource: src/lens/cli.py
tags: [cli, server]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/cli.py, src/lens/api/app.py, src/lens/parent_watch.py]
---
`lens serve [--host HOST] [--port PORT] [--open]`. It is the default command: `lens` with no sub-command (or only serve flags) serves.

| Flag | Default | Effect |
|---|---|---|
| `--host` | [HOST](/config/host.md), `127.0.0.1` | Bind address. A non-loopback value logs a warning ([loopback bind](/security/loopback-bind.md)). |
| `--port` | [PORT](/config/port.md), 8000 | Port. |
| `--open` | off | Opens the UI in a browser one second after the server starts. |

Steps: load settings, `warn_if_not_loopback`, print two lines, start a [parent watch](/packages/parent-watch.md), run uvicorn with `create_app(settings, run_worker=True)` ([API app](/packages/api-app.md)) and `log_config=None`.

Output, first line (parsed by the Flockdeck app that launches lens): `lens <version> at http://localhost:<port>/`. The host name in the URL is `localhost` when the bind host is `127.0.0.1` or `::1`, otherwise the bind host. Second line: `data: <data dir>`. The smoke test checks the first line against the pattern `^lens \S+ at http://localhost:(\d{1,5})/$`.

On start it migrates the database ([migrations](/packages/db-migrate.md)). Exit code 0 after a graceful stop; SIGTERM or the parent watch drains in-flight items first.
