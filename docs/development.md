# Development

You need [uv](https://docs.astral.sh/uv/) and Python 3.12 or later.

```sh
uv sync                    # install the dependencies
uv run lens serve --open   # run it from source
make check                 # ruff, mypy --strict, the test suite
make binary                # build the single executable for this machine
make smoke                 # build it, then drive it over HTTP
```

`make help` lists the other targets: `lint`, `format`, `typecheck`, `test`, `e2e` (the end-to-end
tests without a browser), `e2e-browser`, `run` and `clean`.

## Tests

The tests use a real SQLite database built from the migration, a real browser for the end-to-end
flows (Edge, else Chromium: `uv run playwright install chromium`), and a fake S3 server for the
release scripts. The browser tests use a lot of memory, so run one test run at a time. The tests for
the web UI have their own notes in [tests/web/README.md](../tests/web/README.md).

## Docs

`packaging/check_docs.py` renders every Mermaid diagram in a real browser and checks that every
relative link in the Markdown files resolves. It loads Mermaid from a CDN, so it needs network
access. CI runs it as `uv run python packaging/check_docs.py`.

## CI

`.github/workflows/ci.yaml` runs on every push to `main`, every pull request, every Monday, and
when a release calls it. Its jobs are:

- `static`: the lockfile matches `pyproject.toml`, ruff, mypy `--strict` on linux, win32 and darwin,
  actionlint, shellcheck on the publish script, and the third-party notices.
- `docs`: the check above.
- `test`: the whole suite on Linux, Windows and macOS with Python 3.12, and on Linux with 3.13. Only
  the Linux 3.12 leg enforces the 90% coverage floor.
- `audit`: `pip-audit` over the runtime dependencies.
- `flockdeck-compat`: a check that a lens release is accepted by Flockdeck's own updater code.
- `binaries`: a build and smoke test of the executable on six platforms (Windows on arm64 reports
  but does not block).
- `ci-ok`: passes when all of the above pass. It is the one check to require.

## Releases

Pushing a tag like `v0.2.0` runs all of CI, builds the program on six platforms, signs the release
with Flockdeck's release key, publishes it on GitHub, and uploads it to
`https://dl.flockdeck.ai/lens/`, the CDN Flockdeck downloads its own updates from.
[releasing.md](releasing.md) has the steps, the layout on the CDN, the trust model and what has to
be set up outside this repository.
