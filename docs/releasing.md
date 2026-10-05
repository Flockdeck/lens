# Releasing lens

lens is released the way Flockdeck is: a signed release on GitHub, and the same files on
dl.flockdeck.ai, the DigitalOcean Space and CDN that Flockdeck downloads its own updates from.
Flockdeck's copy of the process is in its `release.yml`, `scripts/publish-downloads.sh` and
`cmd/release`. Ours follows them file for file: `release.yaml`, `packaging/publish-downloads.sh`
and `packaging/release.py`.

## Making a release

1. Write `docs/releases/vX.Y.Z.md`. It is the GitHub release text and goes into the signed
   manifest. A candidate tag (`vX.Y.Z-rc.1`) needs no notes.
2. Merge that to `main` and let CI pass.
3. Tag the merge commit and push the tag: `git tag v0.2.0 && git push origin v0.2.0`.

Pushing the tag is the approval. There is no reviewer gate; the protection is that a pushed tag
cannot be moved or deleted (a ruleset in terrawost) and that the signing key and the bucket's
credentials are only in the `release` environment, which only a `v*` tag can deploy to.

The release workflow then:

1. runs all of CI;
2. checks the tag is `vMAJOR.MINOR.PATCH` (or `-rc.N`) and that the notes file exists;
3. builds the program on all six platforms and runs `packaging/smoke.py` against each;
4. merges the archives and writes `checksums.txt`, signs it, writes and signs `manifest.json`,
   and writes `latest.json`, then verifies all of that against Flockdeck's keys;
5. publishes the release on GitHub (a `-rc` tag as a pre-release; a release older than the newest
   one is not marked latest);
6. checks that the CDN's secrets are set, and uploads to the CDN.

GitHub comes before the CDN on purpose. A run that stops after step 5 has still made a release,
one that is only missing from the CDN. Run the workflow again from the tag (`workflow_dispatch`)
to finish it.

## What is on the CDN

```text
https://dl.flockdeck.ai/lens/latest.json                  {"version":"v0.2.0"}, the only file that changes
https://dl.flockdeck.ai/lens/latest/lens_linux_amd64.tar.gz   download buttons, without the version
https://dl.flockdeck.ai/lens/v0.2.0/lens_v0.2.0_<os>_<arch>.tar.gz   (.zip on Windows)
https://dl.flockdeck.ai/lens/v0.2.0/checksums.txt
https://dl.flockdeck.ai/lens/v0.2.0/checksums.txt.sig
https://dl.flockdeck.ai/lens/v0.2.0/manifest.json
https://dl.flockdeck.ai/lens/v0.2.0/manifest.json.sig
```

`os` is `linux`, `darwin` or `windows` and `arch` is `amd64` or `arm64`. Everything under a version
is cached for a year and is never replaced. `latest.json` and `latest/` are cached for a minute.
The formats are Flockdeck's own, so its updater code can read them: `checksums.txt` is
`<sha256>  <file>` per line; a `.sig` is the Ed25519 signature of that file's exact bytes in
base64 on one line; `manifest.json` lists every file with its URL, SHA-256 and size.

`packaging/publish-downloads.sh` is where the care is, since a published version cannot be taken
back. It uploads a version's files first, reads one back through the public address, and only then
moves `latest/` and, last of all, `latest.json`. It refuses to publish a version whose files differ
from what is already there. It leaves `latest.json` alone for a pre-release, and for a release
older than the one `latest.json` already names. It stops if the bucket can be listed by anyone. It
treats a store it cannot read as unknown, never as empty. `tests/packaging/test_publish.py` runs it
against a fake S3 server with the real `aws` CLI, and checks each of these by breaking the script.

## Trust

Releases are signed with Flockdeck's release key (Ed25519), not a key of lens's own. Flockdeck
installs lens and checks `checksums.txt.sig` against the keys compiled into it, which are that key
and its standby. A lens key would need a Flockdeck release before anything signed by it was
accepted.

That has a consequence worth knowing. The private half is in the `release` environment of this
repository, as `LENS_SIGNING_KEY`, so a leak from this repository can sign Flockdeck releases too,
and the other way round. The terrawost change that makes the secret
(`svc/flockdeck-site/lens_release.tf`) says the same.

`packaging/release.py` refuses to sign with any other key, so that it cannot produce files that
Flockdeck would reject. If Flockdeck rotates its key, `PRIMARY_PUBLIC_KEY` and
`STANDBY_PUBLIC_KEY` in that file must follow. The `flockdeck-compat` job in CI compares them with
Flockdeck's `main` on every run and fails when they differ. The same job runs a signed lens release
through Flockdeck's updater checks (`CheckManifest`, `VerifyAny`, `CheckPointer`), using a copy of
the Go test in `packaging/flockdeck_compat_test.go.txt`.

The builds themselves are not code-signed: Windows shows a SmartScreen warning for a downloaded
program, and macOS Gatekeeper blocks one that came through a browser. Flockdeck does not sign or
notarize its own either.

## One-time setup, outside this repository

Nothing below is done by the workflows, and none of it can be, since it needs the infrastructure
repository (terrawost, applied by its owner).

Apply the `lens-release-signing` branch of terrawost (`svc/flockdeck-site/lens_release.tf`). It
makes, on `Flockdeck/lens`:

- the `release` environment, restricted to `v*` tags;
- its secret `LENS_SIGNING_KEY`, the value of Flockdeck's release key;
- the four CDN secrets `DO_SPACES_KEY`, `DO_SPACES_SECRET`, `DO_SPACES_BUCKET` and
  `DO_SPACES_REGION`, from the same `flockdeck-downloads-ci` key and bucket that Flockdeck's own
  release environment gets;
- a ruleset that stops a pushed `v*` tag being moved or deleted.

The GitHub token the workspace uses needs Administration and Environments read and write, and
Secrets read and write, on `Flockdeck/lens`. Until this is applied a tag still builds, signs
nothing, and stops at the signing step, naming the missing key.

DigitalOcean Spaces keys are per bucket, not per prefix, so that key can write the whole bucket,
including Flockdeck's own releases and its `latest.json`. A compromised lens release run could
replace them. The signature limits the harm (files without a valid signature are refused by
Flockdeck), but the signing key is in the same environment. If that is not acceptable, the other
choice is a separate bucket for lens behind its own path or host, at the cost of not sharing the
CDN.

No DNS change is needed. `dl.flockdeck.ai` already exists.

## Running a step by hand

```sh
python packaging/release.py sums --out dist          # after putting the six archives in dist/
LENS_SIGNING_KEY=... python packaging/release.py sign --version v0.2.0 --out dist --notes docs/releases/v0.2.0.md
python packaging/release.py verify --version v0.2.0 --out dist
DO_SPACES_KEY=... DO_SPACES_SECRET=... DO_SPACES_BUCKET=flockdeck-downloads DO_SPACES_REGION=lon1 \
  sh packaging/publish-downloads.sh v0.2.0 dist
```

The publish script works against any S3-compatible store (`DO_SPACES_ENDPOINT`, `LENS_DL_URL`), and
with `LENS_ALLOW_LISTABLE=1` against one that lists its bucket, which only a local test store does.

## What there is not

- No way to withdraw a release. Flockdeck's updater reads `recalled.json` and `releases.json`, but
  neither repository has code that writes them; removing a published file means deleting it from
  the bucket by hand and purging the CDN.
- No code signing or notarization of the executables, and no software bill of materials or
  provenance attestation.
- The first real release has not been made, so the workflow has only been run up to the point where
  it needs the `release` environment.
