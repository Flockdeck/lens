"""packaging/publish-downloads.sh against a fake S3 server (moto), with the real aws CLI.

The script is the part of a release that cannot be undone: files under a version are cached for a
year and never purged. So what it does in what order, and what it refuses, is tested here.
Skipped where `aws` or `sh` is not installed.
"""

from __future__ import annotations

import os
import shutil
import socket
import stat
import subprocess
import sys
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import boto3
import pytest
from botocore.client import Config
from moto.server import ThreadedMotoServer

PACKAGING = Path(__file__).resolve().parents[2] / "packaging"
SCRIPT = PACKAGING / "publish-downloads.sh"
sys.path.insert(0, str(PACKAGING))

import fake_release  # noqa: E402
import release  # noqa: E402


def aws_path() -> str | None:
    """The aws CLI to use: LENS_TEST_AWS if set (a script is fine, it is run by sh), else PATH."""
    return os.environ.get("LENS_TEST_AWS") or shutil.which("aws")


def usable() -> bool:
    """Whether the script's tools can be run the way it runs them, from sh. Finding the name is
    not enough: an aws that is a Python script, as one installed with pip can be on Windows,
    cannot be started by sh."""
    aws = aws_path()
    if aws is None or shutil.which("sh") is None or shutil.which("curl") is None:
        return False
    probe = subprocess.run(  # noqa: S603
        ["sh", "-c", f'"{Path(aws).as_posix()}" --version'],  # noqa: S607
        capture_output=True,
        check=False,
    )
    return probe.returncode == 0


pytestmark = pytest.mark.skipif(not usable(), reason="needs a working aws CLI, sh and curl")

BUCKET = "flockdeck-downloads"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class Store:
    def __init__(self, port: int) -> None:
        self.endpoint = f"http://127.0.0.1:{port}"
        self.s3 = boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id="test",
            aws_secret_access_key="test",
            region_name="us-east-1",
            config=Config(s3={"addressing_style": "path"}),
        )
        self.s3.create_bucket(Bucket=BUCKET)

    def keys(self) -> list[str]:
        out = self.s3.list_objects_v2(Bucket=BUCKET).get("Contents", [])
        return sorted(o["Key"] for o in out)

    def body(self, key: str) -> bytes:
        return bytes(self.s3.get_object(Bucket=BUCKET, Key=key)["Body"].read())

    def head(self, key: str) -> dict[str, object]:
        return dict(self.s3.head_object(Bucket=BUCKET, Key=key))


@pytest.fixture
def store() -> Iterator[Store]:
    port = free_port()
    server = ThreadedMotoServer(port=port, verbose=False)
    server.start()
    try:
        # moto keeps its state for the life of the process, whatever server is started
        urllib.request.urlopen(  # noqa: S310
            urllib.request.Request(f"http://127.0.0.1:{port}/moto-api/reset", method="POST")
        ).read()
        yield Store(port)
    finally:
        server.stop()


@pytest.fixture
def aws_log(tmp_path: Path) -> Path:
    """A wrapper `aws` that records each upload and then runs the real one."""
    real = aws_path()
    assert real
    log = tmp_path / "aws.log"
    wrapper_dir = tmp_path / "bin"
    wrapper_dir.mkdir()
    wrapper = wrapper_dir / "aws"
    lines = [
        "#!/bin/sh",
        f'printf \'%s\\n\' "$*" >> "{log.as_posix()}"',
        f'exec "{Path(real).as_posix()}" "$@"',
    ]
    wrapper.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
    log.write_text("", encoding="utf-8")
    return log


def publish(
    store: Store,
    dist: Path,
    tag: str,
    aws_log: Path,
    *,
    env: dict[str, str] | None = None,
    listable_ok: bool = True,
) -> subprocess.CompletedProcess[str]:
    path = f"{aws_log.parent / 'bin'}{os.pathsep}{os.environ['PATH']}"
    full = {
        **os.environ,
        "PATH": path,
        "DO_SPACES_KEY": "test",
        "DO_SPACES_SECRET": "test",
        "DO_SPACES_BUCKET": BUCKET,
        "DO_SPACES_REGION": "lon1",
        "DO_SPACES_ENDPOINT": store.endpoint,
        "LENS_DL_URL": f"{store.endpoint}/{BUCKET}",
        "LENS_CHECK_WAIT": "0",
        **({"LENS_ALLOW_LISTABLE": "1"} if listable_ok else {}),
        **(env or {}),
    }
    return subprocess.run(  # noqa: S603
        ["sh", SCRIPT.as_posix(), tag, dist.as_posix()],  # noqa: S607
        env=full,
        capture_output=True,
        text=True,
        check=False,
    )


def uploads(aws_log: Path) -> list[str]:
    keys = []
    for line in aws_log.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if (
            parts[:2] == ["s3", "cp"]
            and parts[3].startswith("s3://")
            and not parts[2].startswith("s3://")
        ):
            keys.append(parts[3].split(f"s3://{BUCKET}/", 1)[1])
    return keys


