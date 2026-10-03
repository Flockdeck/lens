"""Deterministic heuristic enricher over the computed metrics. Needs no API key."""

from typing import Any

from session_lens.enrich.base import EnrichmentResult, RiskNote, StuckPoint
from session_lens.recording.models import Analysis

MOCK_MODEL = "mock"
MOCK_PROMPT_VERSION = "mock-1"


def _num(obj: Any, name: str) -> float:
    """Read a numeric field from a model or a dict (permission may be either)."""
    value = obj.get(name, 0) if isinstance(obj, dict) else getattr(obj, name, 0)
    return float(value or 0)


def _category(analysis: Analysis) -> str:
    edited = [p.lower() for p in analysis.files_touched.edited]
    commands = " ".join(analysis.files_touched.commands).lower()
    if edited:
        if all(p.endswith((".md", ".rst", ".txt")) for p in edited):
            return "docs"
        if all("test" in p for p in edited):
            return "tests"
        if all(p.endswith((".yaml", ".yml", ".toml", ".tf", "dockerfile")) for p in edited):
            return "ops"
        if any(w in commands for w in ("pytest", "test")) and any("test" in p for p in edited):
            return "bugfix"
        return "feature"
    if analysis.metrics.tool_calls > 0:
        return "exploration"
    return "other"


def _rates(analysis: Analysis) -> tuple[float, float, float]:
    m = analysis.metrics
    calls = max(m.tool_calls, 1)
    error_rate = m.tool_errors / calls
    interrupt_rate = m.tool_interrupted / calls
    prompts = _num(m.permission, "prompts")
    denial_rate = _num(m.permission, "denied") / prompts if prompts else 0.0
    return error_rate, interrupt_rate, denial_rate


class MockEnricher:
    async def enrich(self, analysis: Analysis) -> EnrichmentResult:
        m = analysis.metrics
        error_rate, interrupt_rate, denial_rate = _rates(analysis)
        category = _category(analysis)

        frustration = min(1.0, 0.6 * error_rate + 0.8 * interrupt_rate + 0.4 * denial_rate)
        frustration = round(frustration, 2)

        if m.tool_calls == 0 or analysis.completeness == "cut_off":
            outcome = "abandoned"
        elif error_rate >= 0.4 or denial_rate >= 0.5:
            outcome = "stuck"
        else:
            outcome = "done"

        stuck_points: list[StuckPoint] = []
        if error_rate >= 0.3:
            stuck_points.append(
                StuckPoint(
                    description=f"{m.tool_errors} of {m.tool_calls} tool calls failed.",
                    approx_seq=None,
                )
            )
        if denial_rate >= 0.5:
            stuck_points.append(
                StuckPoint(description="Most permission prompts were denied.", approx_seq=None)
            )

        risk_notes = [
            RiskNote(
                seq=r.seq,
                explanation=f"Flagged by rule {r.rule} ({r.severity}) on tool {r.tool}.",
            )
            for r in analysis.risky_actions
        ]

        summary = (
            f"{category.capitalize()} session: {m.turns} turns and {m.tool_calls} tool calls "
            f"over {round(m.duration_seconds)}s, {m.tool_errors} errors, ended "
            f"{analysis.completeness}."
        )
        feedback = (
            "Many tool calls failed; consider giving the agent more context about the "
            "environment up front."
            if error_rate >= 0.3
            else None
        )

        return EnrichmentResult(
            summary=summary,
            category=category,
            outcome=outcome,
            frustration=frustration,
            stuck_points=stuck_points,
            prompt_feedback=feedback,
            model_fit="unclear",
            model_fit_reason="The mock enricher does not judge model fit.",
            risk_notes=risk_notes,
            input_tokens=0,
            output_tokens=0,
            model=MOCK_MODEL,
            prompt_version=MOCK_PROMPT_VERSION,
        )
