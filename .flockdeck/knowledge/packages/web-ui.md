---
type: Module
title: Web UI
description: Static single-page UI served from the package; hash routes for submit, batches, sessions, insights and settings.
resource: src/lens/web/index.html
tags: [web, ui]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/web/index.html, src/lens/web/js/main.js, src/lens/web/js/ui.js, src/lens/web/js/config.js, src/lens/web/js/charts.js, src/lens/web/css/app.css, src/lens/web/css/flockdeck.css]
---
Plain ES modules and CSS, no build step, served by `WebFiles` ([API app](/packages/api-app.md)) at `/`. Dark only (`color-scheme: dark`, no light variant). Fonts (Archivo and JetBrains Mono, SIL OFL) are served from the same origin so a page view contacts nobody. `<meta name="referrer" content="no-referrer">` is set.

`js/main.js` routes on `location.hash`: `#/submit` (default), `#/batches/<id>`, `#/sessions`, `#/sessions/<id>`, `#/insights`, `#/settings`. Each view module exports `render(root, {parts, query})` and may return a cleanup function; a newer navigation cancels an older render (render counter). Document title becomes `<View> - lens`. A footer status bar shows [status line text](/packages/web-lib.md) derived from `GET /config`.

`js/ui.js` is a small DOM helper (`h`, `clear`, toasts, dialogs, `info` help buttons from the glossary). Everything is inserted through `createElement` and `textContent`, never `innerHTML` ([untrusted content](/security/web-untrusted-content.md)). `js/charts.js` draws SVG charts with colours from CSS classes. `js/config.js` caches `GET /config` and retries after a failure on the next navigation.

All network calls go through [the API client](/packages/web-api-client.md); views are in [views](/packages/web-views.md).
