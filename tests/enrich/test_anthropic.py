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
from session_lens.enrich.prompt import PROMPT_VERSION

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


RISKY = [{"seq": 3, "tool": "Bash", "summary": "git push -f", "severity": "high", "rule": "force"}]


async def test_happy_path(make_analysis: Callable[..., Any]) -> None:
    client = FakeClient(reply(json.dumps(GOOD)))
    result = await AnthropicEnricher(client, "claude-haiku-4-5").enrich(
        make_analysis(risky_actions=RISKY)
    )

    assert result.summary == "Fixed a bug."
    assert result.frustration == 1.0
    assert result.stuck_points[0].description == "flaky test"
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
        (anthropic.APIStatusError("x", response=_response(529), body=None), True),
        (anthropic.APIStatusError("x", response=_response(408), body=None), True),
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
    assert "SECRET" not in _chain_text(exc.value)
    assert "SECRET" not in caplog.text


def _chain_text(exc: BaseException | None) -> str:
    parts: list[str] = []
    while exc is not None:
        parts.append(f"{type(exc).__name__}: {exc}")
        exc = exc.__cause__ or exc.__context__
    return chr(10).join(parts)


async def test_api_error_chain_has_no_content(make_analysis: Callable[..., Any]) -> None:
    client = FakeClient(
        anthropic.RateLimitError("rate limited", response=_response(429), body=None)
    )
    with pytest.raises(EnrichmentError) as exc:
        await AnthropicEnricher(client, "m").enrich(make_analysis())
    assert exc.value.__cause__ is not None
    assert "SECRET" not in _chain_text(exc.value)


async def test_max_tokens_retries_once_with_more_room_then_fails(
    make_analysis: Callable[..., Any],
) -> None:
    client = FakeClient(reply("{", stop="max_tokens", i=5, o=7), reply("{", stop="max_tokens"))
    with pytest.raises(EnrichmentError) as exc:
        await AnthropicEnricher(client, "m", max_tokens=1000).enrich(make_analysis())
    assert exc.value.retryable is False
    assert "max_tokens" in str(exc.value)
    assert [c["max_tokens"] for c in client.calls] == [1000, 2000]
    assert (exc.value.input_tokens, exc.value.output_tokens) == (105, 27)


async def test_max_tokens_then_valid_succeeds(make_analysis: Callable[..., Any]) -> None:
    client = FakeClient(reply("{", stop="max_tokens"), reply(json.dumps(GOOD)))
    result = await AnthropicEnricher(client, "m", max_tokens=1000).enrich(make_analysis())
    assert result.summary == "Fixed a bug."
    assert client.calls[1]["max_tokens"] == 2000


async def test_failed_attempt_usage_is_carried_on_error(
    make_analysis: Callable[..., Any],
) -> None:
    client = FakeClient(reply("x", i=10, o=1), reply("x", i=10, o=1), reply("x", i=10, o=1))
    with pytest.raises(EnrichmentError) as exc:
        await AnthropicEnricher(client, "m").enrich(make_analysis())
    assert (exc.value.input_tokens, exc.value.output_tokens) == (30, 3)


async def test_unsupplied_seqs_are_dropped(make_analysis: Callable[..., Any]) -> None:
    out = {
        **GOOD,
        "stuck_points": [
            {"description": "a", "approx_seq": 3},
            {"description": "b", "approx_seq": 999},
        ],
        "risk_notes": [
            {"seq": 3, "explanation": "ok"},
            {"seq": 999, "explanation": "invented"},
        ],
    }
    client = FakeClient(reply(json.dumps(out)))
    result = await AnthropicEnricher(client, "m").enrich(make_analysis(risky_actions=RISKY))
    assert [n.seq for n in result.risk_notes] == [3]
    assert [p.approx_seq for p in result.stuck_points] == [3, None]


def test_from_settings_passes_model_through() -> None:
    e = AnthropicEnricher.from_settings(
        Settings(enricher="anthropic", anthropic_api_key="k", anthropic_model="claude-x-1")
    )
    assert e._model == "claude-x-1"


def test_build_enricher_anthropic_requires_key() -> None:
    with pytest.raises(ValueError):
        build_enricher(Settings(enricher="anthropic", anthropic_api_key=None))
    e = build_enricher(Settings(enricher="anthropic", anthropic_api_key="k"))
    assert isinstance(e, AnthropicEnricher)


# --- the key ------------------------------------------------------------------------------------


def test_the_key_is_a_secret_that_settings_do_not_print() -> None:
    settings = Settings(enricher="anthropic", anthropic_api_key="sk-ant-api03-SECRET-KEY")
    assert "SECRET-KEY" not in repr(settings) and "SECRET-KEY" not in str(settings.model_dump())
    assert "SECRET-KEY" not in settings.model_dump_json()


@pytest.mark.parametrize("key", [None, "", "   "])
def test_choosing_anthropic_without_a_key_stops_at_startup(key: str | None) -> None:
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        build_enricher(Settings(enricher="anthropic", anthropic_api_key=key))


def test_the_default_needs_no_key_and_loads_no_sdk_client() -> None:
    from session_lens.enrich.mock import MockEnricher

    assert Settings().enricher == "mock"
    assert not Settings().anthropic_api_key or not Settings().anthropic_api_key.get_secret_value()
    assert isinstance(build_enricher(Settings()), MockEnricher)


def test_the_remote_choice_is_announced_once_without_the_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    build_enricher(Settings(enricher="anthropic", anthropic_api_key="sk-ant-api03-SECRET-KEY"))
    warned = [r for r in caplog.records if "sent to the Anthropic API" in r.getMessage()]
    assert len(warned) == 1 and warned[0].levelno == logging.WARNING
    assert "SECRET-KEY" not in caplog.text
