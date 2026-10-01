"""Enricher backed by the Anthropic Messages API with schema-constrained JSON output."""

import logging
from typing import Any

import anthropic
from pydantic import ValidationError

from session_lens.config import Settings
from session_lens.enrich.base import EnrichmentError, EnrichmentResult, RiskNote, StuckPoint
from session_lens.enrich.prompt import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    LLMEnrichment,
    build_user_message,
    output_schema,
)
from session_lens.recording.models import Analysis

log = logging.getLogger(__name__)

MAX_OUTPUT_TOKENS = 4096


class AnthropicEnricher:
    def __init__(
        self,
        client: Any,
        model: str,
        *,
        max_output_attempts: int = 3,
        max_tokens: int = MAX_OUTPUT_TOKENS,
    ) -> None:
        # `client` is an anthropic.AsyncAnthropic (or a test fake with the same
        # `messages.create` coroutine).
        self._client = client
        self._model = model
        self._max_attempts = max_output_attempts
        self._max_tokens = max_tokens

    @classmethod
    def from_settings(cls, settings: Settings) -> "AnthropicEnricher":
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required when ENRICHER=anthropic")
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        return cls(client, settings.anthropic_model)

    async def enrich(self, analysis: Analysis) -> EnrichmentResult:
        user_message = build_user_message(analysis)
        input_tokens = 0
        output_tokens = 0
        parsed: LLMEnrichment | None = None

        for attempt in range(1, self._max_attempts + 1):
            message = await self._call(user_message)
            input_tokens += message.usage.input_tokens
            output_tokens += message.usage.output_tokens

            if message.stop_reason == "refusal":
                raise EnrichmentError("model refused to enrich the session", retryable=False)

            text = "".join(b.text for b in message.content if b.type == "text")
            try:
                parsed = LLMEnrichment.model_validate_json(text)
                break
            except ValidationError as exc:
                # Log counts and the stop reason only: error details can echo model output.
                log.warning(
                    "malformed enrichment output attempt=%d/%d errors=%d stop_reason=%s",
                    attempt,
                    self._max_attempts,
                    exc.error_count(),
                    message.stop_reason,
                )

        if parsed is None:
            raise EnrichmentError(
                f"model returned malformed output {self._max_attempts} times", retryable=False
            )

        return EnrichmentResult(
            summary=parsed.summary,
            category=parsed.category,
            outcome=parsed.outcome,
            frustration=parsed.frustration,
            stuck_points=[
                StuckPoint(description=s.description, approx_seq=s.approx_seq)
                for s in parsed.stuck_points
            ],
            prompt_feedback=parsed.prompt_feedback,
            risk_notes=[RiskNote(seq=r.seq, explanation=r.explanation) for r in parsed.risk_notes],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self._model,
            prompt_version=PROMPT_VERSION,
        )

    async def _call(self, user_message: str) -> Any:
        try:
            return await self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
                output_config={"format": {"type": "json_schema", "schema": output_schema()}},
            )
        except (anthropic.RateLimitError, anthropic.APIConnectionError) as exc:
            # APITimeoutError is an APIConnectionError.
            raise EnrichmentError(f"{type(exc).__name__} from Anthropic", retryable=True) from exc
        except anthropic.APIStatusError as exc:
            retryable = exc.status_code >= 500 or exc.status_code in (408, 409, 529)
            raise EnrichmentError(
                f"Anthropic API error status={exc.status_code}", retryable=retryable
            ) from exc
