---
type: CI Check
title: release workflow
description: Tag-triggered pipeline that tests, builds, signs, publishes to GitHub and then to the download site.
resource: .github/workflows/release.yaml
tags: [ci, release]
timestamp: 2026-10-19T00:00:00Z
code_paths: [.github/workflows/release.yaml]
---
Triggers: push of a tag `v*`, or manual dispatch with a `tag` input (run from that tag) to finish a release that stopped part way. Pushing the tag is the approval.

Jobs in order:

1. `test`: the whole [ci workflow](/ci/ci-workflow.md).
2. `version`: the tag must match `^v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$`. Unless it contains `-rc.`, `docs/releases/<tag>.md` must exist.
3. `build`: the [build workflow](/ci/build-workflow.md) with the tag and 30-day retention.
4. `release` (environment `release`, concurrency group `release` without cancel, `contents: write`):
   - download only `lens_<tag>_*` artifacts (CI uploads `lens_v0.0.0-ci_*` archives to the same run and they must not be signed);
   - `release.py sums`, then `sign` and `verify` ([release script](/tools/release-script.md));
   - publish on GitHub first, deliberately: a pre-release (any tag containing `-`) is marked as one and never latest; a release older than the current latest gets `--latest=false` (repeated through the API and restored if it moved); an existing release gets its files uploaded with `--clobber`; notes come from `docs/releases/<tag>.md` if present, else generated; `latest.json` is not attached; if GitHub cannot be asked, nothing is published;
   - check the four `DO_SPACES_*` secrets are set and name all missing ones;
   - run [publish-downloads.sh](/release/publish-downloads.md), read from the workflow's own commit.

Secrets handling: [workflow secrets](/security/workflow-secrets.md).
