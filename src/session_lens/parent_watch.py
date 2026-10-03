"""Stop when the process that launched us is killed.

The packaged program is a launcher that unpacks itself and runs the real program as a child
process (PyInstaller's one-file mode; on Windows a virtualenv's python.exe does the same). If
something kills the launcher outright, which is what Task Manager or another program stopping
it does, the child is not told and would go on holding the port and the database. This watches
the parent and asks the server to shut down (gracefully, with its usual drain) when it goes.

It only acts when the parent is the same program as this process, so running session-lens from
a shell or a script that exits early is unaffected.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable


def _file_name(path: str) -> str:
    return re.split(r"[\\/]", path.strip())[-1].lower()


def same_program(parent_image: str | None, own_image: str) -> bool:
    """True when two process image paths name the same program (by file name)."""
    if not parent_image or not own_image:
        return False
    return _file_name(parent_image) == _file_name(own_image)


def _windows_parent_image(pid: int) -> str | None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return None
    finally:
        kernel32.CloseHandle(handle)


def _windows_wait_for_exit(pid: int) -> None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    handle = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if not handle:
        return  # already gone
    kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)  # INFINITE
    kernel32.CloseHandle(handle)


def _unix_parent_image(pid: int) -> str | None:
    try:
        out = subprocess.run(  # noqa: S603
            ["ps", "-o", "comm=", "-p", str(pid)],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out or None


def watch_parent(on_gone: Callable[[], None]) -> bool:
    """Start watching if the parent is the same program as this one. Returns whether it did."""
    parent = os.getppid()
    if parent <= 1:
        return False
    own = sys.executable
    if sys.platform == "win32":
        image = _windows_parent_image(parent)
    else:
        image = _unix_parent_image(parent)
    if not same_program(image, own):
        return False

    def run() -> None:
        if sys.platform == "win32":
            _windows_wait_for_exit(parent)
        else:
            while os.getppid() == parent:  # reparented to init (1) or a subreaper when it dies
                time.sleep(1.0)
        on_gone()

    threading.Thread(target=run, name="parent-watch", daemon=True).start()
    return True
