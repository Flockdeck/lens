# Build and release steps

* [publish-downloads.sh](publish-downloads.md) - Uploads a signed release to the download bucket in an order that never names files that are not there yet.
* [PyInstaller spec](pyinstaller-spec.md) - packaging/lens.spec builds one self-contained console executable per platform.
* [Release archives](release-archives.md) - Each platform build produces lens_<tag>_<os>_<arch>.tar.gz or .zip holding the binary and legal files.
* [Third-party notices generation](third-party-notices.md) - packaging/third_party_notices.py writes THIRD-PARTY-NOTICES.md from the licences of everything that ships in the binary.
* [Version stamping](version-stamp.md) - The build rewrites __version__ in _version.py from the release tag, then checks the binary reports it.
