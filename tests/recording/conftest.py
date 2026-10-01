import importlib.util
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def fixture() -> Callable[[str], bytes]:
    return lambda name: (FIXTURES / name).read_bytes()


def make_line(seq: int, type_: str, time: str = "10:00:00", **fields: Any) -> dict[str, Any]:
    return {
        "v": 1, "seq": seq, "time": f"2026-10-01T{time}Z", "session": "s", "pane": "p",
        "type": type_, **fields,
    }


def to_bytes(*lines: dict[str, Any]) -> bytes:
    return ("\n".join(json.dumps(ln) for ln in lines) + "\n").encode()


def load_builder() -> Any:
    spec = importlib.util.spec_from_file_location("fixture_build", FIXTURES / "build.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
