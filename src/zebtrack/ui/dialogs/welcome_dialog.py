"""Getting-started window shown once the main window is up.

The first thing a new operator saw was a full application with no indication of
what to do first -- and, in particular, no hint that the six detector models
need assigning to roles before tracking behaves sensibly. Nothing in the menu
bar led to the model configuration panel either; it was reachable only from a
button inside a project view.

This window closes that gap. It explains the models, the roles they fill and
when OpenVINO is worth enabling, then offers to open the panel where those
choices are made.

**The OpenVINO advice is read off the machine, not written in the abstract.**
"Use OpenVINO when you have no NVIDIA card" is true but useless to someone who
does not know what they have; :func:`zebtrack.utils.hardware_detection.get_hardware_summary`
already answers that question, and the bootstrapper has run it by the time this
window opens.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

import structlog

from zebtrack.i18n import _

log = structlog.get_logger()

_WRAP_PX = 560


def _hardware_advice() -> tuple[str, str]:
    """Describe this machine's accelerator and what it implies for OpenVINO.

    Returns:
        ``(headline, detail)``. Both are already translated. On any detection
        failure the pair degrades to generic guidance rather than raising: a
        getting-started window is not worth blocking startup over.
    """
    try:
        from zebtrack.utils.hardware_detection import get_hardware_summary

        summary = get_hardware_summary()
    except Exception:
        log.debug("welcome.hardware_summary.suppressed", exc_info=True)
        return (
            _("Acceleration"),
            _(
                "OpenVINO speeds up Intel processors, integrated graphics and NPUs. "
                "On a machine with an NVIDIA card, PyTorch with CUDA is usually "
                "faster and OpenVINO is not worth enabling."
            ),
        )

    if summary.get("cuda_available"):
        return (
            _("An NVIDIA GPU was detected"),
            _(
                "PyTorch with CUDA will normally be the fastest option here, so "
                "you can leave OpenVINO off. It exists for machines without an "
                "NVIDIA card, where it moves the work onto the Intel CPU, "
                "integrated graphics or NPU instead."
            ),
        )

    devices = summary.get("openvino_devices") or []
    if summary.get("openvino_available"):
        named = ", ".join(str(device) for device in devices) or _("CPU")
        return (
            _("No NVIDIA GPU — OpenVINO is the fast path here"),
            _(
                "Without a CUDA card, OpenVINO is what makes tracking fast on this "
                "machine. It can use: {devices}. Enable it in the model settings "
                "and convert the models you plan to use; conversion happens once "
                "and is cached."
            ).format(devices=named),
        )

    return (
        _("No hardware acceleration was detected"),
        _(
            "Tracking will run on the CPU through PyTorch. It works, but expect it "
            "to be slower than on a machine with an NVIDIA card or Intel "
            "acceleration."
        ),
    )


class WelcomeDialog:
    """Modal getting-started window.

    Built as a plain ``Toplevel`` in the style of
    :mod:`zebtrack.ui.language_dialog` rather than through ``DialogManager``:
    it has one job, no validation and no project state, and it must survive
    being opened before any project exists.
    """

    def __init__(self, parent: Any, *, on_open_model_settings: Any = None) -> None:
        """Build and show the window.

        Args:
            parent: The main window. It is already mapped when this runs, so
                ``transient`` is safe -- unlike the first-launch language
                chooser, whose master is still withdrawn.
            on_open_model_settings: Called when the user chooses to open the
                model configuration panel. Invoked after this window closes,
                so the panel is not fighting a grab.
        """
        self._on_open_model_settings = on_open_model_settings
        self.opened_model_settings = False

        self.window = tk.Toplevel(parent)
        self.window.title(_("Getting started"))
        self.window.transient(parent)
        self.window.resizable(False, False)

        self.dont_show_again = tk.BooleanVar(master=self.window, value=False)

        frame = ttk.Frame(self.window, padding=20)
        frame.pack(fill="both", expand=True)

        self._build_body(frame)
        self._build_buttons(frame)

        self.window.protocol("WM_DELETE_WINDOW", self._close)
        self.window.bind("<Escape>", lambda _event: self._close())

        self._center_on(parent)
        self.window.grab_set()
        self.window.focus_force()
        log.info("welcome.shown")

    def _build_body(self, frame: ttk.Frame) -> None:
        ttk.Label(
            frame,
            text=_("Welcome to DRerio LogAI"),
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            frame,
            text=_("One thing is worth setting up before your first analysis."),
            wraplength=_WRAP_PX,
            justify="left",
        ).pack(anchor="w", pady=(4, 14))

        models = ttk.LabelFrame(frame, text=_("The detector models"), padding=10)
        models.pack(fill="x", pady=(0, 10))
        ttk.Label(
            models,
            text=_(
                "Six models are installed. Four are specialists, trained for one "
                "camera angle each: segmentation and detection, for a lateral view "
                "and for a top-down view. The other two are generalists that work "
                "from any angle but with less precision.\n\n"
                "You assign a model to each of four roles — detecting the aquarium "
                "and detecting the animal, by segmentation and by bounding box. "
                "The specialists are pre-assigned; pick the pair that matches how "
                "your camera is mounted."
            ),
            wraplength=_WRAP_PX,
            justify="left",
        ).pack(anchor="w")

        headline, detail = _hardware_advice()
        hardware = ttk.LabelFrame(frame, text=_("OpenVINO"), padding=10)
        hardware.pack(fill="x", pady=(0, 10))
        ttk.Label(hardware, text=headline, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        ttk.Label(hardware, text=detail, wraplength=_WRAP_PX, justify="left").pack(
            anchor="w", pady=(2, 0)
        )

        ttk.Label(
            frame,
            text=_("All of this lives in Settings > Model settings, at any time."),
            wraplength=_WRAP_PX,
            justify="left",
            foreground="#666666",
        ).pack(anchor="w", pady=(0, 10))

    def _build_buttons(self, frame: ttk.Frame) -> None:
        ttk.Checkbutton(
            frame,
            text=_("Do not show this again"),
            variable=self.dont_show_again,
        ).pack(anchor="w", pady=(0, 10))

        row = ttk.Frame(frame)
        row.pack(fill="x")
        ttk.Button(row, text=_("Not now"), command=self._close).pack(side="right")
        ttk.Button(
            row,
            text=_("Open model settings"),
            command=self._open_model_settings,
        ).pack(side="right", padx=(0, 8))

    def _open_model_settings(self) -> None:
        self.opened_model_settings = True
        self._close()
        if self._on_open_model_settings is not None:
            self._on_open_model_settings()

    def _close(self) -> None:
        if self.dont_show_again.get():
            _persist_dismissal()
        try:
            self.window.grab_release()
        except tk.TclError:
            log.debug("welcome.grab_release.suppressed", exc_info=True)
        self.window.destroy()

    def _center_on(self, parent: Any) -> None:
        """Centre over the main window, falling back to the screen."""
        self.window.update_idletasks()
        width = self.window.winfo_width()
        height = self.window.winfo_height()
        try:
            x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
        except tk.TclError:
            log.debug("welcome.center_on_parent.suppressed", exc_info=True)
            x = (self.window.winfo_screenwidth() - width) // 2
            y = (self.window.winfo_screenheight() - height) // 2
        self.window.geometry(f"+{max(x, 0)}+{max(y, 0)}")


def _persist_dismissal() -> None:
    """Record the preference, writing only ``ui.show_welcome``.

    Uses ``write_local_override`` rather than ``save_settings``: the latter
    dumps the whole resolved Settings tree into ``config.local.yaml``, freezing
    every current default and permanently defeating the layered
    ``config.yaml`` -> ``config.local.yaml`` merge for that installation.

    A write failure degrades to showing the window again next launch, which is
    a minor annoyance; raising here would take down the main window instead.
    """
    try:
        from zebtrack.settings import write_local_override

        write_local_override({"ui": {"show_welcome": False}})
        log.info("welcome.dismissed_permanently")
    except Exception:
        log.warning("welcome.dismiss_persist_failed", exc_info=True)


def should_show_welcome(settings_obj: Any) -> bool:
    """Whether the getting-started window is due.

    Type-checked rather than trusted: a ``MagicMock`` settings object answers
    every attribute truthily, and this decides whether a modal window appears
    over the main window.
    """
    ui = getattr(settings_obj, "ui", None)
    if ui is None:
        return False
    value = getattr(ui, "show_welcome", None)
    return value is True
