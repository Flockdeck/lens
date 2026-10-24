---
type: Environment Variable
title: LENS_SIGNING_KEY
description: Release signing key, read by release.py sign from the environment (a repository secret in the release environment).
resource: packaging/release.py
tags: [config, release, secret]
timestamp: 2026-10-19T00:00:00Z
code_paths: [packaging/release.py, .github/workflows/release.yaml]
---
Holds the Ed25519 private key used to sign `checksums.txt` and `manifest.json`, as a PKCS#8 PEM or a base64 32-byte seed. The value is never printed. `sign` refuses it when empty, unreadable, not Ed25519, or not the public key Flockdeck trusts (primary or standby), unless `--test-key` is given. In the release workflow it comes from `secrets.LENS_SIGNING_KEY` in the `release` environment. See [release signing](../security/release-signing.md) and [release script](../tools/release-script.md).
