from __future__ import annotations

from typing import Any, Callable


def _try_actions(window: Any, actions: tuple[Callable[[], None], ...]) -> bool:
    for action in actions:
        try:
            action()
            return True
        except Exception:
            continue
    return False


def maximize_window(window: Any) -> None:
    """Attempt to maximize a Tk window across platforms."""
    try:
        window.update_idletasks()
    except Exception:
        pass

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
        pass


def schedule_maximize(window: Any) -> None:
    """Schedule maximization after the window is mapped."""
    try:
        window.after(0, lambda: maximize_window(window))
    except Exception:
        pass


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
        pass


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
        pass
