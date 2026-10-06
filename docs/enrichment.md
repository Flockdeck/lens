# Enrichment

lens computes the metrics for a session in code. Enrichment is the part a model writes, behind the
`Enricher` interface: a summary, task category, outcome (done, abandoned, stuck), a frustration
estimate, stuck points, feedback on the prompts, whether the agent's model suited the task, and
notes on the risky actions.

The prompt is built from the computed facts plus the user's prompts, the final assistant messages
and trimmed failing results, never from the raw transcript. Input is size-bounded, JSON-encoded so
transcript text cannot close a prompt tag, and the model's output may only refer to event numbers it
was given.

## Enrichers

| Enricher | `ENRICHER` | Sends anything off the machine |
| --- | --- | --- |
| Mock (default) | `mock` | No. It is deterministic and calls nothing. |
| Ollama | `ollama` | No. It talks to an Ollama server and refuses any URL that is not loopback. |
| Anthropic | `anthropic` | Yes, once chosen: a bounded digest of each session. See [privacy.md](privacy.md). |

Choose one on the Settings page, or set the environment variables below. The enricher in use is
read from the stored settings before each item, so changing it needs no restart.

To enrich with a model on your own machine, run `ollama pull llama3.1:8b`, then choose Ollama in
Settings.

| Variable | Default | Meaning |
| --- | --- | --- |
| `ENRICHER` | `mock` | `mock`, `ollama` or `anthropic` |
| `ANTHROPIC_API_KEY` | none | Required for `anthropic` |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5` | Model to call |
| `ANTHROPIC_WORKSPACE_ID` | none | Needed only for a key that is not tied to one workspace |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Must be this machine |
| `OLLAMA_MODEL` | `llama3.1:8b` | Model to call |

A key entered in Settings is stored in the local database in plain text, like the `.env` it stands
in for. It is write-only: the API says only whether one is set and where it came from.

How the enrichers are built, retried and checked is in [architecture.md](architecture.md), section
2.3.
