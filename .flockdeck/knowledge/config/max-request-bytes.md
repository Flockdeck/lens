---
type: Environment Variable
title: MAX_REQUEST_BYTES
description: Largest total upload body, in bytes.
resource: src/lens/config.py
tags: [config, env]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py]
---
Default: 268435456 (256 MiB).

Read by `Settings` ([settings class](../packages/config-settings.md)) from the environment or the `.env` file.

Enforced on streamed bytes by [BodySizeLimit](../packages/api-limits.md) (413) and again on the sum of accepted file sizes (extra files rejected with `request size limit exceeded`).
