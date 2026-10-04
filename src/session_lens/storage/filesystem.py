"""Local filesystem RecordingStore: the default. Recordings never leave the machine."""

from __future__ import annotations

import asyncio
import contextlib
import os
import tempfile
from pathlib import Path, PurePosixPath

from session_lens.storage.base import RecordingExpired


class InvalidKey(ValueError):
    """The key is not a safe relative path inside the store root."""


class FilesystemStore:
    """Objects are files under `root`, addressed by keys like `recordings/2026/10/<uuid>.jsonl`.

    Writes are atomic (temp file in the same directory, then `os.replace`), so a reader never
    sees a partial recording. Files are 0600 and directories 0700 where the OS supports it; on
    Windows the user's profile ACLs apply. Keys that are absolute, contain `..`, or resolve
    outside the root (for example through a symlink) are rejected."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._real: Path | None = None

    @property
    def root(self) -> Path:
        return self._root

    def _real_root(self) -> Path:
        """The root as the operating system spells it. It is created first: on Windows an
        existing directory resolves to its long name (runneradmin) and one that does not exist
        yet keeps its short one (RUNNER~1), so resolving a key under a root that appears
        halfway through would compare two spellings of the same place."""
        if self._real is None:
            try:
                self._root.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass  # unusable: the operation that needed it reports that
            self._real = self._root.resolve()
        return self._real

    def _path(self, key: str) -> Path:
        if not key or "\x00" in key or "\\" in key or ":" in key:
            raise InvalidKey("invalid key")
        parts = PurePosixPath(key).parts
        if "/".join(parts) != key:  # not canonical: `//`, `/./`, a trailing slash
            raise InvalidKey("invalid key")
        if (
            PurePosixPath(key).is_absolute()
            or not parts
            or any(p in ("", ".", "..") for p in parts)
        ):
            raise InvalidKey("invalid key")
        root = self._real_root()
        path = root.joinpath(*parts).resolve()
        if path == root or not path.is_relative_to(root):
            raise InvalidKey("key escapes the store root")
        return path

    def _mkdirs(self, directory: Path) -> None:
        root = self._real_root()
        missing = []
        d = directory
        while d != root and not d.exists():
            missing.append(d)
            d = d.parent
        root.mkdir(parents=True, exist_ok=True)
        for d in reversed(missing):
            try:
                d.mkdir(mode=0o700, exist_ok=True)
            except PermissionError:
                # Windows reports "access denied", not "exists", when another thread is creating
                # the same directory at that moment. If it is there now, that is all we wanted.
                if not d.is_dir():
                    raise

    def _put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        self._mkdirs(path.parent)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            if os.name != "nt":
                os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    def _get(self, key: str) -> bytes:
        path = self._path(key)
        if (
            path.is_dir()
        ):  # a directory is not a recording (read_bytes would raise OS-specific errors)
            raise RecordingExpired(key)
        try:
            return path.read_bytes()
        except (FileNotFoundError, NotADirectoryError):
            raise RecordingExpired(key) from None

    def _delete(self, key: str) -> None:
        path = self._path(key)
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
        root = self._real_root()
        parent = path.parent
        while parent != root and parent.is_relative_to(root):
            try:
                parent.rmdir()  # only succeeds when empty
            except OSError:
                break
            parent = parent.parent

    def _ping(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        if not os.access(self._root, os.W_OK | os.X_OK):
            raise OSError("storage directory is not writable")

    async def put(self, key: str, data: bytes) -> None:
        await asyncio.to_thread(self._put, key, data)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._get, key)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._delete, key)

    async def ping(self) -> None:
        await asyncio.to_thread(self._ping)

    async def aclose(self) -> None:
        return None
