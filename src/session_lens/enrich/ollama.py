"""Enricher backed by a LOCAL Ollama server. Nothing leaves the machine.

The base URL must point at this machine (loopback, or host.docker.internal from a container);
anything else is refused when the enricher is built, so a mistyped setting cannot send a
digest to another host. The HTTP client ignores proxy environment variables and does not
follow redirects for the same reason.
"""

import logging
from typing import Any
from urllib.parse import urlparse

import httpx
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
LOCAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "host.docker.internal"})


def require_local_url(url: str) -> str:
    """Return `url` without a trailing slash, or raise ValueError if it is not local."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.hostname is None:
        raise ValueError("OLLAMA_URL must be an http(s) URL")
    if parsed.hostname.lower() not in LOCAL_HOSTS:
        raise ValueError(
            "OLLAMA_URL must point at this machine (127.0.0.1, ::1, localhost or "
            "host.docker.internal); session-lens never sends recordings to another host"
        )
    return url.rstrip("/")


class OllamaEnricher:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 120.0,
        max_output_attempts: int = 3,
        max_tokens: int = MAX_OUTPUT_TOKENS,
    ) -> None:
        self._base_url = require_local_url(base_url)
        self._model = model
        self._max_attempts = max_output_attempts
        self._max_tokens = max_tokens
        # trust_env=False: never route through a proxy named in the environment.
        self._client = client or httpx.AsyncClient(
            timeout=timeout_seconds, trust_env=False, follow_redirects=False
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "OllamaEnricher":
        return cls(
            settings.ollama_url,
            settings.ollama_model,
            timeout_seconds=settings.ollama_timeout_seconds,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

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
                body = await self._call(user_message, max_tokens)
            except EnrichmentError as exc:
                exc.input_tokens, exc.output_tokens = input_tokens, output_tokens
                raise
            input_tokens += int(body.get("prompt_eval_count") or 0)
            output_tokens += int(body.get("eval_count") or 0)

            if body.get("done_reason") == "length":
                # The same request would be cut off again: retry once with more room, then stop.
                if grew:
                    raise fail(f"output truncated at num_predict={max_tokens}")
                grew = True
                max_tokens *= 2
                log.warning("output hit num_predict, retrying with num_predict=%d", max_tokens)
                continue

            text = (body.get("message") or {}).get("content") or ""
            try:
                parsed = LLMEnrichment.model_validate_json(text)
                break
            except ValidationError as exc:
                # Counts only: validation details can echo model output.
                log.warning(
                    "malformed enrichment output attempt=%d/%d errors=%d",
                    attempt,
                    self._max_attempts,
                    exc.error_count(),
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

    async def _call(self, user_message: str, max_tokens: int) -> dict[str, Any]:
        payload = {
            "model": self._model,
            "stream": False,
            "format": output_schema(),
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "options": {"temperature": 0, "num_predict": max_tokens},
        }
        try:
            response = await self._client.post(f"{self._base_url}/api/chat", json=payload)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            # Ollama not running yet, or still loading the model: worth retrying later.
            raise EnrichmentError(
                f"{type(exc).__name__} talking to Ollama", retryable=True
            ) from None
        if response.status_code == 404:
            raise EnrichmentError(
                f"Ollama has no model {self._model!r}; run `ollama pull {self._model}`",
                retryable=False,
            )
        if response.status_code >= 400:
            retryable = response.status_code >= 500 or response.status_code in (408, 429)
            raise EnrichmentError(
                f"Ollama error status={response.status_code}", retryable=retryable
            )
        try:
            body = response.json()
        except ValueError:
            raise EnrichmentError("Ollama returned a non-JSON response", retryable=False) from None
        if not isinstance(body, dict):
            raise EnrichmentError("Ollama returned an unexpected response", retryable=False)
        return body
