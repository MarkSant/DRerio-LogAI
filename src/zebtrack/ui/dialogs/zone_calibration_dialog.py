"""Zone Calibration Dialog - Method selection for zone definition.

This dialog allows users to choose between automatic detection and manual drawing
when defining zones for live camera recording sessions.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from zebtrack.i18n import _

if TYPE_CHECKING:
    pass


class ZoneCalibrationDialog:
    """Dialog for selecting zone definition method (auto-detection vs manual).

    Used in live recording workflow to ask user how they want to define
    the aquarium zone before starting recording.

    Returns:
        dict with 'method' key: 'auto', 'manual', or None if cancelled
    """

    def __init__(self, parent: tk.Tk | tk.Toplevel):
        """Initialize the zone calibration dialog.

        Args:
            parent: Parent Tkinter widget (typically root window)
        """
        self.parent = parent
        self.result: dict[str, str] | None = None

        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(_("Zone Configuration"))
        self.dialog.geometry("450x280")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)  # type: ignore[call-overload]
        self.dialog.grab_set()

        # Center dialog
        self._center_dialog()

        # Build UI
        self._create_widgets()

    def _center_dialog(self):
        """Center the dialog on screen."""
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (450 // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (280 // 2)
        self.dialog.geometry(f"+{x}+{y}")

    def _create_widgets(self):
        """Create dialog widgets."""
        # Main container
        main_frame = ttk.Frame(self.dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Title
        title_label = ttk.Label(
            main_frame,
            text=_("Zone Configuration for Recording"),
            font=("Segoe UI", 12, "bold"),
        )
        title_label.pack(pady=(0, 15))

        # Question
        question_label = ttk.Label(
            main_frame,
            text=_("How do you want to define the aquarium zone?"),
            font=("Segoe UI", 10),
        )
        question_label.pack(pady=(0, 20))

        # Radio buttons
        self.method_var = tk.StringVar(value="auto")

        # Auto-detection option
        auto_frame = ttk.Frame(main_frame)
        auto_frame.pack(fill=tk.X, pady=5)

        auto_radio = ttk.Radiobutton(
            auto_frame,
            text=_("Auto-detection (recommended)"),
            variable=self.method_var,
            value="auto",
        )
        auto_radio.pack(anchor=tk.W)

        auto_desc = ttk.Label(
            auto_frame,
            text=_("Will try to detect the aquarium automatically over 10 frames"),
            font=("Segoe UI", 9),
            foreground="gray",
        )
        auto_desc.pack(anchor=tk.W, padx=(25, 0))

        # Manual drawing option
        manual_frame = ttk.Frame(main_frame)
        manual_frame.pack(fill=tk.X, pady=10)

        manual_radio = ttk.Radiobutton(
            manual_frame,
            text=_("Manual Drawing"),
            variable=self.method_var,
            value="manual",
        )
        manual_radio.pack(anchor=tk.W)

        manual_desc = ttk.Label(
            manual_frame,
            text=_("You will draw the aquarium polygon manually"),
            font=("Segoe UI", 9),
            foreground="gray",
        )
        manual_desc.pack(anchor=tk.W, padx=(25, 0))

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side=tk.BOTTOM, pady=(20, 0))

        cancel_btn = ttk.Button(button_frame, text=_("Cancel"), command=self._on_cancel, width=12)
        cancel_btn.pack(side=tk.LEFT, padx=5)

        proceed_btn = ttk.Button(
            button_frame, text=_("Proceed"), command=self._on_proceed, width=12
        )
        proceed_btn.pack(side=tk.LEFT, padx=5)

        # Bind Enter key to proceed
        self.dialog.bind("<Return>", lambda e: self._on_proceed())
        self.dialog.bind("<Escape>", lambda e: self._on_cancel())

    def _on_proceed(self):
        """Handle proceed button click."""
        method = self.method_var.get()
        self.result = {"method": method}
        self.dialog.destroy()

    def _on_cancel(self):
        """Handle cancel button click."""
        self.result = None
        self.dialog.destroy()

    def show(self) -> dict[str, str] | None:
        """Show the dialog and wait for user response.

        Returns:
            dict with 'method' key ('auto' or 'manual'), or None if cancelled
        """
        self.dialog.wait_window()
        return self.result
