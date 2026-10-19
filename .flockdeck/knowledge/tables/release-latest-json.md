---
type: File Format
title: latest.json
description: Unsigned pointer naming the latest released version.
resource: packaging/release.py
tags: [release, format]
timestamp: 2026-10-19T00:00:00Z
code_paths: [packaging/release.py, packaging/publish-downloads.sh]
---
Content `{"version":"<tag>"}` with a newline. Unsigned on purpose: it only names a release whose own signed manifest is checked before use. It is not uploaded to the GitHub release (the workflow skips it) and is published last by [publish-downloads](/release/publish-downloads.md), so the switch to a new version is one step.
