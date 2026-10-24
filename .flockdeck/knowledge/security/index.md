# Security boundaries

* [Anthropic egress is opt-in and bounded](anthropic-egress.md) - Only the Anthropic enricher sends data off the machine, and it sends a bounded digest, never the raw recording.
* [Anthropic API key handling](api-key-handling.md) - The key is a secret string, write-only through the API, never logged, and stored as plain text in the local database when set from the UI.
* [Download bucket must not be listable](bucket-not-listable.md) - The publish script fails if the public address lists the bucket; only uploaded files are public.
* [No CORS headers](cors-closed.md) - The app adds no Access-Control headers, so other origins cannot read responses.
* [Local-only guard](local-only-guard.md) - No API key exists; requests are accepted only for this machine's own host names and from same-origin writers.
* [Log content policy](log-content-policy.md) - Logs carry ids, counts, timings and exception types only; never recording content, filenames, query strings or messages.
* [Loopback bind and non-loopback warning](loopback-bind.md) - The server binds to 127.0.0.1 by default; any other bind address logs a warning.
* [No interactive API docs](no-interactive-docs.md) - docs, redoc and openapi endpoints are disabled so nothing loads scripts from a CDN.
* [Ollama local URL rule](ollama-local-url.md) - The Ollama base URL must be loopback or host.docker.internal, and the client ignores proxies and redirects.
* [Release signing and trusted keys](release-signing.md) - Releases are signed with Flockdeck's Ed25519 release key; only two public keys are trusted and the signing step refuses any other.
* [Response caching rules](response-caching.md) - Data endpoints are no-store; UI files are no-cache so an upgrade is never stale.
* [Store key validation](store-key-validation.md) - FilesystemStore refuses keys that could escape the data directory.
* [Upload limits](upload-limits.md) - Caps on file size, file count, field count, request size and filename length for uploads.
* [Web UI treats recording text as untrusted](web-untrusted-content.md) - The UI never uses innerHTML; summaries and events are inserted as text nodes.
* [Workflow secrets and permissions](workflow-secrets.md) - Release secrets sit in a protected environment; workflows default to read-only contents permission.
