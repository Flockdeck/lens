---
type: CI Check
title: build workflow
description: Reusable workflow that builds, version-checks, smoke-tests and archives the program on six platforms.
resource: .github/workflows/build.yaml
tags: [ci, build]
timestamp: 2026-10-19T00:00:00Z
code_paths: [.github/workflows/build.yaml]
---
Called by CI (tag `v0.0.0-ci`) and by the release workflow, so both go through the same steps. Inputs: `tag` (default `v0.0.0-dev`), `retention-days` (default 3). Permissions `contents: read`.

Matrix (native runners): `ubuntu-latest`, `ubuntu-24.04-arm`, `macos-15-intel`, `macos-latest`, `windows-latest`, `windows-11-arm` (the last is `experimental`, so `continue-on-error`). Timeout 30 minutes, `fail-fast: false`, bash shell.

Steps: checkout, `setup-uv`, Python 3.12, `uv sync --frozen`; [stamp the version](/release/version-stamp.md); [PyInstaller build](/release/pyinstaller-spec.md); compare `dist/lens version` with the stamped version; run the [smoke test](/tools/smoke-test.md) against the new binary; make the [archive](/release/release-archives.md); upload it.
