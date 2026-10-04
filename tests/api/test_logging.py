from __future__ import annotations

import sys
from pathlib import Path

import pytest

from lens.api.logging import log_destination


def test_a_dash_means_standard_output(tmp_path: Path) -> None:
    assert log_destination("-", str(tmp_path)) is None


def test_an_explicit_file_is_used(tmp_path: Path) -> None:
    assert log_destination(str(tmp_path / "x.log"), "ignored") == tmp_path / "x.log"


def test_without_a_terminal_logs_go_to_a_file_in_the_data_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False, raising=False)
    assert log_destination("", str(tmp_path)) == tmp_path / "lens.log"


def test_in_a_terminal_logs_go_to_the_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
    assert log_destination("", str(tmp_path)) is None
