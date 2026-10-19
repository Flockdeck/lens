---
type: Build Step
title: publish-downloads.sh
description: Uploads a signed release to the download bucket in an order that never names files that are not there yet.
resource: packaging/publish-downloads.sh
tags: [build, deploy, release]
timestamp: 2026-10-19T00:00:00Z
code_paths: [packaging/publish-downloads.sh]
---
Usage: `packaging/publish-downloads.sh <version> [dist]` (POSIX sh; needs `aws` and `curl`). Inputs are the `DO_SPACES_*` variables ([key](../config/do-spaces-key.md), [secret](../config/do-spaces-secret.md), [bucket](../config/do-spaces-bucket.md), [region](../config/do-spaces-region.md), [endpoint](../config/do-spaces-endpoint.md)), [LENS_DL_URL](../config/lens-dl-url.md), [LENS_CHECK_WAIT](../config/lens-check-wait.md) and [LENS_ALLOW_LISTABLE](../config/lens-allow-listable.md). Any S3-compatible store works, so it can be run by hand against a fake store.

Order:

1. Validate the version shape and that every archive matches `checksums.txt`, and that `manifest.json` and `latest.json` name the version.
2. Fetch `lens/<version>/checksums.txt` from the bucket. If it exists and differs, stop; if identical, keep the already published manifest ([immutability](../gotchas/downloads-are-immutable.md)).
3. Upload under `lens/<version>/`: archives, `checksums.txt`, its signature, manifest signature, then `manifest.json` (cache one year, immutable).
4. Read `checksums.txt` back through the public URL (six tries) and check the bucket is not listable ([security](../security/bucket-not-listable.md)).
5. A pre-release stops here.
6. If `lens/latest.json` already names a newer version, stop. The `newer` function compares numerically, so `v1.10.0` is newer than `v1.9.0`.
7. Copy archives to `lens/latest/lens_<os>_<arch>.<ext>` and last upload `lens/latest.json` (cache 60 s).

Aws CLI checksum behaviour is turned off with `when_required` settings because not every S3-compatible store accepts the default checksums. A `fetch` failure other than not-found aborts, so a throttled or unreadable bucket is never mistaken for empty. Called by the [release workflow](../ci/release-workflow.md); linted by shellcheck in [static checks](../ci/static-checks.md).
