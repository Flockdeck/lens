"""Enricher backed by the Anthropic Messages API with schema-constrained JSON output.

Opt-in and remote: it is used only when ENRICHER=anthropic and ANTHROPIC_API_KEY are set. The
default (mock) and the local Ollama enricher send nothing anywhere."""

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
    supplied_seqs,
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
        key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else ""
        if not key.strip():
            raise ValueError("ANTHROPIC_API_KEY is required when ENRICHER=anthropic")
        # The one place anything leaves this machine, and only when ENRICHER=anthropic is chosen
        # on purpose: the bounded digest (prompts, final messages, trimmed failures, metrics),
        # never the raw recording. The log line says so once, and carries no content.
        log.warning(
            "ENRICHER=anthropic: session digests are sent to the Anthropic API",
            extra={"model": settings.anthropic_model},
        )
        return cls(anthropic.AsyncAnthropic(api_key=key), settings.anthropic_model)

    async def enrich(self, analysis: Analysis) -> EnrichmentResult:
        user_message = build_user_message(analysis)
        allowed_seqs = supplied_seqs(analysis)
        input_tokens = 0
        output_tokens = 0
        max_tokens = self._max_tokens
        grew = False
        parsed: LLMEnrichment | None = None

        def fail(message: str, *, retryable: bool = False) -> EnrichmentError:
            return EnrichmentError(
                message,
                retryable=retryable,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        for attempt in range(1, self._max_attempts + 1):
            try:
                message = await self._call(user_message, max_tokens)
            except EnrichmentError as exc:
                # Carry what earlier attempts already spent.
                exc.input_tokens, exc.output_tokens = input_tokens, output_tokens
                raise
            input_tokens += message.usage.input_tokens
            output_tokens += message.usage.output_tokens

            if message.stop_reason == "refusal":
                raise fail("model refused to enrich the session")
            if message.stop_reason == "max_tokens":
                # The same request would be cut off again: retry once with more room, then stop.
                if grew:
                    raise fail(f"output truncated at max_tokens={max_tokens}")
                grew = True
                max_tokens *= 2
                log.warning("output hit max_tokens, retrying with max_tokens=%d", max_tokens)
                continue

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
            raise fail(f"model returned no valid output in {self._max_attempts} attempts")

        # The model may only refer to seqs it was given; drop or null anything else.
        return EnrichmentResult(
            summary=parsed.summary,
            category=parsed.category,
            outcome=parsed.outcome,
            frustration=parsed.frustration,
            stuck_points=[
                StuckPoint(
                    description=s.description,
                    approx_seq=s.approx_seq if s.approx_seq in allowed_seqs else None,
                )
                for s in parsed.stuck_points
            ],
            prompt_feedback=parsed.prompt_feedback,
            model_fit=parsed.model_fit,
            model_fit_reason=parsed.model_fit_reason,
            risk_notes=[
                RiskNote(seq=r.seq, explanation=r.explanation)
                for r in parsed.risk_notes
                if r.seq in allowed_seqs
            ],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self._model,
            prompt_version=PROMPT_VERSION,
        )

    async def _call(self, user_message: str, max_tokens: int) -> Any:
        try:
            return await self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
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
