"""packaging/release.py: checksums, signatures, the manifest, and what it refuses."""

from __future__ import annotations

import base64
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

PACKAGING = Path(__file__).resolve().parents[2] / "packaging"
sys.path.insert(0, str(PACKAGING))

import fake_release  # noqa: E402
import release  # noqa: E402


def test_the_keys_flockdeck_trusts_are_the_ones_embedded() -> None:
    """If Flockdeck rotates its release key, this and the compat job in CI are what say so."""
    primary, standby = release.trusted_keys()
    assert base64.b64encode(release.raw_public(primary)).decode() == (
        "pz2sDY7Kt1XaOwrrH/NdCkChEMoBty1B1bXB5J4ROc4="
    )
    assert base64.b64encode(release.raw_public(standby)).decode() == release.STANDBY_PUBLIC_KEY


def test_a_signed_release_verifies_and_has_the_shapes_flockdeck_reads(tmp_path: Path) -> None:
    key, public = fake_release.make_release(
        tmp_path, "v0.3.0", now=datetime(2026, 10, 4, 8, 30, 15, 999, tzinfo=UTC)
    )
    assert release.run_verify(tmp_path, "v0.3.0", [key.public_key()]) == []

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert list(manifest) == ["version", "date", "notes_url", "notes", "files"]
    assert manifest["version"] == "v0.3.0"
    assert manifest["date"] == "2026-10-04T08:30:15Z"  # seconds, UTC, like Go's time.Time
    assert manifest["notes_url"] == "https://github.com/Flockdeck/lens/releases/tag/v0.3.0"
    names = [f["name"] for f in manifest["files"]]
    assert names == sorted(n for n in names if n.startswith("lens_")) + [
        "checksums.txt",
        "checksums.txt.sig",
    ]
    assert len([n for n in names if n.startswith("lens_")]) == 6
    first = manifest["files"][0]
    assert list(first) == ["name", "url", "sha256", "size"]
    assert first["url"] == f"https://dl.flockdeck.ai/lens/v0.3.0/{first['name']}"
    assert re.fullmatch(r"[0-9a-f]{64}", first["sha256"])
    # manifest.json is the indented form the publish script greps for
    assert '"version": "v0.3.0"' in (tmp_path / "manifest.json").read_text(encoding="utf-8")
    assert (tmp_path / "latest.json").read_text(encoding="utf-8") == '{"version":"v0.3.0"}\n'
    assert public  # raw ed25519 public key, base64


def test_a_signature_is_standard_base64_on_one_line(tmp_path: Path) -> None:
    fake_release.make_release(tmp_path)
    for name in ("checksums.txt.sig", "manifest.json.sig"):
        text = (tmp_path / name).read_text(encoding="utf-8")
        assert text.endswith("\n") and text.count("\n") == 1
        assert len(base64.b64decode(text.strip(), validate=True)) == 64


def test_checksums_are_sorted_and_in_the_format_sha256sum_writes(tmp_path: Path) -> None:
    fake_release.make_release(tmp_path)
    lines = (tmp_path / "checksums.txt").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 6
    assert lines == sorted(lines, key=lambda line: line.split("  ")[1])
    assert all(
        re.fullmatch(r"[0-9a-f]{64}  lens_v0\.3\.0_\w+_\w+\.(zip|tar\.gz)", ln) for ln in lines
    )


def test_archive_names_match_what_the_build_workflow_makes() -> None:
    assert release.archive_name("v0.3.0", "windows", "arm64") == "lens_v0.3.0_windows_arm64.zip"
    assert release.archive_name("v0.3.0", "linux", "amd64") == "lens_v0.3.0_linux_amd64.tar.gz"
    assert release.archive_name("v0.3.0", "darwin", "arm64") == "lens_v0.3.0_darwin_arm64.tar.gz"


def test_tampering_with_a_file_after_signing_is_found(tmp_path: Path) -> None:
    key, _ = fake_release.make_release(tmp_path)
    victim = next(tmp_path.glob("lens_v0.3.0_linux_amd64*"))
    victim.write_bytes(victim.read_bytes() + b"x")
    problems = release.run_verify(tmp_path, "v0.3.0", [key.public_key()])
    assert any(victim.name in p for p in problems)


def test_tampering_with_the_manifest_or_checksums_breaks_the_signature(tmp_path: Path) -> None:
    key, _ = fake_release.make_release(tmp_path)
    (tmp_path / "manifest.json").write_bytes(
        (tmp_path / "manifest.json").read_bytes().replace(b"A fake", b"A forged")
    )
    (tmp_path / "checksums.txt").write_bytes(b"0" * 64 + b"  lens_v0.3.0_linux_amd64.tar.gz\n")
    problems = release.run_verify(tmp_path, "v0.3.0", [key.public_key()])
    assert "manifest.json.sig does not verify" in problems
    assert "checksums.txt.sig does not verify" in problems


