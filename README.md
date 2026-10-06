# lens

lens is a local program that reads the recordings [Flockdeck](https://github.com/Flockdeck/flockdeck)
makes of coding-agent sessions and computes metrics for each one: how long it ran, what the agent
did, where it got stuck, which actions were risky. It can ask a model for a summary and a judgement
(outcome, frustration, whether the model suited the task), and by default it asks nothing and sends
nothing anywhere. The results are shown in a web page on your own machine.

It is one program: no database server, no separate worker, nothing to sign in to. Flockdeck can
install and run it for you; it also runs on its own.

## Install and run

```sh
uv sync
uv run lens serve --open
```

That needs [uv](https://docs.astral.sh/uv/) and Python 3.12 or later. The server listens on
`http://localhost:8000/` and `--open` opens it in your browser. To run a release instead of the
source, see [docs/usage.md](docs/usage.md).

## Where data lives

Everything lens keeps is in one folder: `%LOCALAPPDATA%\lens` on Windows,
`~/Library/Application Support/lens` on macOS, `~/.local/share/lens` on Linux. Set `DATA_DIR` to
move it.

## Privacy

The default mock enricher sends nothing, and the Ollama enricher talks only to a loopback address.
Anthropic is opt-in: once you choose it, each session's bounded digest (prompts, final messages,
trimmed failing output and the metrics) is sent to `api.anthropic.com`, never the raw recording. The
server listens on loopback and logs no recording content. See [docs/privacy.md](docs/privacy.md).

## Documentation

- [docs/usage.md](docs/usage.md): running it, settings, the input format, the web interface and the API
- [docs/enrichment.md](docs/enrichment.md): the enrichers and their settings
- [docs/privacy.md](docs/privacy.md): what stays on your machine and what can leave it
- [docs/architecture.md](docs/architecture.md): components, data model and flows
- [docs/contracts.md](docs/contracts.md): the interfaces between components and the HTTP API
- [docs/development.md](docs/development.md): working on lens, tests and CI
- [docs/releasing.md](docs/releasing.md): making a release

## Licence

lens is released under the [PolyForm Noncommercial licence](LICENSE): free to use, copy and change for
any noncommercial purpose, source included. Copyright Jim Wright.

The program is one executable that carries other people's code: Python, the libraries it depends on,
and two typefaces. All of the code is permissive (MIT, BSD, Apache 2.0, the Python licence) apart from
certifi, which is under the MPL 2.0 and is bundled unmodified; the typefaces are under the SIL Open
Font License 1.1. The notices each of those licences asks for are in
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md), which is generated from the packages themselves,
checked in CI, and ships inside every release archive beside the program.

The agents whose recordings lens reads, and the model services it can call, are separate programs and
services with their own licences and terms; none of them is part of lens.
