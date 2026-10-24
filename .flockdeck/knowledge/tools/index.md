# Developer tools

* [packaging/check_docs.py](check-docs.md) - Renders Mermaid diagrams and checks relative links in the repository's markdown files.
* [tests/web/fake_server.py](fake-api-server.md) - Stdlib fake of the lens HTTP API for developing and testing the UI without the real stack.
* [packaging/fake_release.py](fake-release.md) - Builds a signed release of random bytes with a throwaway key, for testing release tooling.
* [flockdeck_compat_test.go.txt](flockdeck-compat-test.md) - A Go test file kept as text and copied into a Flockdeck checkout by CI.
* [Lint and type-check configuration](lint-config.md) - ruff and mypy settings in pyproject.toml.
* [Makefile targets](makefile.md) - Developer shortcuts for install, run, lint, typecheck, test, e2e, binary and smoke.
* [packaging/release.py](release-script.md) - Checksums, signs and verifies a release in the format Flockdeck's updater accepts.
* [packaging/smoke.py](smoke-test.md) - Starts a built binary and uses it like a person would, in four phases.
* [Recording fixtures generator](test-fixtures.md) - tests/fixtures/build.py generates the .jsonl fixtures and a test checks the committed files match.
* [Test suite layout](test-suite.md) - pytest tests for API, worker, recording, enrichment, packaging and end-to-end flows, plus node tests for the UI.
