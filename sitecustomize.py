"""Project-level sitecustomize hooks used during tests.

This module configures Tcl/Tk search paths so that headless environments can
instantiate Tkinter widgets without needing manual environment setup.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from pathlib import Path


def _iter_candidate_roots() -> Iterable[Path]:
    """Yield potential roots that may contain Tcl/Tk resources."""
    seen: set[Path] = set()
    for raw_path in (sys.base_prefix, sys.prefix, Path(sys.executable).parent):
        try:
            path = Path(raw_path).resolve()
        except OSError:
            continue
        if path not in seen:
            seen.add(path)
            yield path


def _try_configure_from_root(root: Path, versions: tuple[str, ...]) -> bool:
    """Attempt to configure Tcl/Tk environment variables from a given root."""

    def _configure_from_dir(base_dir: Path) -> bool:
        if not base_dir.exists():
            return False

        collected_paths: list[str] = []

        for version in versions:
            tcl_dir = base_dir / f"tcl{version}"
            tk_dir = base_dir / f"tk{version}"

            if not os.environ.get("TCL_LIBRARY") and tcl_dir.exists():
                normalized = str(tcl_dir).replace("\\", "/")
                os.environ["TCL_LIBRARY"] = normalized
                collected_paths.append(normalized)

            if not os.environ.get("TK_LIBRARY") and tk_dir.exists():
                normalized = str(tk_dir).replace("\\", "/")
                os.environ["TK_LIBRARY"] = normalized
                collected_paths.append(normalized)

            if os.environ.get("TCL_LIBRARY") and os.environ.get("TK_LIBRARY"):
                break

        # Fall back to the first matching subdirectory if versioned ones were not found.
        if not os.environ.get("TCL_LIBRARY"):
            for child in sorted(base_dir.glob("tcl*")):
                if child.is_dir():
                    normalized = str(child).replace("\\", "/")
                    os.environ["TCL_LIBRARY"] = normalized
                    collected_paths.append(normalized)
                    break

        if not os.environ.get("TK_LIBRARY"):
            for child in sorted(base_dir.glob("tk*")):
                if child.is_dir():
                    normalized = str(child).replace("\\", "/")
                    os.environ["TK_LIBRARY"] = normalized
                    collected_paths.append(normalized)
                    break

        if collected_paths:
            current = os.environ.get("TCLLIBPATH", "").split()
            for path in collected_paths:
                if path not in current:
                    current.append(path)
            os.environ["TCLLIBPATH"] = " ".join(filter(None, current))

        return bool(os.environ.get("TCL_LIBRARY") and os.environ.get("TK_LIBRARY"))

    if _configure_from_dir(root / "tcl"):
        return True
    if _configure_from_dir(root / "Lib" / "tcl"):
        return True
    return False


def _ensure_windows_dll_access():
    if os.name != "nt":
        return

    add_dll_directory = getattr(os, "add_dll_directory", None)
    if add_dll_directory is None:
        return

    candidate_subdirs = ("DLLs", "Library\\bin", "bin")
    seen: set[Path] = set()

    for root in _iter_candidate_roots():
        for sub in candidate_subdirs:
            path = (root / sub).resolve()
            if path in seen or not path.exists():
                continue
            try:
                add_dll_directory(str(path))
                seen.add(path)
            except FileNotFoundError:
                continue


def _ensure_tk_env():
    """Ensure Tcl/Tk environment variables are set when available."""
    if os.environ.get("TCL_LIBRARY") and os.environ.get("TK_LIBRARY"):
        return

    version_candidates = ("8.7", "8.6", "8.5")

    for candidate_root in _iter_candidate_roots():
        try:
            if _try_configure_from_root(candidate_root, version_candidates):
                break
        except Exception:
            # Silently ignore unexpected issues so the import never fails.
            continue


_ensure_windows_dll_access()
_ensure_tk_env()


def _patch_tkinter():
    try:
        import tkinter  # type: ignore
    except Exception:
        return

    original_tk = getattr(tkinter, "Tk", None)
    if not callable(original_tk):
        return

    if getattr(original_tk, "__name__", "") == "_patched_Tk":
        return

    def _patched_Tk(*args, **kwargs):
        _ensure_tk_env()
        return original_tk(*args, **kwargs)

    _patched_Tk.__name__ = "_patched_Tk"
    tkinter.Tk = _patched_Tk  # type: ignore[attr-defined]


_patch_tkinter()

__all__ = []
