"""The version. The release workflow writes the tag into this file before building."""

__version__ = "0.1.0"


def app_version() -> str:
    return __version__