def made(tmp_path: Path, tag: str, name: str = "dist") -> Path:
    dist = tmp_path / f"{name}-{tag}"
    fake_release.make_release(dist, tag)
    return dist


def test_a_release_goes_up_in_the_order_that_makes_it_safe(
    store: Store, tmp_path: Path, aws_log: Path
) -> None:
    dist = made(tmp_path, "v0.3.0")
    result = publish(store, dist, "v0.3.0", aws_log)
    assert result.returncode == 0, result.stdout + result.stderr

    order = uploads(aws_log)
    first_latest = next(i for i, k in enumerate(order) if k.startswith("lens/latest/"))
    assert all(k.startswith("lens/v0.3.0/") for k in order[:first_latest])
    assert order[-1] == "lens/latest.json"  # the switch is last of all
    assert order.index("lens/v0.3.0/manifest.json.sig") < order.index("lens/v0.3.0/manifest.json")
    assert order.index("lens/v0.3.0/manifest.json") < first_latest  # the version is whole first

    assert store.keys() == sorted(
        [f"lens/v0.3.0/{p.name}" for p in dist.iterdir() if p.name != "latest.json"]
        + ["lens/latest.json"]
        + [
            f"lens/latest/lens_{os_name}_{arch}.{'zip' if os_name == 'windows' else 'tar.gz'}"
            for os_name, arch in release.PLATFORMS
        ]
    )
    assert store.body("lens/latest.json") == b'{"version":"v0.3.0"}\n'
    assert store.body("lens/v0.3.0/manifest.json") == (dist / "manifest.json").read_bytes()


def test_how_long_each_file_may_be_cached(store: Store, tmp_path: Path, aws_log: Path) -> None:
    publish(store, made(tmp_path, "v0.3.0"), "v0.3.0", aws_log)
    forever = "public, max-age=31536000, immutable"
    assert store.head("lens/v0.3.0/checksums.txt")["CacheControl"] == forever
    assert store.head("lens/v0.3.0/manifest.json")["CacheControl"] == forever
    assert store.head("lens/v0.3.0/lens_v0.3.0_linux_amd64.tar.gz")["CacheControl"] == forever
    assert store.head("lens/latest.json")["CacheControl"] == "public, max-age=60"
    assert store.head("lens/latest/lens_linux_amd64.tar.gz")["CacheControl"] == "public, max-age=60"
    assert store.head("lens/v0.3.0/manifest.json")["ContentType"] == "application/json"
    assert (
        store.head("lens/v0.3.0/lens_v0.3.0_windows_amd64.zip")["ContentType"] == "application/zip"
    )
    acl = store.s3.get_object_acl(Bucket=BUCKET, Key="lens/v0.3.0/checksums.txt")
    assert any(g["Grantee"].get("URI", "").endswith("AllUsers") for g in acl["Grants"])


def test_a_prerelease_goes_up_under_its_version_and_moves_nothing(
    store: Store, tmp_path: Path, aws_log: Path
) -> None:
    publish(store, made(tmp_path, "v0.3.0"), "v0.3.0", aws_log)
    before = store.body("lens/latest.json")
    result = publish(store, made(tmp_path, "v0.4.0-rc.1"), "v0.4.0-rc.1", aws_log)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "pre-release" in result.stdout
    assert "lens/v0.4.0-rc.1/manifest.json" in store.keys()
    assert store.body("lens/latest.json") == before == b'{"version":"v0.3.0"}\n'


def test_an_older_release_does_not_move_latest_back(
    store: Store, tmp_path: Path, aws_log: Path
) -> None:
    publish(store, made(tmp_path, "v0.10.0"), "v0.10.0", aws_log)
    result = publish(store, made(tmp_path, "v0.9.0"), "v0.9.0", aws_log)  # 0.9 < 0.10, as numbers
    assert result.returncode == 0, result.stdout + result.stderr
    assert "newer than v0.9.0" in result.stdout
    assert "lens/v0.9.0/checksums.txt" in store.keys()
    assert store.body("lens/latest.json") == b'{"version":"v0.10.0"}\n'


def test_a_newer_release_moves_latest_and_its_download_names(
    store: Store, tmp_path: Path, aws_log: Path
) -> None:
    publish(store, made(tmp_path, "v0.3.0"), "v0.3.0", aws_log)
    newer = made(tmp_path, "v0.3.1")
    assert publish(store, newer, "v0.3.1", aws_log).returncode == 0
    assert store.body("lens/latest.json") == b'{"version":"v0.3.1"}\n'
    served = store.body("lens/latest/lens_linux_amd64.tar.gz")
    assert served == (newer / "lens_v0.3.1_linux_amd64.tar.gz").read_bytes()


