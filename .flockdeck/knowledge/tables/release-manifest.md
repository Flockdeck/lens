---
type: File Format
title: manifest.json
description: Signed release manifest with version, date, notes and every file's URL, SHA-256 and size.
resource: packaging/release.py
tags: [release, format]
timestamp: 2026-10-19T00:00:00Z
code_paths: [packaging/release.py]
---
Keys: `version` (the tag), `date` (UTC, second precision), `notes_url` (the GitHub release page for the tag), optional `notes` (text of the notes file), and `files`: entries `{name, url, sha256, size}` for the six archives plus `checksums.txt` and `checksums.txt.sig`. File URLs are `<base>/<tag>/<name>` where the base defaults to the public download path for lens. Serialised with 2-space indent and a trailing newline; `manifest.json.sig` signs those bytes. Written by `release.py sign` after it has read both signatures back with the public key. Checked by `verify` ([release script](../tools/release-script.md)).
