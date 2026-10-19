---
type: Build Step
title: Third-party notices generation
description: packaging/third_party_notices.py writes THIRD-PARTY-NOTICES.md from the licences of everything that ships in the binary.
resource: packaging/third_party_notices.py
tags: [build, licensing]
timestamp: 2026-10-19T00:00:00Z
code_paths: [packaging/third_party_notices.py, packaging/licenses/python-LICENSE.txt, THIRD-PARTY-NOTICES.md, tests/test_legal.py]
---
`python packaging/third_party_notices.py` writes the file; `--check` exits 1 when the committed file differs (run in [static checks](../ci/static-checks.md)). It runs `uv export --frozen --no-dev` for runtime requirements, then fetches package metadata for three platforms (Windows x86_64, manylinux x86_64, macOS arm64) and lists the union, because the bundle differs by platform (uvloop on Linux and macOS, colorama on Windows). No package is installed or run. It adds the Python licence text and the two font licences from `src/lens/web/fonts/`. Needs `uv` and network access or a warm cache. The file is included in every archive ([archives](release-archives.md)). `tests/test_legal.py` checks that notices cover the fonts and every bundled library and that the licence and package metadata agree.
