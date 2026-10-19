---
type: Gotcha
title: Published versions are immutable and cached for a year
description: publish-downloads refuses to replace a published version with different files and never moves latest backwards.
resource: packaging/publish-downloads.sh
tags: [release, cdn]
timestamp: 2026-10-19T00:00:00Z
code_paths: [packaging/publish-downloads.sh]
---
Files under a version are uploaded with `Cache-Control: public, max-age=31536000, immutable` and nothing is purged. If `checksums.txt` of that version is already in the bucket and differs, the script exits ("tag a new version"). If it is identical, files are re-uploaded but the existing `manifest.json` and signature are kept, since re-signing changes the date and an edge holding the old manifest beside the new signature would fail verification. `latest.json` and `latest/` are cached for 60 seconds and are not moved when a pre-release is published or when `latest.json` already names a newer version. Any failure to read the bucket other than a not-found stops the run instead of being taken for an empty bucket. See [publish-downloads](/release/publish-downloads.md).
