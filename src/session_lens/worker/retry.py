"""Failure classification and backoff."""

from __future__ import annotations

import random
from dataclasses import dataclass

import zstandard

from session_lens.enrich.base import EnrichmentError
from session_lens.recording.parser import EmptyRecording, UnsupportedVersion

BACKOFF_BASE_SECONDS = 5.0
BACKOFF_CAP_SECONDS = 300.0
MAX_ERROR_LENGTH = 500


@dataclass(frozen=True)
class Failure:
    message: str  # never contains recording content
    retryable: bool


def backoff_seconds(
    attempt: int,
    base: float = BACKOFF_BASE_SECONDS,
    cap: float = BACKOFF_CAP_SECONDS,
    rng: random.Random | None = None,
) -> float:
    """Exponential backoff with equal jitter: half the delay is fixed, half is random, so
    retries of a burst of failures spread out without ever being near zero."""
    delay = min(cap, base * 2.0 ** max(attempt - 1, 0))
    rng = rng or random.Random()
    return delay / 2 + rng.uniform(0, delay / 2)


def classify(exc: BaseException) -> Failure:
    """Permanent: unsupported version, empty file, corrupt blob, missing raw, non-retryable
    enrichment failure. Retryable: enrichment timeouts/rate limits/5xx, and anything
    unexpected (bounded by max_attempts). Message text is kept only for exception types whose
    messages we control; arbitrary exceptions (e.g. validation errors) can echo their input,
    so only their type name is stored."""
    name = type(exc).__name__
    if isinstance(exc, UnsupportedVersion | EmptyRecording):
        return Failure(f"{name}: {exc}"[:MAX_ERROR_LENGTH], retryable=False)
    if isinstance(exc, EnrichmentError):
        return Failure(f"{name}: {exc}"[:MAX_ERROR_LENGTH], retryable=exc.retryable)
    if isinstance(exc, zstandard.ZstdError):
        return Failure(f"{name}: raw recording is corrupt", retryable=False)
    if isinstance(exc, MissingRaw):
        return Failure("raw recording is no longer available", retryable=False)
    if isinstance(exc, TimeoutError):
        return Failure("TimeoutError: processing timed out", retryable=True)
    return Failure(name, retryable=True)


class MissingRaw(Exception):
    """The raw recording is gone (retention cleanup ran). Permanent."""
