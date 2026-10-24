---
type: Security Boundary
title: Download bucket must not be listable
description: The publish script fails if the public address lists the bucket; only uploaded files are public.
resource: packaging/publish-downloads.sh
tags: [security, release, deploy]
timestamp: 2026-10-19T00:00:00Z
code_paths: [packaging/publish-downloads.sh]
---
Each file is uploaded `public-read`, but the bucket itself is meant to be private. After uploading, the script requests `<LENS_DL_URL>/` and `<LENS_DL_URL>/lens/`; if either answers successfully it exits with an error saying the bucket lists to anyone. `LENS_ALLOW_LISTABLE=1` skips this for local test stores ([LENS_ALLOW_LISTABLE](../config/lens-allow-listable.md)). See [publish-downloads](../release/publish-downloads.md).
