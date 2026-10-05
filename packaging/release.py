"""Checksum, sign and check a release, in the format dl.flockdeck.ai serves and Flockdeck verifies.

    python packaging/release.py sums   --version v0.2.0 --out dist
    python packaging/release.py sign   --version v0.2.0 --out dist [--notes FILE]
    python packaging/release.py verify --version v0.2.0 --out dist

This is the Python counterpart of Flockdeck's cmd/release (-sums, -sign), and writes the same
files in the same shapes, so that Flockdeck's own updater code can check them:

  checksums.txt        "<sha256>  <archive>" per line, sorted
  checksums.txt.sig    Ed25519 signature of those exact bytes, base64 on one line
  manifest.json        the release: version, date, notes, and every file with its sha256 and size
  manifest.json.sig    its signature
  latest.json          {"version":"v0.2.0"}, unsigned: all it does is name a release

The key is Flockdeck's release key (Ed25519). Its private half is in the LENS_SIGNING_KEY secret
of this repository's `release` environment, as a PKCS#8 PEM (what Terraform writes) or as a
base64 seed. Its public half, and the standby's, are trusted below. Flockdeck builds trust those
two keys only, so a signature made with any other key would be refused by every copy; `sign`
refuses such a key up front instead of producing files nobody can use.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

PRODUCT = "lens"
REPO = "Flockdeck/lens"
SIGNING_KEY_ENV = "LENS_SIGNING_KEY"
DEFAULT_BASE = "https://dl.flockdeck.ai/lens"

# What a release has to contain: one archive per platform.
PLATFORMS = [
    ("linux", "amd64"),
    ("linux", "arm64"),
    ("darwin", "amd64"),
    ("darwin", "arm64"),
    ("windows", "amd64"),
    ("windows", "arm64"),
]

# The public halves of Flockdeck's release keys, as they are compiled into the Flockdeck app
# (internal/selfupdate/releasekey.go: releaseKey, releaseKeyStandby). Public keys; safe to commit.
PRIMARY_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEApz2sDY7Kt1XaOwrrH/NdCkChEMoBty1B1bXB5J4ROc4=
-----END PUBLIC KEY-----
"""
STANDBY_PUBLIC_KEY = "ty1U7aJkzB0IqhCQdtLCCeaSsWs608iLxIBXZcpvyyE="

TAG = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$")


class ReleaseError(Exception):
    """Something is wrong with the release or the key. The message says what to do."""


# ------------------------------------------------------------------------------------ keys


def trusted_keys() -> list[Ed25519PublicKey]:
    primary = serialization.load_pem_public_key(PRIMARY_PUBLIC_KEY.encode())
    standby = Ed25519PublicKey.from_public_bytes(base64.b64decode(STANDBY_PUBLIC_KEY))
    assert isinstance(primary, Ed25519PublicKey)
    return [primary, standby]


