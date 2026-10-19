---
type: Security Boundary
title: Release signing and trusted keys
description: Releases are signed with Flockdeck's Ed25519 release key; only two public keys are trusted and the signing step refuses any other.
resource: packaging/release.py
tags: [security, release, signing]
timestamp: 2026-10-19T00:00:00Z
code_paths: [packaging/release.py, packaging/fake_release.py, packaging/flockdeck_compat_test.go.txt, .github/workflows/ci.yaml, .github/workflows/release.yaml]
---
`checksums.txt` and `manifest.json` each get a detached base64 Ed25519 signature. The Flockdeck app trusts a primary and a standby public key, which `release.py` embeds (public keys, as compiled into Flockdeck's `internal/selfupdate`). `sign` derives the public half of `LENS_SIGNING_KEY` ([secret](/config/lens-signing-key.md)) and refuses to proceed unless it equals one of the two, so no unusable release is produced; `--test-key` bypasses this for tests. After signing it verifies both signatures with the public key before writing them. `verify` checks signatures, listed hashes and sizes, version and the presence of all six platform archives.

The key lives in the `release` environment of the repository, which only a `v*` tag may deploy to (per the workflow comment). The [flockdeck-compat job](/ci/flockdeck-compat.md) runs Flockdeck's own updater checks over a release signed with a throwaway key and compares the embedded keys. Formats: [checksums](/tables/release-checksums.md), [manifest](/tables/release-manifest.md), [latest.json](/tables/release-latest-json.md).
