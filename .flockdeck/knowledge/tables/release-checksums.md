---
type: File Format
title: checksums.txt
description: Release file listing the SHA-256 and name of every archive, sorted, with a detached signature.
resource: packaging/release.py
tags: [release, format]
timestamp: 2026-10-19T00:00:00Z
code_paths: [packaging/release.py]
---
One line per archive: `<sha256>  <archive name>`, sorted by name, written by `release.py sums` from the `lens_*` `.zip` and `.gz` files in the output directory. Any archive of another tag in the directory is an error. `checksums.txt.sig` is the base64 Ed25519 signature of those exact bytes on one line. Archive names: [release archives](/release/release-archives.md). Signing: [release signing](/security/release-signing.md). Same shape as Flockdeck's own release files.
