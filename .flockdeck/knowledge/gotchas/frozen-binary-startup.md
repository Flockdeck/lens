---
type: Gotcha
title: Frozen binary specifics
description: freeze_support, an unpacked launcher, a data-directory path with a space, and files read from the bundle.
resource: src/lens/__main__.py
tags: [pyinstaller, windows]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/__main__.py, packaging/lens.spec, src/lens/db/migrate.py, packaging/smoke.py]
---
- `__main__.py` calls `multiprocessing.freeze_support()`, which only matters for a frozen Windows build.
- The web UI and the Alembic scripts are included as data files because StaticFiles and Alembic read them from disk ([spec](../release/pyinstaller-spec.md)); `MIGRATIONS` is resolved relative to the package.
- `upx=False` in the spec: UPX-packed binaries trip antivirus software.
- The smoke test uses a data directory with a space in it ("as real ones have").
- A first run is slower: unpacking the one-file binary plus TLS certificate loading ([enricher thread](enricher-built-off-the-event-loop.md)).