def raw_public(key: Ed25519PublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def parse_signing_key(text: str) -> Ed25519PrivateKey:
    """A PKCS#8 PEM (Terraform's private_key_pem_pkcs8) or a base64 32-byte seed."""
    text = text.strip()
    if text.startswith("-----BEGIN"):
        try:
            key = serialization.load_pem_private_key(text.encode(), password=None)
        except (ValueError, TypeError) as exc:
            raise ReleaseError(f"{SIGNING_KEY_ENV} is not a readable PEM private key") from exc
        if not isinstance(key, Ed25519PrivateKey):
            raise ReleaseError(f"{SIGNING_KEY_ENV} is not an Ed25519 key")
        return key
    try:
        seed = base64.b64decode(text, validate=True)
    except ValueError as exc:
        raise ReleaseError(f"{SIGNING_KEY_ENV} is neither a PEM nor a base64 seed") from exc
    if len(seed) != 32:
        raise ReleaseError(
            f"{SIGNING_KEY_ENV} is a base64 value of {len(seed)} bytes, not a 32-byte seed"
        )
    return Ed25519PrivateKey.from_private_bytes(seed)


def sign(key: Ed25519PrivateKey, data: bytes) -> bytes:
    """The detached signature: standard base64 of the Ed25519 signature, one line."""
    return (base64.b64encode(key.sign(data)).decode() + "\n").encode()


def check_signature(keys: list[Ed25519PublicKey], data: bytes, signature: bytes) -> bool:
    try:
        raw = base64.b64decode(signature.strip(), validate=True)
    except ValueError:
        return False
    for key in keys:
        try:
            key.verify(raw, data)
            return True
        except InvalidSignature:
            continue
    return False


# -------------------------------------------------------------------------------- the files


def archive_name(tag: str, os_name: str, arch: str) -> str:
    return f"{PRODUCT}_{tag}_{os_name}_{arch}.{'zip' if os_name == 'windows' else 'tar.gz'}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_sums(out: Path, tag: str) -> str:
    """checksums.txt over every archive in `out`. Rebuilt from what is there, since each build job
    writes only its own platform. An archive of any other release in the directory is an error,
    not something to leave out: what is signed and published is the directory as it stands."""
    archives = sorted(p for p in out.glob(f"{PRODUCT}_*") if p.suffix in {".zip", ".gz"})
    if not archives:
        raise ReleaseError(f"{out} holds no {PRODUCT} archives")
    foreign = [p.name for p in archives if not p.name.startswith(f"{PRODUCT}_{tag}_")]
    if foreign:
        raise ReleaseError(
            f"{out} holds archives that are not of {tag}: {', '.join(foreign)}. Only {tag}'s "
            "should have been downloaded into it"
        )
    text = "".join(f"{sha256_file(p)}  {p.name}\n" for p in archives)
    (out / "checksums.txt").write_text(text, encoding="utf-8", newline="")
    return text


def listed_files(out: Path, tag: str, base: str, sums: bytes) -> list[dict[str, object]]:
    """The manifest's entry for every archive checksums.txt lists, each read back and checked."""
    listed: dict[str, str] = {}
    for line in sums.decode("utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 2 or not parts[1].startswith(f"{PRODUCT}_{tag}_"):
            raise ReleaseError(f"checksums.txt lists {line!r}, which is not an archive of {tag}")
        listed[parts[1]] = parts[0]
    for os_name, arch in PLATFORMS:
        name = archive_name(tag, os_name, arch)
        if name not in listed:
            raise ReleaseError(f"checksums.txt does not list {name}; build the release again")
    files = []
    for name in sorted(listed):
        path = out / name
        if not path.is_file():
            raise ReleaseError(f"{name} is listed in checksums.txt but is not in {out}")
        got = sha256_file(path)
        if got != listed[name]:
            raise ReleaseError(f"{name} does not match checksums.txt; build the release again")
        files.append(file_entry(base, tag, name, got, path.stat().st_size))
    return files


def file_entry(base: str, tag: str, name: str, sha256: str, size: int) -> dict[str, object]:
    return {"name": name, "url": f"{base.rstrip('/')}/{tag}/{name}", "sha256": sha256, "size": size}


def bytes_entry(base: str, tag: str, name: str, data: bytes) -> dict[str, object]:
    return file_entry(base, tag, name, hashlib.sha256(data).hexdigest(), len(data))


def run_sign(
    out: Path,
    tag: str,
    *,
    key_text: str,
    base: str = DEFAULT_BASE,
    notes: Path | None = None,
    any_key: bool = False,
    now: datetime | None = None,
) -> None:
    if not TAG.match(tag):
        raise ReleaseError(f"--version needs the release's tag, such as v0.2.0, not {tag!r}")
    if not key_text.strip():
        raise ReleaseError(
            f"{SIGNING_KEY_ENV} is not set: it holds the release signing key, which Terraform "
            "writes into the repository's `release` environment"
        )
    key = parse_signing_key(key_text)
    public = key.public_key()
    if not any_key and not any(raw_public(public) == raw_public(k) for k in trusted_keys()):
        raise ReleaseError(
            f"{SIGNING_KEY_ENV} is not Flockdeck's release key or its standby, so Flockdeck "
            "would refuse everything signed with it"
        )
    sums_path = out / "checksums.txt"
    if not sums_path.is_file():
        raise ReleaseError(f"no release to sign in {out}: run `release.py sums` first")
    sums = sums_path.read_bytes()
    files = listed_files(out, tag, base, sums)
    sums_sig = sign(key, sums)
    files += [
        bytes_entry(base, tag, "checksums.txt", sums),
        bytes_entry(base, tag, "checksums.txt.sig", sums_sig),
    ]
    note_text = notes.read_text(encoding="utf-8").strip() if notes else ""
    when = (now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
    manifest_obj: dict[str, object] = {
        "version": tag,
        "date": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "notes_url": f"https://github.com/{REPO}/releases/tag/{tag}",
    }
    if note_text:
        manifest_obj["notes"] = note_text
    manifest_obj["files"] = files
    manifest = (json.dumps(manifest_obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    manifest_sig = sign(key, manifest)
    # Read back what was made, the way the app will, before leaving it for anyone.
    if not check_signature([public], sums, sums_sig) or not check_signature(
        [public], manifest, manifest_sig
    ):
        raise ReleaseError("the signatures just made do not verify; refusing to write them")
    pointer = (json.dumps({"version": tag}, separators=(",", ":")) + "\n").encode("utf-8")
    for name, data in {
        "checksums.txt.sig": sums_sig,
        "manifest.json": manifest,
        "manifest.json.sig": manifest_sig,
        "latest.json": pointer,
    }.items():
        (out / name).write_bytes(data)


def run_verify(out: Path, tag: str, keys: list[Ed25519PublicKey] | None = None) -> list[str]:
    """Everything the app would check of a published release. Returns what it found wrong."""
    keys = keys or trusted_keys()
    problems: list[str] = []

    def read(name: str) -> bytes:
        path = out / name
        if not path.is_file():
            problems.append(f"{name} is missing")
            return b""
        return path.read_bytes()

    sums, sums_sig = read("checksums.txt"), read("checksums.txt.sig")
    manifest, manifest_sig = read("manifest.json"), read("manifest.json.sig")
    if sums and not check_signature(keys, sums, sums_sig):
        problems.append("checksums.txt.sig does not verify")
    if manifest and not check_signature(keys, manifest, manifest_sig):
        problems.append("manifest.json.sig does not verify")
    if manifest:
        parsed = json.loads(manifest)
        if parsed.get("version") != tag:
            problems.append(f"manifest.json is for {parsed.get('version')}, not {tag}")
        for entry in parsed.get("files", []):
            path = out / entry["name"]
            if not path.is_file():
                problems.append(f"{entry['name']} is in the manifest but not in {out}")
            elif sha256_file(path) != entry["sha256"] or path.stat().st_size != entry["size"]:
                problems.append(f"{entry['name']} does not match the manifest")
        have = {e["name"] for e in parsed.get("files", [])}
        for os_name, arch in PLATFORMS:
            if archive_name(tag, os_name, arch) not in have:
                problems.append(f"the manifest has no {archive_name(tag, os_name, arch)}")
    pointer = read("latest.json")
    if pointer and json.loads(pointer).get("version") != tag:
        problems.append("latest.json does not name this release")
    return problems


# ------------------------------------------------------------------------------------- cli


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("sums", help="write checksums.txt for the archives of --version in --out")
    s.add_argument("--version", required=True, help="the release tag, such as v0.2.0")
    s.add_argument("--out", type=Path, default=Path("dist"))
    g = sub.add_parser("sign", help="sign the release in --out")
    g.add_argument("--version", required=True, help="the release tag, such as v0.2.0")
    g.add_argument("--out", type=Path, default=Path("dist"))
    g.add_argument("--base", default=DEFAULT_BASE, help="where the CDN serves it")
    g.add_argument("--notes", type=Path, help="a file of release notes for the manifest")
    g.add_argument(
        "--test-key", action="store_true", help="accept a key Flockdeck does not trust (tests only)"
    )
    sub.add_parser("keys", help="print the public keys this tool trusts, raw base64, one per line")
    v = sub.add_parser("verify", help="check the signed release in --out as the app would")
    v.add_argument("--version", required=True)
    v.add_argument("--out", type=Path, default=Path("dist"))
    args = parser.parse_args(argv)
    try:
        if args.command == "keys":
            for key in trusted_keys():
                print(base64.b64encode(raw_public(key)).decode())
        elif args.command == "sums":
            text = write_sums(args.out, args.version)
            print(text, end="")
        elif args.command == "sign":
            run_sign(
                args.out,
                args.version,
                key_text=os.environ.get(SIGNING_KEY_ENV, ""),
                base=args.base,
                notes=args.notes,
                any_key=args.test_key,
            )
            print(f"signed {args.version}: signatures, manifest.json, latest.json in {args.out}")
        else:
            problems = run_verify(args.out, args.version)
            for p in problems:
                print("FAIL", p)
            if problems:
                return 1
            print(f"{args.version} verifies against Flockdeck's release keys")
    except ReleaseError as exc:
        print(f"release: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
