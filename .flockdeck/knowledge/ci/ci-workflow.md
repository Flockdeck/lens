---
type: CI Check
title: ci workflow
description: Checks that must pass before a merge or release, covering static checks, docs, tests, audit, Flockdeck compatibility and binaries.
resource: .github/workflows/ci.yaml
tags: [ci]
timestamp: 2026-10-19T00:00:00Z
code_paths: [.github/workflows/ci.yaml]
---
Triggers: push to `main`, pull requests, `workflow_call` (from the release workflow), manual dispatch, and a weekly schedule (Mondays 05:17 UTC) to catch changed dependencies or advisories. Permissions `contents: read`. Concurrency group per workflow and ref; in-progress runs are cancelled only for pull requests.

Jobs: [static](static-checks.md), [docs](docs-check.md), [test](test-matrix.md), [audit](dependency-audit.md), [flockdeck-compat](flockdeck-compat.md), `binaries` (calls the [build workflow](build-workflow.md) with tag `v0.0.0-ci`), and `ci-ok`, which depends on all of them, runs `if: always()` and fails unless every result is `success`. It is the single name to require in branch protection. Tool setup uses `astral-sh/setup-uv` and `uv python install 3.12`, then `uv sync --frozen`.
