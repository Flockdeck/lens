"""The licence and notices that ship with every release."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_the_licence_is_flockdecks_and_names_its_owner() -> None:
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("# PolyForm Noncommercial License 1.0.0\n")
    assert "Required Notice: Copyright Jim Wright (https://flockdeck.ai)" in text
    assert "\r" not in text  # kept byte for byte


def test_the_package_metadata_names_the_same_licence() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'license = "PolyForm-Noncommercial-1.0.0"' in pyproject
    assert '"LICENSE"' in pyproject and '"THIRD-PARTY-NOTICES.md"' in pyproject


def test_the_notices_cover_the_fonts_and_every_bundled_library() -> None:
    text = (ROOT / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8")
    flat = " ".join(text.split())  # the text is wrapped, and a phrase can break across lines
    for needle in ("## Python", "## PyInstaller", "SIL Open Font License", "certifi"):
        assert needle in flat, needle
    listed = {m.group(1).lower() for m in re.finditer(r"^### (\S+) ", text, re.M)}
    for name in (
        "fastapi",
        "sqlalchemy",
        "pydantic",
        "uvicorn",
        "anthropic",
        "aiosqlite",
        "alembic",
    ):
        assert name in listed, name
    assert "ships no licence file" not in text  # every package gave a licence text


def test_the_fonts_travel_with_their_licences() -> None:
    fonts = ROOT / "src" / "lens" / "web" / "fonts"
    assert (fonts / "OFL-Archivo.txt").is_file() and (fonts / "OFL-JetBrainsMono.txt").is_file()


def test_the_readme_is_the_products_not_the_interview_brief() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert readme.startswith("# lens\n")
    assert "Yantra" not in readme and "technical deep dive" not in readme
    assert "](LICENSE)" in readme and "](THIRD-PARTY-NOTICES.md)" in readme


def test_no_tracked_text_mentions_the_interview_it_started_as() -> None:
    skip = {".git", ".venv", "node_modules", "dist", "build"}
    for path in ROOT.rglob("*"):
        if (
            not path.is_file()
            or skip.intersection(path.relative_to(ROOT).parts)
            or path.suffix in {".woff2", ".png", ".svg", ".lock", ".db"}
            or path.name == "test_legal.py"
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        assert "yantra" not in text.lower(), path.relative_to(ROOT)
