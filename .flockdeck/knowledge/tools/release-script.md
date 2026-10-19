---
type: Developer Tool
title: packaging/release.py
description: Checksums, signs and verifies a release in the format Flockdeck's updater accepts.
resource: packaging/release.py
tags: [tools, release]
timestamp: 2026-10-19T00:00:00Z
code_paths: [packaging/release.py]
---
Python port of Flockdeck's `cmd/release`, writing the same file shapes.

| Command | Effect |
|---|---|
| `sums --version TAG --out DIR` | writes `checksums.txt` for the `lens_<TAG>_*` archives; errors on none, or on archives of another tag |
| `sign --version TAG --out DIR [--base URL] [--notes FILE] [--test-key]` | checks the listed archives against their hashes and requires all six platforms; signs; writes `checksums.txt.sig`, `manifest.json`, `manifest.json.sig`, `latest.json` |
| `verify --version TAG --out DIR` | checks signatures with the trusted keys, hashes and sizes, version and platforms; prints `FAIL ...` lines and exits 1 on any problem |
| `keys` | prints the two trusted public keys (raw base64), one per line |

`--base` defaults to the lens path under the public download host. The tag must match `vX.Y.Z` with an optional suffix. Errors are `ReleaseError` and print as `release: <message>`, exit 1. Key rules: [release signing](/security/release-signing.md) and [LENS_SIGNING_KEY](/config/lens-signing-key.md). Output formats: [checksums](/tables/release-checksums.md), [manifest](/tables/release-manifest.md), [latest.json](/tables/release-latest-json.md). Used by the [release workflow](/ci/release-workflow.md); unit tests are in `tests/packaging/test_release.py`.
