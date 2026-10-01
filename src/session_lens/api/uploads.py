"""Multipart upload validation: per-file extension, size and emptiness checks."""

import posixpath

from starlette.datastructures import UploadFile

from session_lens.api.schemas import RejectedFile
from session_lens.config import Settings

_CHUNK = 1024 * 1024
_MAX_FILENAME = 255


def clean_filename(raw: str | None) -> str:
    name = (raw or "").replace("\\", "/")
    return posixpath.basename(name).strip() or "(unnamed)"


async def read_limited(file: UploadFile, limit: int) -> bytes | None:
    """Read at most `limit` bytes in chunks; None if the file is larger."""
    if file.size is not None and file.size > limit:
        return None
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(_CHUNK):
        total += len(chunk)
        if total > limit:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


async def check_file(file: UploadFile, settings: Settings) -> tuple[str, bytes | RejectedFile]:
    """Validate one part. Returns (filename, content) or (filename, rejection)."""
    name = clean_filename(file.filename)
    if len(name) > _MAX_FILENAME:
        return name[:_MAX_FILENAME], RejectedFile(
            filename=name[:_MAX_FILENAME], reason="filename too long"
        )
    if not name.lower().endswith(".jsonl"):
        return name, RejectedFile(filename=name, reason="wrong type: only .jsonl files accepted")
    data = await read_limited(file, settings.max_file_bytes)
    if data is None:
        return name, RejectedFile(
            filename=name, reason=f"too large: limit is {settings.max_file_bytes} bytes"
        )
    if not data.strip():
        return name, RejectedFile(filename=name, reason="empty")
    return name, data
