---
type: Environment Variable
title: ANTHROPIC_WORKSPACE_ID
description: Workspace id sent as a header, only for a key that is not scoped to one workspace.
resource: src/lens/config.py
tags: [config, env]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/config.py]
---
Default: none.

Read by `Settings` ([settings class](/packages/config-settings.md)) from the environment or the `.env` file.

When non-blank it is sent as the `anthropic-workspace-id` header by [AnthropicEnricher](/packages/enrich-anthropic.md). It may not contain whitespace when set through [PUT /settings](/api/settings-put.md).
