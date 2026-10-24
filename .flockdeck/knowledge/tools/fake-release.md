---
type: Developer Tool
title: packaging/fake_release.py
description: Builds a signed release of random bytes with a throwaway key, for testing release tooling.
resource: packaging/fake_release.py
tags: [tools, release, testing]
timestamp: 2026-10-19T00:00:00Z
code_paths: [packaging/fake_release.py, tests/packaging/test_release.py, tests/packaging/test_publish.py]
---
`python packaging/fake_release.py DIR [--version v0.3.0]` writes six fake archives of random bytes, runs `write_sums` and `run_sign` with a freshly generated Ed25519 key (`any_key=True`), and prints the public half as raw base64. Nothing it makes is a real release. Used by the [flockdeck-compat job](../ci/flockdeck-compat.md) and by the packaging tests (the publish tests exercise [publish-downloads](../release/publish-downloads.md)).
