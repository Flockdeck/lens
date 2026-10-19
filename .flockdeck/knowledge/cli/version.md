---
type: CLI Command
title: lens version
description: Prints the program version and exits.
resource: src/lens/cli.py
tags: [cli]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/cli.py, src/lens/_version.py]
---
`lens version` prints `app_version()` from `src/lens/_version.py`. Release builds overwrite that value from the tag ([version stamping](../release/version-stamp.md)), and CI checks the built binary reports the stamped value.
