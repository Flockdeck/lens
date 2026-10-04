"""Check the documentation: every Mermaid diagram renders and every relative link resolves.

    python packaging/check_docs.py

Diagrams are rendered by Mermaid itself in a real browser (Playwright), so a typo that GitHub
would show as a red error box fails here instead. Mermaid is loaded from a CDN, so this needs
network access. Exit status 0 means everything is fine.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
MERMAID_JS = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"
FENCE = re.compile(r"^```mermaid\n(.*?)^```", re.S | re.M)
LINK = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
CODE_FENCE = re.compile(r"^```.*?^```", re.S | re.M)


def markdown_files() -> list[Path]:
    skip = {".venv", "node_modules", "dist", "build", ".git"}
    return sorted(p for p in ROOT.rglob("*.md") if not skip.intersection(p.relative_to(ROOT).parts))


def broken_links(path: Path) -> list[str]:
    """Relative links whose target file is missing. URLs and in-page anchors are not checked."""
    text = CODE_FENCE.sub("", path.read_text(encoding="utf-8"))
    problems = []
    for target in LINK.findall(text):
        if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("#"):
            continue
        file_part = target.split("#", 1)[0]
        if file_part and not (path.parent / file_part).exists():
            problems.append(f"{path.relative_to(ROOT)}: link to missing {target}")
    return problems


def render_diagrams(blocks: list[tuple[Path, int, str]]) -> list[str]:
    if not blocks:
        return []
    problems = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="msedge")
        except Exception:
            browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(f'<html><body><script src="{MERMAID_JS}"></script></body></html>')
        page.wait_for_function("window.mermaid !== undefined", timeout=60000)
        page.evaluate("mermaid.initialize({startOnLoad: false, securityLevel: 'strict'})")
        for n, (path, index, source) in enumerate(blocks, 1):
            error = page.evaluate(
                """async ([n, source]) => {
                    try { await mermaid.render('d' + n, source); return null; }
                    catch (e) { return String(e.message || e).slice(0, 300); }
                }""",
                [n, source],
            )
            if error:
                problems.append(
                    f"{path.relative_to(ROOT)}: diagram {index} does not render: {error}"
                )
        browser.close()
    return problems


def main() -> int:
    files = markdown_files()
    blocks: list[tuple[Path, int, str]] = []
    problems: list[str] = []
    for path in files:
        problems += broken_links(path)
        for i, source in enumerate(FENCE.findall(path.read_text(encoding="utf-8")), 1):
            blocks.append((path, i, source))
    problems += render_diagrams(blocks)
    print(f"{len(files)} markdown files, {len(blocks)} diagrams")
    for line in problems:
        print("FAIL", line)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
