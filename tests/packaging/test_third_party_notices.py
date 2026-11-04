"""packaging/third_party_notices.py: every distinct licence text of a package is kept."""

from __future__ import annotations

import sys
from pathlib import Path

PACKAGING = Path(__file__).resolve().parents[2] / "packaging"
sys.path.insert(0, str(PACKAGING))

import third_party_notices  # noqa: E402


def test_licence_files_with_the_same_name_in_one_package_are_all_kept(tmp_path: Path) -> None:
    info = tmp_path / "foo-1.0.dist-info"
    (info / "licenses" / "third_party").mkdir(parents=True)
    (info / "METADATA").write_text("Name: foo\nVersion: 1.0\nLicense: MIT\n", encoding="utf-8")
    (info / "licenses" / "LICENSE").write_text("MIT text of foo\n", encoding="utf-8")
    (info / "licenses" / "third_party" / "LICENSE").write_text("BSD text\n", encoding="utf-8")

    found: dict = {}
    third_party_notices.read_target(tmp_path, "linux", found)

    (pkg,) = found.values()
    assert sorted(pkg.texts.values()) == ["BSD text", "MIT text of foo"]
