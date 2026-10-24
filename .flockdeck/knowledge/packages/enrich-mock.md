---
type: Module
title: Mock enricher
description: Deterministic heuristic enricher over the computed metrics; the default; needs no key and sends nothing.
resource: src/lens/enrich/mock.py
tags: [enrichment, mock]
timestamp: 2026-10-19T00:00:00Z
code_paths: [src/lens/enrich/mock.py]
---
Result `model` is `mock` and `prompt_version` is `mock-1`; tokens are 0 and `model_fit` is `unclear`.

- Category: from edited files. All docs-like extensions give `docs`; all paths containing `test` give `tests`; all config-like files give `ops`; a test command plus a test file edit gives `bugfix`; any other edit `feature`; no edits but tool calls `exploration`; otherwise `other`.
- Rates: error rate (errors / calls, calls at least 1), interrupt rate, denial rate (denied / permission prompts).
- Frustration: `min(1, 0.6*error + 0.8*interrupt + 0.4*denial)` rounded to 2 places.
- Outcome: `abandoned` if no tool calls or completeness `cut_off`; `stuck` if error rate >= 0.4 or denial rate >= 0.5; else `done`.
- Stuck points when error rate >= 0.3 or denial rate >= 0.5; prompt feedback when error rate >= 0.3.
- One risk note per risky action, naming rule, severity and tool.
