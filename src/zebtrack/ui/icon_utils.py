"""Utilities for loading DRerio LogAI application icons."""

import tkinter as tk
from pathlib import Path

import structlog

log = structlog.get_logger()


def get_icon_path() -> Path | None:
    """
    Obtém o caminho para o ícone da aplicação (.ico).

    Returns:
        Path para o ícone ou None se não encontrado.
    """
    # Try to locate the asset relative to the package
    try:
        # Path relative to this module (zebtrack/ui/icon_utils.py)
        icon_path = Path(__file__).parent / "assets" / "drerio_logai.ico"

        if icon_path.exists():
            log.debug("icon.path.found", path=str(icon_path))
            return icon_path

        # Fallback: path relative to the working directory (development)
        icon_path_dev = Path("src/zebtrack/ui/assets/drerio_logai.ico")
        if icon_path_dev.exists():
            log.debug("icon.path.found_dev", path=str(icon_path_dev))
            return icon_path_dev

        log.warning("icon.path.not_found", attempted_paths=[str(icon_path), str(icon_path_dev)])
        return None

    except Exception as e:
        log.warning("icon.path.error", error=str(e))
        return None


def set_window_icon(window) -> None:
    """
    Define o ícone para uma janela Tkinter.

    Args:
        window: Instância de tk.Tk ou tk.Toplevel
    """
    icon_path = get_icon_path()

    if icon_path is None:
        log.info("icon.set.skipped", reason="Icon file not found")
        return

    # Check if window still exists and is valid
    try:
        if not window.winfo_exists():
            log.debug("icon.set.skipped", reason="Window no longer exists")
            return
    except Exception:
        # Window might be in invalid state, skip silently
        log.debug("icon.set.skipped", reason="Window in invalid state")
        return

    try:
        window.iconbitmap(default=str(icon_path))
        log.info(
            "icon.set.success",
            window_title=window.title() if hasattr(window, "title") else "unknown",
        )
    except tk.TclError as e:
        # Tkinter-specific errors (e.g., bad window path) - downgrade to debug
        log.debug("icon.set.tk_error", error=str(e))
    except Exception as e:
        # Unexpected errors - keep as warning
        log.warning("icon.set.failed", error=str(e), path=str(icon_path))
