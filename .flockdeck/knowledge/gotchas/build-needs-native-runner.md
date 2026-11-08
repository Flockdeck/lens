---
type: Gotcha
title: PyInstaller cannot cross-compile
description: Each platform's binary is built on a runner of that platform; the build installs no dev group so Windows on arm64 needs no source builds.
resource: .github/workflows/build.yaml
tags: [build, pyinstaller, ci]
timestamp: 2026-10-19T00:00:00Z
code_paths: [.github/workflows/build.yaml, packaging/lens.spec]
---
The matrix uses native runners (Linux amd64 and arm64, macOS Intel and Apple silicon, Windows amd64 and arm64). All six legs must pass, because `release.py` requires all six platform archives and a release without one fails at `sums`/`sign` ([release script](../tools/release-script.md)). The build syncs `--no-dev --group build` (runtime dependencies plus PyInstaller) and runs with `uv run --no-sync`: the dev group holds `cryptography`, which has no Windows arm64 wheel in `uv.lock` and would be compiled from source on `windows-11-arm`. The `windows-11-arm` leg was `experimental` with `continue-on-error` before that. `lens.spec` lists hidden imports for modules found by name at run time (uvicorn loop and protocol modules, the SQLite dialect, Alembic DDL, the three enrichers, the Anthropic SDK) and the web and migration directories as data ([PyInstaller spec](../release/pyinstaller-spec.md)).
