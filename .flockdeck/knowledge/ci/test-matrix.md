---
type: CI Check
title: test job
description: Pytest on Linux, Windows and macOS with Python 3.12, plus Linux on 3.13, with a 90 percent coverage floor on one leg.
resource: .github/workflows/ci.yaml
tags: [ci, test]
timestamp: 2026-10-19T00:00:00Z
code_paths: [.github/workflows/ci.yaml, pyproject.toml]
---
Matrix: ubuntu, windows, macOS on 3.12 and ubuntu on 3.13 (`fail-fast: false`). Playwright Chromium is installed for browser tests (with OS libraries on Linux). Command: `pytest -ra --durations=10 --cov=lens --cov-branch ... --junitxml=pytest.xml --cov-fail-under=$COVERAGE_MIN`. `COVERAGE_MIN` is 90 only for Linux 3.12 and 0 elsewhere, because some code runs on one platform only. Results (`pytest.xml`, `coverage.xml`) are uploaded for 7 days. Test layout: [test suite](../tools/test-suite.md). pytest uses `asyncio_mode = auto` and a `browser` marker for tests that need a real browser.