def test_a_signature_by_another_key_does_not_verify(tmp_path: Path) -> None:
    fake_release.make_release(tmp_path)
    other = Ed25519PrivateKey.generate().public_key()
    assert "checksums.txt.sig does not verify" in release.run_verify(tmp_path, "v0.3.0", [other])
    # and against the real keys, which a test key is not
    assert release.run_verify(tmp_path, "v0.3.0") != []


def sums_for(tmp_path: Path, tag: str = "v0.3.0", *, skip: str | None = None) -> None:
    for os_name, arch in release.PLATFORMS:
        name = release.archive_name(tag, os_name, arch)
        if skip and skip in name:
            continue
        (tmp_path / name).write_bytes(name.encode() * 50)
    release.write_sums(tmp_path)


def test_a_release_missing_a_platform_is_refused(tmp_path: Path) -> None:
    sums_for(tmp_path, skip="windows_arm64")
    key = Ed25519PrivateKey.generate()
    with pytest.raises(release.ReleaseError, match="windows_arm64"):
        release.run_sign(tmp_path, "v0.3.0", key_text=fake_release.private_pem(key), any_key=True)
    assert not (tmp_path / "manifest.json").exists()  # nothing half-signed is left behind


def test_an_archive_that_changed_since_checksums_is_refused(tmp_path: Path) -> None:
    sums_for(tmp_path)
    next(tmp_path.glob("*darwin_arm64*")).write_bytes(b"swapped after the checksums")
    key = Ed25519PrivateKey.generate()
    with pytest.raises(release.ReleaseError, match="does not match checksums.txt"):
        release.run_sign(tmp_path, "v0.3.0", key_text=fake_release.private_pem(key), any_key=True)


def test_an_archive_of_another_version_is_refused(tmp_path: Path) -> None:
    sums_for(tmp_path, "v0.2.0")
    key = Ed25519PrivateKey.generate()
    with pytest.raises(release.ReleaseError, match="not an archive of v0.3.0"):
        release.run_sign(tmp_path, "v0.3.0", key_text=fake_release.private_pem(key), any_key=True)


def test_a_key_flockdeck_does_not_trust_is_refused_up_front(tmp_path: Path) -> None:
    sums_for(tmp_path)
    key = Ed25519PrivateKey.generate()
    with pytest.raises(release.ReleaseError, match="would refuse everything"):
        release.run_sign(tmp_path, "v0.3.0", key_text=fake_release.private_pem(key))


def test_a_missing_or_garbled_key_says_what_to_do(tmp_path: Path) -> None:
    sums_for(tmp_path)
    with pytest.raises(release.ReleaseError, match="LENS_SIGNING_KEY is not set"):
        release.run_sign(tmp_path, "v0.3.0", key_text="  ", any_key=True)
    with pytest.raises(release.ReleaseError, match="neither a PEM nor a base64 seed"):
        release.run_sign(tmp_path, "v0.3.0", key_text="not a key!", any_key=True)
    with pytest.raises(release.ReleaseError, match="not a 32-byte seed"):
        release.run_sign(
            tmp_path, "v0.3.0", key_text=base64.b64encode(b"short").decode(), any_key=True
        )


def test_a_key_may_be_a_pem_or_a_base64_seed(tmp_path: Path) -> None:
    key = Ed25519PrivateKey.generate()
    seed = key.private_bytes_raw()
    from_seed = release.parse_signing_key(base64.b64encode(seed).decode())
    from_pem = release.parse_signing_key(fake_release.private_pem(key))
    assert release.raw_public(from_seed.public_key()) == release.raw_public(key.public_key())
    assert release.raw_public(from_pem.public_key()) == release.raw_public(key.public_key())


@pytest.mark.parametrize("tag", ["0.3.0", "v0.3", "v1.2.3.4", "latest", "v0.3.0+build", ""])
def test_only_release_tags_are_accepted(tmp_path: Path, tag: str) -> None:
    key = Ed25519PrivateKey.generate()
    with pytest.raises(release.ReleaseError):
        release.run_sign(tmp_path, tag, key_text=fake_release.private_pem(key), any_key=True)


def test_the_command_line_works_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sums_for(tmp_path)
    key = Ed25519PrivateKey.generate()
    monkeypatch.setenv("LENS_SIGNING_KEY", fake_release.private_pem(key))
    assert release.main(["sums", "--out", str(tmp_path)]) == 0
    assert release.main(["sign", "--version", "v0.3.0", "--out", str(tmp_path), "--test-key"]) == 0
    assert release.main(["verify", "--version", "v0.3.0", "--out", str(tmp_path)]) == 1  # real keys
    assert "FAIL checksums.txt.sig does not verify" in capsys.readouterr().out
    monkeypatch.delenv("LENS_SIGNING_KEY")
    assert release.main(["sign", "--version", "v0.3.0", "--out", str(tmp_path)]) == 1
    assert "LENS_SIGNING_KEY is not set" in capsys.readouterr().err
