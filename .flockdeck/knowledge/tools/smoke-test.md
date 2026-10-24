---
type: Developer Tool
title: packaging/smoke.py
description: Starts a built binary and uses it like a person would, in four phases.
resource: packaging/smoke.py
tags: [tools, testing, release]
timestamp: 2026-10-19T00:00:00Z
code_paths: [packaging/smoke.py, tests/fixtures/claude_full.jsonl]
---
`python packaging/smoke.py dist/lens[.exe]`; standard library only; exit 0 means pass. Run on every platform build ([build workflow](../ci/build-workflow.md)). On failure it prints the last 40 lines of any `lens.log`.

Phases:

1. Default setup: fresh data directory (name contains a space), `ENRICHER=mock`, stdout is a pipe nobody reads. Waits up to 60 s for `/readyz`, fetches the UI and CSS, `/config`, uploads the `claude_full.jsonl` fixture and waits for the batch, reads sessions and three events, `/settings`, checks `Host: evil.example` gets 421, `lens.db` and a non-empty `lens.log` exist, then stops it and restarts on the same data to confirm the session persists.
2. Launched the way Flockdeck launches it: a minimal environment (only the variables the Flockdeck helper supervisor passes through), `serve --host 127.0.0.1 --port <p>`, `ALLOWED_HOSTS=127.0.0.1`, `LOG_FILE=-`. The first output line must match `^lens \S+ at http://localhost:(\d{1,5})/$` with the chosen port. Checks `/healthz`, an upload, and that `Host: localhost` is refused with 421.
3. Anthropic enricher offline: key set to a fake value, SDK base URL pointed at an unused local port, `MAX_ATTEMPTS=1`; the item's error must mention Anthropic and not an import error, proving the SDK is bundled.
4. Hard kill of the launcher: the port must stop answering ([parent watch](../packages/parent-watch.md)).

`stop()` terminates and waits until nothing listens on the port. See [log file gotcha](../gotchas/log-file-when-piped.md).
