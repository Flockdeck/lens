"""OllamaEnricher against a scripted fake server (httpx.MockTransport). No network."""

import json
import logging
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from session_lens.config import Settings
from session_lens.enrich import EnrichmentError, build_enricher
from session_lens.enrich.ollama import OllamaEnricher, require_local_url
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
RISKY = [{"seq": 3, "tool": "Bash", "summary": "git push -f", "severity": "high", "rule": "force"}]
URL = "http://127.0.0.1:11434"


def chat(text: str, *, done: str = "stop", i: int = 100, o: int = 20) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "message": {"role": "assistant", "content": text},
            "done": True,
            "done_reason": done,
            "prompt_eval_count": i,
            "eval_count": o,
        },
    )


class FakeOllama:
    """Plays back responses (or raises exceptions) in order, recording each request body."""

    def __init__(self, *script: httpx.Response | Exception) -> None:
        self.script = list(script)
        self.requests: list[httpx.Request] = []
        self.client = httpx.AsyncClient(transport=httpx.MockTransport(self._handle))

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def bodies(self) -> list[dict[str, Any]]:
        return [json.loads(r.content) for r in self.requests]

    def enricher(self, **kwargs: Any) -> OllamaEnricher:
        return OllamaEnricher(URL, "m", client=self.client, **kwargs)


def _chain_text(exc: BaseException | None) -> str:
    parts: list[str] = []
    while exc is not None:
        parts.append(f"{type(exc).__name__}: {exc}")
        # What a traceback would show: the explicit cause, or the implicit context unless
        # it was suppressed with `from None`.
        exc = exc.__cause__ or (None if exc.__suppress_context__ else exc.__context__)
    return chr(10).join(parts)


async def test_happy_path(make_analysis: Callable[..., Any]) -> None:
    fake = FakeOllama(chat(json.dumps(GOOD)))
    result = await fake.enricher().enrich(make_analysis(risky_actions=RISKY))

    assert result.summary == "Fixed a bug."
    assert result.frustration == 1.0
    assert result.stuck_points[0].description == "flaky test"
    assert result.risk_notes[0].seq == 3
    assert (result.input_tokens, result.output_tokens) == (100, 20)
    assert result.model == "m"
    assert result.prompt_version == PROMPT_VERSION

    request = fake.requests[0]
    assert request.url.path == "/api/chat"
    body = fake.bodies()[0]
    assert body["stream"] is False
    assert body["options"]["temperature"] == 0
    assert body["format"]["type"] == "object"
    assert "SECRET-PROMPT" in body["messages"][1]["content"]


async def test_malformed_then_valid_retries_and_sums_tokens(
    make_analysis: Callable[..., Any],
) -> None:
    fake = FakeOllama(chat("not json", i=10, o=1), chat(json.dumps(GOOD), i=10, o=5))
    result = await fake.enricher().enrich(make_analysis())
    assert len(fake.requests) == 2
    assert (result.input_tokens, result.output_tokens) == (20, 6)


async def test_schema_violation_counts_as_malformed(make_analysis: Callable[..., Any]) -> None:
    bad = {**GOOD, "outcome": "great"}
    fake = FakeOllama(chat(json.dumps(bad)), chat(json.dumps(GOOD)))
    await fake.enricher().enrich(make_analysis())
    assert len(fake.requests) == 2


async def test_malformed_after_bounded_retries_is_permanent(
    make_analysis: Callable[..., Any],
) -> None:
    fake = FakeOllama(*[chat("nope") for _ in range(3)])
    with pytest.raises(EnrichmentError) as exc:
        await fake.enricher(max_output_attempts=3).enrich(make_analysis())
    assert exc.value.retryable is False
    assert len(fake.requests) == 3


@pytest.mark.parametrize(
    ("outcome", "retryable"),
    [
        (httpx.ConnectError("refused"), True),  # Ollama not running
        (httpx.ReadTimeout("slow"), True),  # model still loading
        (httpx.Response(500), True),
        (httpx.Response(503), True),
        (httpx.Response(429), True),
        (httpx.Response(408), True),
        (httpx.Response(400), False),
        (httpx.Response(404), False),  # model not pulled
        (httpx.Response(200, text="<html>not json</html>"), False),
        (httpx.Response(200, json=["not", "an", "object"]), False),
    ],
)
async def test_errors_are_mapped(
    make_analysis: Callable[..., Any], outcome: httpx.Response | Exception, retryable: bool
) -> None:
    fake = FakeOllama(outcome)
    with pytest.raises(EnrichmentError) as exc:
        await fake.enricher().enrich(make_analysis())
    assert exc.value.retryable is retryable
    assert len(fake.requests) == 1


