# CI checks

* [build workflow](build-workflow.md) - Reusable workflow that builds, version-checks, smoke-tests and archives the program on six platforms.
* [ci workflow](ci-workflow.md) - Checks that must pass before a merge or release, covering static checks, docs, tests, audit, Flockdeck compatibility and binaries.
* [audit job](dependency-audit.md) - Runs pip-audit over the runtime dependencies that ship in the binary.
* [docs job](docs-check.md) - Renders every Mermaid diagram in a browser and checks that relative markdown links resolve.
* [flockdeck-compat job](flockdeck-compat.md) - Runs Flockdeck's own updater checks over a lens release signed with a throwaway key, and compares the embedded trusted keys.
* [release workflow](release-workflow.md) - Tag-triggered pipeline that tests, builds, signs, publishes to GitHub and then to the download site.
* [static job](static-checks.md) - Lockfile, ruff, mypy strict on three platforms, actionlint, shellcheck and the notices check.
* [test job](test-matrix.md) - Pytest on Linux, Windows and macOS with Python 3.12, plus Linux on 3.13, with a 90 percent coverage floor on one leg.
