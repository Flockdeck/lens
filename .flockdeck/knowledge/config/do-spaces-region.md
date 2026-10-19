---
type: Environment Variable
title: DO_SPACES_REGION
description: Region of the bucket, also used to build the default endpoint.
resource: packaging/publish-downloads.sh
tags: [config, release, secret]
timestamp: 2026-10-19T00:00:00Z
code_paths: [packaging/publish-downloads.sh, .github/workflows/release.yaml]
---
Required by `publish-downloads.sh`: if any of the four `DO_SPACES_*` variables is empty the script names all missing ones and exits ([publish-downloads](/release/publish-downloads.md)). The release workflow checks all four before the publish step and reads them from the `release` environment's secrets. Names only are documented here; values are never in the repository. See [workflow secrets](/security/workflow-secrets.md).
