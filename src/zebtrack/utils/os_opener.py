"""Cross-platform opener for files and folders.

Consolidates the six duplicated open-path patterns scattered across UI
components into one validated, injection-safe utility.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import structlog

log = structlog.get_logger()


def open_path(path: str | Path) -> None:
    """Open *path* (file or directory) with the default OS handler.

    - Windows: ``os.startfile``
    - macOS:   ``open``
    - Linux:   ``xdg-open``

    The path is resolved and validated before being passed to the OS to
    prevent command injection via crafted file names.

    Args:
        path: Filesystem path to open.

    Raises:
        FileNotFoundError: If *path* does not exist.
        OSError: If the platform has no known open mechanism.
    """
    resolved = Path(path).resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Path does not exist: {resolved}")

    target = str(resolved)
    log.debug("os_opener.open_path", path=target, platform=sys.platform)

    if sys.platform == "win32":
        startfile = getattr(os, "startfile", None)
        if callable(startfile):
            startfile(target)
        else:
            raise OSError("os.startfile not available on this platform")
    elif sys.platform == "darwin":
        subprocess.Popen(["open", target])
    else:
        subprocess.Popen(["xdg-open", target])
