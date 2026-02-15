"""Window utility functions for cross-platform Tkinter window management.

Provides platform-independent utilities for window operations such as maximizing
and centering windows across different operating systems.
"""

from __future__ import annotations

from collections.abc import Callable
from tkinter import TclError, ttk
from typing import Any, cast

import structlog

log = structlog.get_logger()

try:
    import ttkbootstrap as ttkb
except Exception:  # pragma: no cover - optional dependency
    ttkb = cast(Any, None)


def _try_actions(window: Any, actions: tuple[Callable[[], None], ...]) -> bool:
    for action in actions:
        try:
            action()
            return True
        except Exception:
            log.debug("window_utils.try_actions.action_failed", exc_info=True)
            continue
    return False


def maximize_window(window: Any) -> None:
    """Attempt to maximize a Tk window across platforms."""
    try:
        window.update_idletasks()
    except Exception:
        log.debug("window_utils.maximize.update_idletasks_failed", exc_info=True)

    def _state_zoomed() -> None:
        window.state("zoomed")

    def _attributes_zoomed() -> None:
        window.attributes("-zoomed", True)

    if _try_actions(window, (_state_zoomed, _attributes_zoomed)):
        return

    try:
        screen_w = window.winfo_screenwidth()
        screen_h = window.winfo_screenheight()
        window.geometry(f"{screen_w}x{screen_h}+0+0")
    except Exception:
        log.debug("window_utils.maximize.geometry_fallback_failed", exc_info=True)


def schedule_maximize(window: Any) -> None:
    """Schedule maximization after the window is mapped."""
    try:
        window.after(0, lambda: maximize_window(window))
    except Exception:
        log.debug("window_utils.schedule_maximize.suppressed", exc_info=True)


def reset_geometry_if_not_maximized(window: Any) -> None:
    """Reset geometry only when window isn't already maximized."""
    try:
        state = window.state()
    except Exception:
        state = None

    if state == "zoomed":
        return

    try:
        window.geometry("")
    except Exception:
        log.debug("window_utils.reset_geometry.suppressed", exc_info=True)


def set_geometry_if_not_maximized(window: Any, geometry: str) -> None:
    """Apply geometry changes only if the window isn't maximized."""
    try:
        state = window.state()
    except Exception:
        state = None

    if state == "zoomed":
        return

    try:
        window.geometry(geometry)
    except Exception:
        log.debug("window_utils.set_geometry.suppressed", exc_info=True)


def _ttkbootstrap_style_needs_reset() -> bool:
    if ttkb is None:
        return False

    try:
        from ttkbootstrap.style import Style
    except Exception:
        return False

    style = getattr(Style, "instance", None)
    if style is None:
        return False

    try:
        master = getattr(style, "master", None)
        return not (master and master.winfo_exists())
    except Exception:
        return True


def _clear_ttkbootstrap_style() -> None:
    if ttkb is None:
        return

    try:
        from ttkbootstrap.style import Style
    except Exception:
        return

    Style.instance = None


def create_scrollbar(parent: Any, **kwargs: Any):
    """Create a ttk Scrollbar resilient to destroyed Tk masters."""
    try:
        return ttk.Scrollbar(parent, **kwargs)
    except TclError as exc:
        if "application has been destroyed" not in str(exc):
            raise
        if _ttkbootstrap_style_needs_reset():
            _clear_ttkbootstrap_style()
        return ttk.Scrollbar(parent, **kwargs)
