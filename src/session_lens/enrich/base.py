"""Enricher protocol, result types and the factory that picks an implementation."""

from typing import Literal, Protocol

from pydantic import BaseModel, Field

from session_lens.config import Settings
from session_lens.recording.models import Analysis


class StuckPoint(BaseModel):
    description: str
    approx_seq: int | None = None


class RiskNote(BaseModel):
    seq: int
    explanation: str


class EnrichmentResult(BaseModel):
    summary: str
    category: str  # bugfix|feature|refactor|exploration|docs|tests|ops|other
    outcome: Literal["done", "abandoned", "stuck"]
    frustration: float = Field(ge=0.0, le=1.0)
    stuck_points: list[StuckPoint] = Field(default_factory=list)
    prompt_feedback: str | None = None
    risk_notes: list[RiskNote] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    model: str
    prompt_version: str


class EnrichmentError(Exception):
    """Enrichment failed. `retryable` is True for rate limits, timeouts and 5xx; False for
    permanent failures such as malformed output after bounded retries.

    Messages never include recording content.
    """

    def __init__(
        self, message: str, *, retryable: bool, input_tokens: int = 0, output_tokens: int = 0
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        # Tokens spent on attempts that produced no result, so callers can still account for them.
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class Enricher(Protocol):
    async def enrich(self, analysis: Analysis) -> EnrichmentResult: ...


def build_enricher(settings: Settings) -> Enricher:
    # Imported lazily so the mock path needs no HTTP client at all.
    if settings.enricher == "ollama":
        from session_lens.enrich.ollama import OllamaEnricher

        return OllamaEnricher.from_settings(settings)

    from session_lens.enrich.mock import MockEnricher

    return MockEnricher()