def test_publishing_the_same_release_again_changes_nothing_that_was_cached(
    store: Store, tmp_path: Path, aws_log: Path
) -> None:
    dist = made(tmp_path, "v0.3.0")
    publish(store, dist, "v0.3.0", aws_log)
    first_manifest = store.body("lens/v0.3.0/manifest.json")
    # signed again from the same archives: a new date, so a different manifest
    from datetime import UTC, datetime

    key, _ = fake_release.make_release(
        tmp_path / "again", "v0.3.0", now=datetime(2030, 1, 1, tzinfo=UTC)
    )
    for p in dist.glob("lens_*"):
        shutil.copy(p, tmp_path / "again" / p.name)
    release.write_sums(tmp_path / "again", "v0.3.0")
    release.run_sign(
        tmp_path / "again",
        "v0.3.0",
        key_text=fake_release.private_pem(key),
        any_key=True,
        now=datetime(2030, 1, 1, tzinfo=UTC),
    )
    shutil.copy(dist / "checksums.txt", tmp_path / "again" / "checksums.txt")
    result = publish(store, tmp_path / "again", "v0.3.0", aws_log)
    # the archives are identical, but this was signed by another key, so its signatures differ
    # from the published ones; the manifest that was published first is kept regardless
    assert "already published with these same files" in result.stdout or result.returncode != 0
    assert store.body("lens/v0.3.0/manifest.json") == first_manifest


def test_a_version_already_published_with_other_files_is_refused(
    store: Store, tmp_path: Path, aws_log: Path
) -> None:
    publish(store, made(tmp_path, "v0.3.0", "first"), "v0.3.0", aws_log)
    published = store.body("lens/v0.3.0/checksums.txt")
    other = made(tmp_path, "v0.3.0", "second")  # random bytes: different archives, same tag
    aws_log.write_text("", encoding="utf-8")
    result = publish(store, other, "v0.3.0", aws_log)
    assert result.returncode != 0
    assert "already published with other files" in result.stderr
    assert uploads(aws_log) == []  # not one file was written over
    assert store.body("lens/v0.3.0/checksums.txt") == published


def test_an_archive_that_does_not_match_its_checksum_is_refused_before_anything_goes_up(
    store: Store, tmp_path: Path, aws_log: Path
) -> None:
    dist = made(tmp_path, "v0.3.0")
    victim = next(dist.glob("lens_v0.3.0_linux_arm64*"))
    victim.write_bytes(victim.read_bytes() + b"tampered")
    result = publish(store, dist, "v0.3.0", aws_log)
    assert result.returncode != 0
    assert "does not match checksums.txt" in result.stderr
    assert store.keys() == [] and uploads(aws_log) == []


def test_an_unsigned_release_is_refused(store: Store, tmp_path: Path, aws_log: Path) -> None:
    dist = made(tmp_path, "v0.3.0")
    (dist / "manifest.json.sig").unlink()
    result = publish(store, dist, "v0.3.0", aws_log)
    assert result.returncode != 0 and "manifest.json.sig is missing" in result.stderr
    assert store.keys() == []


def test_a_manifest_for_another_version_is_refused(
    store: Store, tmp_path: Path, aws_log: Path
) -> None:
    dist = made(tmp_path, "v0.3.0")
    (dist / "latest.json").write_text('{"version":"v9.9.9"}\n', encoding="utf-8")
    result = publish(store, dist, "v0.3.0", aws_log)
    assert result.returncode != 0 and "does not name v0.3.0" in result.stderr
    assert store.keys() == []


def test_every_missing_secret_is_named_at_once(store: Store, tmp_path: Path, aws_log: Path) -> None:
    dist = made(tmp_path, "v0.3.0")
    blank = {"DO_SPACES_KEY": "", "DO_SPACES_SECRET": "", "DO_SPACES_REGION": ""}
    result = publish(store, dist, "v0.3.0", aws_log, env=blank)
    assert result.returncode != 0
    assert "not set: DO_SPACES_KEY DO_SPACES_SECRET DO_SPACES_REGION" in result.stderr
    assert store.keys() == []


@pytest.mark.parametrize("tag", ["0.3.0", "latest", "v1.2", ""])
def test_only_release_versions_are_accepted(
    store: Store, tmp_path: Path, aws_log: Path, tag: str
) -> None:
    result = publish(store, tmp_path, tag, aws_log)
    assert result.returncode != 0 and store.keys() == []


def test_a_bucket_that_lists_itself_stops_the_release_before_latest_moves(
    store: Store, tmp_path: Path, aws_log: Path
) -> None:
    """The real bucket is private, so listing it fails. A store that lists it to anyone is a
    misconfiguration, and the release must not switch over to it."""
    dist = made(tmp_path, "v0.3.0")
    result = publish(store, dist, "v0.3.0", aws_log, listable_ok=False)
    assert result.returncode != 0
    assert "lists the bucket to anyone" in result.stderr
    assert "lens/latest.json" not in store.keys()


def test_a_store_that_cannot_be_read_is_not_taken_for_an_empty_one(
    tmp_path: Path, aws_log: Path
) -> None:
    """If the script cannot tell whether a version is already published, it must not publish."""
    dead = Store.__new__(Store)
    dead.endpoint = f"http://127.0.0.1:{free_port()}"  # nothing listens here
    dist = made(tmp_path, "v0.3.0")
    result = publish(dead, dist, "v0.3.0", aws_log)
    assert result.returncode != 0
    assert "could not read" in result.stderr
    assert uploads(aws_log) == []
