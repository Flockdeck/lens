---
type: Build Step
title: Release archives
description: Each platform build produces lens_<tag>_<os>_<arch>.tar.gz or .zip holding the binary and legal files.
resource: .github/workflows/build.yaml
tags: [build, release, packaging]
timestamp: 2026-10-19T00:00:00Z
code_paths: [.github/workflows/build.yaml, packaging/release.py]
---
Name: `lens_<tag>_<goos>_<goarch>.<ext>` with `tar.gz` for Linux and macOS and `zip` (made with `7z`) for Windows. Platforms (`release.PLATFORMS`): linux amd64 and arm64, darwin amd64 and arm64, windows amd64 and arm64.

Contents of the folder `lens_<tag>_<os>_<arch>/`: the executable (`lens` or `lens.exe`), `README.md`, `LICENSE`, `THIRD-PARTY-NOTICES.md`. On Unix the binary gets mode +x. The archive is uploaded as an artifact with the same name; `if-no-files-found: error`, retention 3 days by default and 30 days from the release workflow.

`release.py sums` then lists every archive in `checksums.txt` ([checksums](../tables/release-checksums.md)).
