---
type: Environment Variable
title: ALLOWED_HOSTS
description: Host names this machine answers to; any other Host header is refused with 421.
resource: src/lens/config.py
tags: [config, env]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py]
---
Default: `127.0.0.1`, `localhost`, `::1`.

Read by `Settings` ([settings class](/packages/config-settings.md)) from the environment or the `.env` file.

Accepted forms: one name, names separated by commas or spaces, or a JSON list (`127.0.0.1,localhost`, `["127.0.0.1", "localhost"]`). The field is declared `NoDecode` and parsed by a validator because the Flockdeck app passes a plain name, which pydantic would otherwise reject as invalid JSON. A value starting with `[` that is not valid JSON, such as `[::1]`, is treated as an IPv6 name. Ports are ignored in comparisons and brackets are stripped. Enforced by [LocalOnly](/packages/api-local.md); the same names bound the Origin check. See [local-only guard](/security/local-only-guard.md). The smoke test launches with `ALLOWED_HOSTS=127.0.0.1` and expects `Host: localhost` to get 421.