async def test_missing_model_message_tells_the_user_what_to_do(
    make_analysis: Callable[..., Any],
) -> None:
    fake = FakeOllama(httpx.Response(404))
    with pytest.raises(EnrichmentError, match="ollama pull m"):
        await fake.enricher().enrich(make_analysis())


async def test_content_never_logged_or_in_errors(
    make_analysis: Callable[..., Any], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    fake = FakeOllama(*[chat('{"summary": "SECRET-OUT"}') for _ in range(3)])
    with pytest.raises(EnrichmentError) as exc:
        await fake.enricher().enrich(make_analysis())
    assert "SECRET" not in _chain_text(exc.value)
    assert "SECRET" not in caplog.text


async def test_transport_error_chain_has_no_content(make_analysis: Callable[..., Any]) -> None:
    fake = FakeOllama(httpx.ConnectError("SECRET-PROMPT leaked in a transport message"))
    with pytest.raises(EnrichmentError) as exc:
        await fake.enricher().enrich(make_analysis())
    assert "SECRET" not in _chain_text(exc.value)


async def test_truncation_retries_once_with_more_room_then_fails(
    make_analysis: Callable[..., Any],
) -> None:
    fake = FakeOllama(chat("{", done="length", i=5, o=7), chat("{", done="length"))
    with pytest.raises(EnrichmentError) as exc:
        await fake.enricher(max_tokens=1000).enrich(make_analysis())
    assert exc.value.retryable is False
    assert "num_predict" in str(exc.value)
    assert [b["options"]["num_predict"] for b in fake.bodies()] == [1000, 2000]
    assert (exc.value.input_tokens, exc.value.output_tokens) == (105, 27)


async def test_truncation_then_valid_succeeds(make_analysis: Callable[..., Any]) -> None:
    fake = FakeOllama(chat("{", done="length"), chat(json.dumps(GOOD)))
    result = await fake.enricher(max_tokens=1000).enrich(make_analysis())
    assert result.summary == "Fixed a bug."
    assert fake.bodies()[1]["options"]["num_predict"] == 2000


async def test_failed_attempt_usage_is_carried_on_error(
    make_analysis: Callable[..., Any],
) -> None:
    fake = FakeOllama(chat("x", i=10, o=1), chat("x", i=10, o=1), chat("x", i=10, o=1))
    with pytest.raises(EnrichmentError) as exc:
        await fake.enricher().enrich(make_analysis())
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
    fake = FakeOllama(chat(json.dumps(out)))
    result = await fake.enricher().enrich(make_analysis(risky_actions=RISKY))
    assert [n.seq for n in result.risk_notes] == [3]
    assert [p.approx_seq for p in result.stuck_points] == [3, None]


# --- nothing leaves the machine ----------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:11434",
        "http://localhost:11434/",
        "http://[::1]:11434",
        "http://host.docker.internal:11434",
        "https://LOCALHOST:11434",
    ],
)
def test_local_urls_are_accepted(url: str) -> None:
    assert require_local_url(url) == url.rstrip("/")


@pytest.mark.parametrize(
    "url",
    [
        "http://ollama.example.com:11434",
        "http://8.8.8.8:11434",
        "http://192.168.1.20:11434",
        "http://127.0.0.1.evil.example:11434",
        "http://localhost.evil.example",
        "ftp://127.0.0.1",
        "127.0.0.1:11434",
        "",
    ],
)
def test_non_local_urls_are_refused(url: str) -> None:
    with pytest.raises(ValueError):
        require_local_url(url)
    with pytest.raises(ValueError):
        OllamaEnricher(url, "m")


def test_build_enricher_selects_ollama_and_passes_settings_through() -> None:
    e = build_enricher(Settings(enricher="ollama", ollama_url=URL, ollama_model="qwen2.5:7b"))
    assert isinstance(e, OllamaEnricher)
    assert e._model == "qwen2.5:7b"
    with pytest.raises(ValueError):
        build_enricher(Settings(enricher="ollama", ollama_url="http://example.com:11434"))


def test_build_enricher_defaults_to_the_mock() -> None:
    from session_lens.enrich.mock import MockEnricher

    assert isinstance(build_enricher(Settings()), MockEnricher)


def test_client_ignores_proxy_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:3128")
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.example:3128")
    e = OllamaEnricher(URL, "m")
    assert e._client.follow_redirects is False
    assert not e._client._trust_env  # type: ignore[attr-defined]
