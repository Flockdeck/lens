---
type: Security Boundary
title: Web UI treats recording text as untrusted
description: The UI never uses innerHTML; summaries and events are inserted as text nodes.
resource: src/lens/web/js/ui.js
tags: [security, xss, web]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/web/js/ui.js, src/lens/web/index.html, tests/web/helpers.test.mjs]
---
`h()` creates elements with `createElement`, sets attributes individually, and appends text with `document.createTextNode`; style objects are assigned through the CSSOM so a strict CSP would work. The comment in `ui.js` gives the reason: summaries and events come from recordings. `index.html` sets `referrer` to `no-referrer`. Fonts are served locally so viewing the UI contacts no third party.
