import random

from session_lens.recording.parser import EmptyRecording, UnsupportedVersion
from session_lens.storage.base import RecordingExpired
from session_lens.worker.retry import backoff_seconds, classify
from tests.worker.helpers import permanent, retryable


def test_backoff_grows_exponentially_with_jitter_and_caps():
    rng = random.Random(1)
    for attempt, delay in [(1, 5), (2, 10), (3, 20), (4, 40), (10, 300), (50, 300)]:
        samples = [backoff_seconds(attempt, rng=rng) for _ in range(200)]
        assert all(delay / 2 <= s <= delay for s in samples)
        assert max(samples) - min(samples) > delay / 10  # jittered, not constant


def test_classify():
    assert not classify(UnsupportedVersion("v2")).retryable
    assert not classify(EmptyRecording()).retryable
    expired = classify(RecordingExpired())
    assert not expired.retryable and expired.message == "raw recording expired"
    assert not classify(permanent()).retryable
    assert classify(retryable()).retryable
    assert classify(TimeoutError()).retryable
    assert classify(RuntimeError("anything else")).retryable


def test_unknown_exception_text_is_not_stored():
    failure = classify(ValueError("secret recording content"))
    assert failure.message == "ValueError"
