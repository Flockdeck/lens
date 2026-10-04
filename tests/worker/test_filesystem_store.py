import asyncio
import os
import stat
import uuid

import pytest

from lens.storage.base import RecordingExpired, build_store
from lens.storage.filesystem import FilesystemStore, InvalidKey

KEY = "recordings/2026/10/{}.jsonl"


def key() -> str:
    return KEY.format(uuid.uuid4())


async def test_round_trip_and_overwrite(fs_store):
    k = key()
    await fs_store.put(k, b"one\n")
    assert await fs_store.get(k) == b"one\n"
    await fs_store.put(k, b"two\n")
    assert await fs_store.get(k) == b"two\n"


async def test_17_mib_round_trip(fs_store):
    k = key()
    data = os.urandom(17 * 1024 * 1024)
    await fs_store.put(k, data)
    assert await fs_store.get(k) == data


async def test_missing_file_is_recording_expired(fs_store):
    with pytest.raises(RecordingExpired):
        await fs_store.get(key())
    await fs_store.put(key(), b"x")
    with pytest.raises(RecordingExpired):  # a directory is not a recording either
        await fs_store.get("recordings/2026")


async def test_delete_is_idempotent_and_removes_empty_directories(fs_store):
    k = key()
    await fs_store.put(k, b"x")
    other = key()
    await fs_store.put(other, b"y")
    await fs_store.delete(k)
    await fs_store.delete(k)
    assert (fs_store.root / "recordings" / "2026" / "10").is_dir()  # still holds `other`
    await fs_store.delete(other)
    assert fs_store.root.is_dir()  # the root itself stays
    assert list(fs_store.root.iterdir()) == []  # every empty parent directory is gone


async def test_write_is_atomic_no_partial_file_is_ever_visible(fs_store, monkeypatch):
    k = key()
    await fs_store.put(k, b"complete")

    def crash(src, dst):
        raise OSError("crash before the rename")

    monkeypatch.setattr(os, "replace", crash)
    with pytest.raises(OSError):
        await fs_store.put(k, b"partial replacement")
    monkeypatch.undo()
    assert await fs_store.get(k) == b"complete"  # the old content is intact
    leftovers = [p.name for p in (fs_store.root / "recordings/2026/10").iterdir()]
    assert all(not n.startswith(".tmp-") for n in leftovers)  # and no temp file is left behind


async def test_concurrent_writes_to_different_keys(fs_store):
    keys = [key() for _ in range(8)]
    payloads = {k: os.urandom(100_000) for k in keys}
    await asyncio.gather(*(fs_store.put(k, p) for k, p in payloads.items()))
    for k, p in payloads.items():
        assert await fs_store.get(k) == p


@pytest.mark.parametrize(
    "bad",
    [
        "../escape.jsonl",
        "recordings/../../escape.jsonl",
        "recordings/2026/../../../escape",
        "/etc/passwd",
        "/absolute/path.jsonl",
        "C:/windows/system.ini",
        "C:\\windows\\system.ini",
        "recordings\\..\\escape",
        "",
        ".",
        "..",
        "recordings//x.jsonl",
        "recordings/./x.jsonl",
        "recordings/x\x00.jsonl",
    ],
)
async def test_path_traversal_is_rejected_by_every_operation(fs_store, tmp_path, bad):
    for op in (
        lambda: fs_store.put(bad, b"x"),
        lambda: fs_store.get(bad),
        lambda: fs_store.delete(bad),
    ):
        with pytest.raises(InvalidKey):
            await op()
    assert not (tmp_path / "escape.jsonl").exists()
    assert not (tmp_path / "escape").exists()


async def test_symlink_escape_is_rejected(fs_store, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.jsonl").write_bytes(b"secret")
    await fs_store.put(key(), b"x")  # creates the root
    link = fs_store.root / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("cannot create symlinks here")
    with pytest.raises(InvalidKey):
        await fs_store.get("link/secret.jsonl")
    with pytest.raises(InvalidKey):
        await fs_store.put("link/new.jsonl", b"x")
    assert not (outside / "new.jsonl").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
async def test_files_and_directories_are_private(fs_store):
    k = key()
    await fs_store.put(k, b"x")
    path = fs_store.root / k
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    for d in (path.parent, path.parent.parent, path.parent.parent.parent):
        assert stat.S_IMODE(d.stat().st_mode) == 0o700


async def test_ping_creates_and_checks_the_root(tmp_path):
    store = FilesystemStore(tmp_path / "new" / "dir")
    await store.ping()
    assert (tmp_path / "new" / "dir").is_dir()


async def test_ping_fails_when_the_root_is_a_file(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    with pytest.raises(OSError):
        await FilesystemStore(blocker / "data").ping()


async def test_aclose_is_a_noop(fs_store):
    await fs_store.aclose()
    await fs_store.put(key(), b"still works")


def test_build_store_defaults_to_the_filesystem(tmp_path):
    from lens.config import Settings

    store = build_store(Settings(data_dir=str(tmp_path / "d")))
    assert isinstance(store, FilesystemStore) and store.root == tmp_path / "d"
