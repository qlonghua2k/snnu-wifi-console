from __future__ import annotations

import ctypes
import subprocess
import sys
from pathlib import Path


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> bool:
    params = subprocess.list2cmdline(sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv)
    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        sys.executable,
        params,
        str(Path.cwd()),
        1,
    )
    return int(result) > 32
