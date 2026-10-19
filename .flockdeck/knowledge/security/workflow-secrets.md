---
type: Security Boundary
title: Workflow secrets and permissions
description: Release secrets sit in a protected environment; workflows default to read-only contents permission.
resource: .github/workflows/release.yaml
tags: [security, ci, secrets]
timestamp: 2026-10-19T00:00:00Z
code_paths: [.github/workflows/release.yaml, .github/workflows/ci.yaml, .github/workflows/build.yaml]
---
- All three workflows set `permissions: contents: read`; only the `release` job raises it to `contents: write`.
- The signing key and download-bucket credentials (`LENS_SIGNING_KEY`, `DO_SPACES_KEY`, `DO_SPACES_SECRET`, `DO_SPACES_BUCKET`, `DO_SPACES_REGION`) are read from the `release` environment, not plain repository secrets. The workflow comment says repository secrets would be readable by a run on any branch.
- `actions/checkout` uses `persist-credentials: false` where nothing pushes; `gh` takes its token from `GH_TOKEN`.
- The publish script is read from the workflow's own commit (`git show $GITHUB_SHA:...`), not from the tag, so a re-run of an old tag cannot use an old script.
- The `version` job validates the tag against a strict pattern before anything is built.
- The release job runs one at a time (`concurrency: release`, no cancel).
