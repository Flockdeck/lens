"""In-memory RecordingStore for unit tests."""

from __future__ import annotations

from session_lens.storage.base import RecordingExpired


class InMemoryStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail_put = False

    async def put(self, key: str, data: bytes) -> None:
        if self.fail_put:
            raise OSError("put failed")
        self.objects[key] = data

    async def get(self, key: str) -> bytes:
        try:
            return self.objects[key]
        except KeyError:
            raise RecordingExpired(key) from None

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    async def ping(self) -> None:
        return None
