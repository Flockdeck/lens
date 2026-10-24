---
type: Developer Tool
title: flockdeck_compat_test.go.txt
description: A Go test file kept as text and copied into a Flockdeck checkout by CI.
resource: packaging/flockdeck_compat_test.go.txt
tags: [tools, release, go]
timestamp: 2026-10-19T00:00:00Z
code_paths: [packaging/flockdeck_compat_test.go.txt]
---
Not built in this repository (the `.txt` suffix keeps it out of Go tooling). In CI it becomes `internal/selfupdate/lens_release_test.go` in a checkout of Flockdeck and runs against `LENS_RELEASE_DIR` with `LENS_TEST_PUBKEY` and `LENS_TRUSTED_KEYS`. Tests: `TestLensReleaseIsAcceptedByTheUpdaterChecks` and `TestLensEmbedsTheKeysFlockdeckTrusts`. See [flockdeck-compat job](../ci/flockdeck-compat.md).
