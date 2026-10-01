"""The UI follows Flockdeck's colour design: its tokens, and its rule that colour is never alone."""

import os
import pathlib
import re

import pytest

WEB = pathlib.Path(__file__).resolve().parents[2] / "src" / "session_lens" / "web"
# Set FLOCKDECK_DESIGN_DIR to the Flockdeck repository's design/ folder to compare the copy to it.
FLOCKDECK_COLOR = pathlib.Path(os.environ.get("FLOCKDECK_DESIGN_DIR", "/nonexistent")) / "color.css"

CSS = (WEB / "css" / "app.css").read_text(encoding="utf-8")
TOKENS = (WEB / "css" / "flockdeck-color.css").read_text(encoding="utf-8")
UI_JS = (WEB / "js" / "ui.js").read_text(encoding="utf-8")
INDEX = (WEB / "index.html").read_text(encoding="utf-8")


def test_tokens_load_before_the_app_stylesheet() -> None:
    assert INDEX.index("css/flockdeck-color.css") < INDEX.index("css/app.css")


def test_tokens_define_the_flockdeck_palette_in_both_themes() -> None:
    for name in ("--c-surface", "--c-accent", "--c-ok", "--c-warn", "--c-err", "--c-border-strong"):
        assert name in TOKENS
    assert "#0B6E77" in TOKENS and "#4FD1DB" in TOKENS  # the one accent, light and dark
    assert '[data-theme="dark"]' in TOKENS and "prefers-color-scheme: dark" in TOKENS


@pytest.mark.skipif(not FLOCKDECK_COLOR.exists(), reason="FLOCKDECK_DESIGN_DIR is not set")
def test_tokens_match_flockdeck_source() -> None:
    assert TOKENS.endswith(FLOCKDECK_COLOR.read_text(encoding="utf-8"))


def test_app_stylesheet_has_no_colour_literals_except_neutral_shadows() -> None:
    literals = re.findall(r"#[0-9a-fA-F]{3,8}\b", CSS)
    assert literals == []
    assert re.findall(r"rgb\([^)]*\)", CSS) == ["rgb(0 0 0 / .2)", "rgb(0 0 0 / .45)"]


def test_every_status_hue_has_a_glyph() -> None:
    """Colour is the third channel: each badge that gets a status hue also gets a glyph."""
    coloured: set[str] = set()
    hues = ("var(--good", "var(--warn", "var(--bad", "var(--accent")
    for selectors, body in re.findall(r"((?:\.badge-[\w-]+(?:,\s*)?)+)\s*\{([^}]*)\}", CSS):
        if any(h in body for h in hues):
            coloured.update(re.findall(r"\.badge-([\w-]+)", selectors))
    glyphs = set(re.findall(r'"?([\w-]+)"?:\s*"\\u[0-9A-Fa-f]{4}"', UI_JS))
    assert coloured, "no coloured badges found; the test pattern is stale"
    assert coloured <= glyphs, f"coloured without a glyph: {sorted(coloured - glyphs)}"


def test_running_is_accent_never_green() -> None:
    assert re.search(r"\.badge-running\s*\{[^}]*var\(--accent", CSS)
    assert re.search(r"\.seg-running\s*\{[^}]*var\(--accent", CSS)
    assert not re.search(r"\.badge-running\s*\{[^}]*var\(--good", CSS)


def test_chart_series_do_not_use_status_colours() -> None:
    series = r"\.(?:chart \.(?:dot\.)?line-[ab]|swatch\.line-[ab])[^{]*\{[^}]*\}"
    for rule in re.findall(series, CSS):
        assert "--bad" not in rule and "--good" not in rule and "--warn" not in rule


def test_operable_controls_use_the_strong_border() -> None:
    assert re.search(r"\.btn\s*\{[^}]*border:\s*1px solid var\(--border-strong\)", CSS)
    assert re.search(r"select\s*\{[^}]*border:\s*1px solid var\(--border-strong\)", CSS)


def test_flockdeck_mark_is_in_the_header_and_the_favicon() -> None:
    mark = WEB / "img" / "flockdeck-mark.svg"
    assert mark.exists()
    assert 'class="brand-mark"' in INDEX and "img/flockdeck-mark.svg" in INDEX
    assert re.search(r'rel="icon"[^>]*flockdeck-mark\.svg', INDEX)
    assert 'aria-label="flockdeck"' in mark.read_text(encoding="utf-8")


@pytest.mark.skipif(not FLOCKDECK_COLOR.exists(), reason="FLOCKDECK_DESIGN_DIR is not set")
def test_mark_matches_flockdeck_source() -> None:
    source = FLOCKDECK_COLOR.parent.parent / "cmd" / "sitegen" / "assets" / "favicon.svg"
    if source.exists():
        assert (WEB / "img" / "flockdeck-mark.svg").read_bytes() == source.read_bytes()
