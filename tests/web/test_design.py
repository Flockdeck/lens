"""The UI wears Flockdeck's look as the flockdeck.ai site and the Flockdeck phone client wear it:
dark only, their fonts and tokens, a glyph and a word on every status,
and colour only for states the app knows."""

import os
import pathlib
import re

import pytest

WEB = pathlib.Path(__file__).resolve().parents[2] / "src" / "lens" / "web"
# Set FLOCKDECK_REMOTE_DIR to a flockdeck-remote checkout to compare the copies with their source.
REMOTE = pathlib.Path(os.environ.get("FLOCKDECK_REMOTE_DIR", "/nonexistent")) / "web" / "app"
needs_remote = pytest.mark.skipif(not REMOTE.exists(), reason="FLOCKDECK_REMOTE_DIR is not set")

CSS = (WEB / "css" / "app.css").read_text(encoding="utf-8")
TOKENS = (WEB / "css" / "flockdeck.css").read_text(encoding="utf-8")
UI_JS = (WEB / "js" / "ui.js").read_text(encoding="utf-8")
INDEX = (WEB / "index.html").read_text(encoding="utf-8")


def root_tokens(css: str) -> dict[str, str]:
    block = css[css.index(":root {") : css.index("}", css.index(":root {"))]
    return dict(re.findall(r"(--[\w-]+):\s*([^;]+);", block))


def test_dark_only_like_the_site_and_the_client() -> None:
    assert '<meta name="color-scheme" content="dark">' in INDEX
    assert "color-scheme: dark" in TOKENS
    assert "prefers-color-scheme" not in TOKENS + CSS
    assert "data-theme" not in TOKENS + CSS + UI_JS
    assert 'id="theme"' not in INDEX and not (WEB / "js" / "theme.js").exists()


def test_tokens_are_the_sites_palette() -> None:
    t = root_tokens(TOKENS)
    assert t["--surface"] == "#0F1418" and t["--raised"] == "#161C21" and t["--sunken"] == "#0A0E11"
    assert t["--accent"] == "#4FD1DB" and t["--on-accent"] == "#0F1418"
    assert (t["--working"], t["--waiting"], t["--exited"]) == ("#64C97F", "#E2B341", "#F0776A")
    assert t["--tap"] == "44px" and t["--radius"] == "10px"


def test_the_fonts_are_served_from_here_and_licensed() -> None:
    for name in (
        "archivo.woff2",
        "jetbrains-mono.woff2",
        "OFL-Archivo.txt",
        "OFL-JetBrainsMono.txt",
    ):
        assert (WEB / "fonts" / name).exists(), name
    assert re.findall(r'url\("([^"]+)"\)', TOKENS) == [
        "../fonts/archivo.woff2",
        "../fonts/jetbrains-mono.woff2",
    ]
    assert "fonts/archivo.woff2" in INDEX and "fonts/jetbrains-mono.woff2" in INDEX
    assert "fonts.googleapis" not in INDEX + TOKENS + CSS


def test_the_page_loads_the_tokens_before_the_app_stylesheet() -> None:
    assert INDEX.index("css/flockdeck.css") < INDEX.index("css/app.css")


def test_app_stylesheet_has_no_colour_literals_beyond_the_clients_own_translucent_bars() -> None:
    assert re.findall(r"#[0-9a-fA-F]{3,8}\b", CSS) == []
    assert sorted(re.findall(r"rgba?\([^)]*\)", CSS)) == sorted(
        [
            "rgba(15,20,24,.84)",
            "rgba(79,209,219,.18)",
            "rgba(15,20,24,.9)",
            "rgb(0 0 0 / .6)",
        ]
    )


def test_every_status_hue_has_a_glyph() -> None:
    """The colour is the third channel: each badge that gets a status hue also gets a glyph."""
    coloured: set[str] = set()
    hues = ("var(--working", "var(--waiting", "var(--exited", "var(--accent")
    for selectors, body in re.findall(r"((?:\.badge-[\w-]+(?:,\s*)?)+)\s*\{([^}]*)\}", CSS):
        if any(h in body for h in hues):
            coloured.update(re.findall(r"\.badge-([\w-]+)", selectors))
    glyphs = set(re.findall(r'"?([\w-]+)"?:\s*"\\u[0-9A-Fa-f]{4}"', UI_JS))
    assert coloured, "no coloured badges found; the test pattern is stale"
    assert coloured - {"queued", "cancelled", "abandoned"} <= glyphs
    assert {"queued", "cancelled", "abandoned"} <= glyphs  # the muted states have glyphs too


def test_running_is_accent_never_green() -> None:
    assert re.search(r"\.badge-running\s*\{[^}]*var\(--accent", CSS)
    assert re.search(r"\.seg-running\s*\{[^}]*var\(--accent", CSS)
    assert not re.search(r"\.badge-running\s*\{[^}]*var\(--working", CSS)


def test_chart_series_do_not_use_status_colours() -> None:
    series = r"\.(?:chart \.(?:dot\.)?line-[ab]|swatch\.line-[ab])[^{]*\{[^}]*\}"
    for rule in re.findall(series, CSS):
        assert not any(c in rule for c in ("--exited", "--working", "--waiting"))


def test_operable_controls_have_the_hard_edge_and_a_tap_sized_target() -> None:
    assert re.search(r"\.btn\s*\{[^}]*border:\s*1px solid var\(--edge-hard\)", CSS)
    assert re.search(r"\.btn\s*\{[^}]*min-height:\s*var\(--tap\)", CSS)
    assert re.search(r"select\s*\{[^}]*border:\s*1px solid var\(--edge-hard\)", CSS)
    assert "font-size: 16px" in CSS  # anything smaller and iOS zooms the page on focus


def test_the_mark_and_favicon_are_in_the_header_and_the_page() -> None:
    assert (WEB / "img" / "mark.svg").exists() and (WEB / "img" / "favicon.svg").exists()
    assert 'class="brand-mark" src="img/mark.svg"' in INDEX
    assert re.search(r'rel="icon"[^>]*img/favicon\.svg', INDEX)


@needs_remote
def test_fonts_and_marks_match_flockdeck_remote() -> None:
    for name in ("archivo.woff2", "jetbrains-mono.woff2"):
        assert (WEB / "fonts" / name).read_bytes() == (REMOTE / "fonts" / name).read_bytes()
    assert (WEB / "img" / "mark.svg").read_bytes() == (REMOTE / "icons" / "mark.svg").read_bytes()
    assert (WEB / "img" / "favicon.svg").read_bytes() == (
        REMOTE / "icons" / "favicon.svg"
    ).read_bytes()


@needs_remote
def test_tokens_match_flockdeck_remote() -> None:
    ours = root_tokens(TOKENS)
    theirs = root_tokens((REMOTE / "app.css").read_text(encoding="utf-8"))
    shared = {k for k in ours if k in theirs and k not in {"--tap"}}
    assert len(shared) > 20
    assert {k: ours[k] for k in shared} == {k: theirs[k] for k in shared}
