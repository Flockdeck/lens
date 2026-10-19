---
type: CI Check
title: flockdeck-compat job
description: Runs Flockdeck's own updater checks over a lens release signed with a throwaway key, and compares the embedded trusted keys.
resource: .github/workflows/ci.yaml
tags: [ci, release, compat]
timestamp: 2026-10-19T00:00:00Z
code_paths: [.github/workflows/ci.yaml, packaging/fake_release.py, packaging/flockdeck_compat_test.go.txt]
---
Release files are verified by the Flockdeck app, so this job judges them with Flockdeck's code at its current `main`:

1. Check out this repository and `Flockdeck/flockdeck` (no persisted credentials); set up Go from Flockdeck's `go.mod`.
2. `fake_release.py` builds a signed fake release at `v0.3.0` and prints the throwaway public key ([tool](/tools/fake-release.md)); `release.py keys` prints the two keys lens embeds.
3. Environment for the Go tests: `LENS_RELEASE_DIR`, `LENS_VERSION`, `LENS_TEST_PUBKEY`, `LENS_TRUSTED_KEYS`.
4. Copy `packaging/flockdeck_compat_test.go.txt` to `internal/selfupdate/lens_release_test.go` in the checkout and run `go test ./internal/selfupdate -run 'TestLens' -count=1 -v`.

The Go file has two tests: `TestLensReleaseIsAcceptedByTheUpdaterChecks` (signatures, manifest, pointer) and `TestLensEmbedsTheKeysFlockdeckTrusts` (fails with a message to update the key constants in `packaging/release.py`). A change in Flockdeck's checks fails here before a release that every Flockdeck would refuse. See [release signing](/security/release-signing.md).
