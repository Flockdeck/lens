---
type: Gotcha
title: PyInstaller cannot cross-compile
description: Each platform's binary is built on a runner of that platform; Windows on arm64 is allowed to fail.
resource: .github/workflows/build.yaml
tags: [build, pyinstaller, ci]
timestamp: 2026-10-19T00:00:00Z
code_paths: [.github/workflows/build.yaml, packaging/lens.spec]
---
The matrix uses native runners (Linux amd64 and arm64, macOS Intel and Apple silicon, Windows amd64 and arm64). The `windows-11-arm` leg is `experimental: true` and uses `continue-on-error`, because some dependencies may lack wheels there. But `release.py` requires all six platform archives, so a release without the arm64 Windows archive fails at `sums`/`sign` ([release script](/tools/release-script.md)). `lens.spec` lists hidden imports for modules found by name at run time (uvicorn loop and protocol modules, the SQLite dialect, Alembic DDL, the three enrichers, the Anthropic SDK) and the web and migration directories as data ([PyInstaller spec](/build/pyinstaller-spec.md)).
