import json
import logging
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest

from session_lens.config import Settings
from session_lens.enrich import EnrichmentError, build_enricher
from session_lens.enrich.anthropic import AnthropicEnricher
from session_lens.enrich.prompt import PROMPT_VERSION, build_user_message

GOOD: dict[str, Any] = {
    "summary": "Fixed a bug.",
    "category": "bugfix",
    "outcome": "done",
    "frustration": 1.7,  # out of range, must be clamped
    "stuck_points": [{"description": "flaky test", "approx_seq": 12}],
    "prompt_feedback": None,
    "risk_notes": [{"seq": 3, "explanation": "force push to a scratch branch"}],
}


def reply(text: str, *, stop: str = "end_turn", i: int = 100, o: int = 20) -> Any:
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop,
        usage=SimpleNamespace(input_tokens=i, output_tokens=o),
    )


class FakeClient:
    """Plays back replies (or raises exceptions) in order, recording each request."""

    def __init__(self, *script: Any) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []
        self.messages = self

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _response(status: int) -> httpx2.Response:
    return httpx2.Response(status, request=httpx2.Request("POST", "https://api.invalid"))


async def test_happy_path(make_analysis: Callable[..., Any]) -> None:
    client = FakeClient(reply(json.dumps(GOOD)))
    result = await AnthropicEnricher(client, "claude-haiku-4-5").enrich(make_analysis())

    assert result.summary == "Fixed a bug."
    assert result.frustration == 1.0
    assert result.stuck_points[0].approx_seq == 12
    assert result.risk_notes[0].seq == 3
    assert (result.input_tokens, result.output_tokens) == (100, 20)
    assert result.model == "claude-haiku-4-5"
    assert result.prompt_version == PROMPT_VERSION

    call = client.calls[0]
    assert call["model"] == "claude-haiku-4-5"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert "SECRET-PROMPT" in call["messages"][0]["content"]


async def test_malformed_then_valid_retries_and_sums_tokens(
    make_analysis: Callable[..., Any],
) -> None:
    client = FakeClient(reply("not json", i=10, o=1), reply(json.dumps(GOOD), i=10, o=5))
    result = await AnthropicEnricher(client, "m").enrich(make_analysis())
    assert len(client.calls) == 2
    assert (result.input_tokens, result.output_tokens) == (20, 6)


async def test_schema_violation_counts_as_malformed(make_analysis: Callable[..., Any]) -> None:
    bad = {**GOOD, "outcome": "great"}
    client = FakeClient(reply(json.dumps(bad)), reply(json.dumps(GOOD)))
    await AnthropicEnricher(client, "m").enrich(make_analysis())
    assert len(client.calls) == 2


async def test_malformed_after_bounded_retries_is_permanent(
    make_analysis: Callable[..., Any],
) -> None:
    client = FakeClient(*[reply("nope") for _ in range(3)])
    with pytest.raises(EnrichmentError) as exc:
        await AnthropicEnricher(client, "m", max_output_attempts=3).enrich(make_analysis())
    assert exc.value.retryable is False
    assert len(client.calls) == 3


async def test_refusal_is_permanent_and_not_retried(make_analysis: Callable[..., Any]) -> None:
    client = FakeClient(reply("", stop="refusal"))
    with pytest.raises(EnrichmentError) as exc:
        await AnthropicEnricher(client, "m").enrich(make_analysis())
    assert exc.value.retryable is False
    assert len(client.calls) == 1


@pytest.mark.parametrize(
    ("error", "retryable"),
    [
        (anthropic.RateLimitError("x", response=_response(429), body=None), True),
        (anthropic.APITimeoutError(request=httpx2.Request("POST", "https://api.invalid")), True),
        (
            anthropic.APIConnectionError(
                message="x", request=httpx2.Request("POST", "https://api.invalid")
            ),
            True,
        ),
        (anthropic.InternalServerError("x", response=_response(500), body=None), True),
        (anthropic.BadRequestError("x", response=_response(400), body=None), False),
        (anthropic.AuthenticationError("x", response=_response(401), body=None), False),
    ],
)
async def test_api_errors_are_mapped(
    make_analysis: Callable[..., Any], error: Exception, retryable: bool
) -> None:
    client = FakeClient(error)
    with pytest.raises(EnrichmentError) as exc:
        await AnthropicEnricher(client, "m").enrich(make_analysis())
    assert exc.value.retryable is retryable
    assert len(client.calls) == 1


async def test_content_never_logged_or_in_errors(
    make_analysis: Callable[..., Any], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    client = FakeClient(*[reply('{"summary": "SECRET-OUT"}') for _ in range(3)])
    with pytest.raises(EnrichmentError) as exc:
        await AnthropicEnricher(client, "m").enrich(make_analysis())
    assert "SECRET" not in str(exc.value)
    assert "SECRET" not in caplog.text


def test_user_message_is_digest_and_facts_only(make_analysis: Callable[..., Any]) -> None:
    msg = build_user_message(make_analysis())
    assert "<facts>" in msg and "<digest>" in msg
    assert "recording_session" not in msg


def test_build_enricher_anthropic_requires_key() -> None:
    with pytest.raises(ValueError):
        build_enricher(Settings(enricher="anthropic", anthropic_api_key=None))
    e = build_enricher(Settings(enricher="anthropic", anthropic_api_key="k"))
    assert isinstance(e, AnthropicEnricher)
