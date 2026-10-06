# What stays on your machine

A recording contains prompts, file contents and command output. Flockdeck's own policy is that this
stays on the machine, and lens keeps to it.

## Enrichers

By default nothing is uploaded. The default enricher is a deterministic mock. The optional local one
talks to an [Ollama](https://ollama.com) server and refuses any URL that is not loopback; its HTTP
client ignores proxy variables and does not follow redirects. With either, the program makes no
outbound network calls.

Anthropic is an explicit opt-in. Choose it in the Settings page, or set `ENRICHER=anthropic` and
`ANTHROPIC_API_KEY` (the model is `ANTHROPIC_MODEL`, default `claude-haiku-4-5`; a key not tied to
one workspace also needs `ANTHROPIC_WORKSPACE_ID`). A key entered in Settings is stored in the local
database in plain text, like the `.env` it stands in for. It is write-only: the API says only
whether one is set and where it came from. Once chosen, each session's bounded digest (your prompts,
the agent's final messages, trimmed failing output and the metrics, never the raw recording) is sent
to `api.anthropic.com`. The log says so when the Anthropic enricher is built, and the status bar
changes to "Sends digests to Anthropic". The key is never logged.

## Loopback, and no key

The server binds `127.0.0.1` and warns if asked to bind anywhere else. There is no API key to manage
because nothing outside the machine can reach it. What a key would also have stopped is a web page
you have open talking to `127.0.0.1` for you (a form post, or DNS rebinding), so every request is
checked: the `Host` must be one of this machine's names (`ALLOWED_HOSTS`: one name, names separated
by commas or spaces, or a JSON list; default `127.0.0.1`, `localhost`, `::1`), and a write that
carries a foreign `Origin` (or `null`, or `Sec-Fetch-Site: cross-site`) is refused. There are no
CORS headers. `curl` and scripts, which send neither header, work as they are.

## No residue

Responses that carry recording-derived data (`/sessions`, `/batches`, `/stats`, `/config`,
`/settings`) have `Cache-Control: no-store`. The UI files are revalidated each time, so an upgrade
is never stale. Logs hold ids and counts, never content, file names or query strings. The UI makes
no external requests (a test enforces it) and sends no referrer.

## Visible

The footer says "Local only · storage: filesystem · enrichment: mock · raw kept 30 days", built from
`GET /config`, and says "Not verified as local-only" when a setting says otherwise.

## Short-lived raw data

Raw recordings are deleted after `RAW_RETENTION_DAYS` (30; 0 keeps them until you delete them), by
the program itself. The metrics and enrichments derived from them stay. Enrichments can quote the
recording, so [architecture.md](architecture.md) lists that among the known gaps.
