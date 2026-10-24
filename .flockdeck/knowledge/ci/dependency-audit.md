---
type: CI Check
title: audit job
description: Runs pip-audit over the runtime dependencies that ship in the binary.
resource: .github/workflows/ci.yaml
tags: [ci, security]
timestamp: 2026-10-19T00:00:00Z
code_paths: [.github/workflows/ci.yaml, uv.lock]
---
`uv export --frozen --no-dev --no-hashes --no-emit-project` writes `runtime-requirements.txt`, then `uvx pip-audit --strict --no-deps --disable-pip -r` it. Dev dependencies are not audited. The weekly schedule of the [ci workflow](ci-workflow.md) exists to catch new advisories.
