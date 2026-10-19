---
type: Build Step
title: Version stamping
description: The build rewrites __version__ in _version.py from the release tag, then checks the binary reports it.
resource: .github/workflows/build.yaml
tags: [build, release]
timestamp: 2026-10-19T00:00:00Z
code_paths: [.github/workflows/build.yaml, src/lens/_version.py]
---
In the `build` job: `VERSION="${TAG#v}"`, then `sed` replaces the `__version__ = ...` line in `src/lens/_version.py` (the replacement writes single quotes) and prints `app_version()`. After PyInstaller runs, `./dist/lens version` must equal `VERSION` or the job fails. CI uses the tag `v0.0.0-ci`; the default input is `v0.0.0-dev`. The committed value (`0.1.0`) is not what releases report. `pyproject.toml` also carries `version = "0.1.0"`, which the build does not touch. See [version command](../cli/version.md).
