# PyInstaller spec: one self-contained executable per platform.
#   uv run pyinstaller packaging/session-lens.spec --noconfirm
# Output: dist/session-lens (dist/session-lens.exe on Windows).
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).parent
src = root / "src" / "session_lens"

hidden = (
    # uvicorn picks its loop, HTTP and websocket implementations by name at run time
    collect_submodules("uvicorn")
    # the database driver and dialect are named in the URL, not imported
    + ["aiosqlite", "sqlalchemy.dialects.sqlite", "sqlalchemy.dialects.sqlite.aiosqlite"]
    + collect_submodules("alembic.ddl")
    # the migration files import these when alembic loads them
    + ["alembic.operations.ops"]
    # loaded lazily, only when ENRICHER selects them
    + ["session_lens.enrich.anthropic", "session_lens.enrich.ollama", "session_lens.enrich.mock"]
    + collect_submodules("anthropic")
)

a = Analysis(
    [str(src / "__main__.py")],
    pathex=[str(root / "src")],
    datas=[
        # the web UI, served from disk by StaticFiles
        (str(src / "web"), "session_lens/web"),
        # alembic reads these as files
        (str(src / "migrations"), "session_lens/migrations"),
    ],
    hiddenimports=hidden,
    excludes=["tkinter", "pytest", "playwright", "mypy", "ruff", "aioboto3", "botocore"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="session-lens",
    console=True,  # a terminal program: prints its address, logs to the terminal
    upx=False,  # UPX-packed binaries trip antivirus
    strip=False,
)
