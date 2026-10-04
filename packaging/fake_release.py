"""A signed release made of random bytes, for testing the release tooling.

    python packaging/fake_release.py DIR [--version v0.3.0]

Writes six fake archives and everything release.py signs (checksums.txt, manifest.json, latest.json
and the signatures) into DIR, signed with a throwaway key, and prints that key's public half, raw
base64, so that a checker can be told to trust it. Nothing here is a real release.
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
from datetime import datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release  # noqa: E402


def private_pem(key: Ed25519PrivateKey) -> str:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def make_release(
    out: Path,
    tag: str = "v0.3.0",
    *,
    key: Ed25519PrivateKey | None = None,
    notes: str = "A fake release.",
    now: datetime | None = None,
    size: int = 2048,
) -> tuple[Ed25519PrivateKey, str]:
    """Returns the key and its public half (raw, base64)."""
    out.mkdir(parents=True, exist_ok=True)
    key = key or Ed25519PrivateKey.generate()
    for i, (os_name, arch) in enumerate(release.PLATFORMS):
        (out / release.archive_name(tag, os_name, arch)).write_bytes(os.urandom(size + i))
    release.write_sums(out)
    notes_file = out / "notes.md"
    notes_file.write_text(notes + "\n", encoding="utf-8")
    release.run_sign(out, tag, key_text=private_pem(key), notes=notes_file, any_key=True, now=now)
    notes_file.unlink()
    public = base64.b64encode(release.raw_public(key.public_key())).decode()
    return key, public


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("--version", default="v0.3.0")
    args = parser.parse_args()
    _, public = make_release(args.out, args.version)
    print(public)
    return 0


if __name__ == "__main__":
    sys.exit(main())
