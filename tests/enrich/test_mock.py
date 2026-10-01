from collections.abc import Callable
from typing import Any

from session_lens.config import Settings
from session_lens.enrich import build_enricher
from session_lens.enrich.mock import MockEnricher


async def test_deterministic(make_analysis: Callable[..., Any]) -> None:
    a = make_analysis()
    assert await MockEnricher().enrich(a) == await MockEnricher().enrich(a)


async def test_clean_session_is_done_and_calm(make_analysis: Callable[..., Any]) -> None:
    r = await MockEnricher().enrich(make_analysis())
    assert r.outcome == "done"
    assert r.frustration == 0
    assert r.stuck_points == []
    assert (r.input_tokens, r.output_tokens) == (0, 0)
    assert r.model == "mock"


async def test_many_errors_is_stuck_with_frustration(make_analysis: Callable[..., Any]) -> None:
    a = make_analysis(
        metrics={"tool_calls": 10, "tool_errors": 6, "tool_interrupted": 1, "turns": 4}
    )
    r = await MockEnricher().enrich(a)
    assert r.outcome == "stuck"
    assert 0 < r.frustration <= 1
    assert r.stuck_points


async def test_cut_off_or_no_tools_is_abandoned(make_analysis: Callable[..., Any]) -> None:
    cut = make_analysis(completeness="cut_off")
    assert (await MockEnricher().enrich(cut)).outcome == "abandoned"
    a = make_analysis(metrics={"tool_calls": 0})
    assert (await MockEnricher().enrich(a)).outcome == "abandoned"


async def test_denied_permissions_raise_frustration(make_analysis: Callable[..., Any]) -> None:
    a = make_analysis(metrics={"tool_calls": 4, "permission": {"prompts": 4, "denied": 4}})
    r = await MockEnricher().enrich(a)
    assert r.outcome == "stuck"
    assert r.frustration > 0


async def test_category_from_files(make_analysis: Callable[..., Any]) -> None:
    docs = make_analysis(files_touched={"edited": ["README.md"]})
    tests = make_analysis(files_touched={"edited": ["tests/test_a.py"]})
    code = make_analysis(files_touched={"edited": ["src/a.py"]})
    explore = make_analysis(files_touched={"read": ["src/a.py"]})
    assert (await MockEnricher().enrich(docs)).category == "docs"
    assert (await MockEnricher().enrich(tests)).category == "tests"
    assert (await MockEnricher().enrich(code)).category == "feature"
    assert (await MockEnricher().enrich(explore)).category == "exploration"


async def test_risky_actions_become_risk_notes(make_analysis: Callable[..., Any]) -> None:
    a = make_analysis(
        risky_actions=[
            {"seq": 7, "tool": "Bash", "summary": "rm -rf", "severity": "high", "rule": "rm-rf"}
        ]
    )
    r = await MockEnricher().enrich(a)
    assert [n.seq for n in r.risk_notes] == [7]


def test_build_enricher_mock() -> None:
    assert isinstance(build_enricher(Settings(enricher="mock")), MockEnricher)
