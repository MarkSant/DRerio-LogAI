"""Zone Reuse Dialog - Ask if user wants to reuse existing zones.

This dialog is shown when starting a new recording session and zones
already exist from a previous recording. Allows user to reuse or redefine.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tkinter import Misc

    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.project.zone_manager import ZoneData


class ZoneReuseDialog:
    """Dialog for asking if user wants to reuse existing zones.

    Used in live recording workflow when zones already exist from
    previous recordings in the same session.

    Returns:
        dict with 'reuse' key: True to reuse, False to redefine
    """

    def __init__(self, parent: Misc, zone_data: ZoneData, project_manager: ProjectManager):
        """Initialize the zone reuse dialog.

        Args:
            parent: Parent Tkinter widget (typically root window)
            zone_data: Existing zone data to potentially reuse
            project_manager: ProjectManager for accessing zone metadata
        """
        self.parent = parent
        self.zone_data = zone_data
        self.project_manager = project_manager
        self.result: dict[str, bool] | None = None

        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Reutilizar Zonas Existentes?")
        self.dialog.transient(parent.winfo_toplevel())
        self.dialog.grab_set()

        # Build UI first, THEN size the window to fit its content. A fixed
        # 500x350 geometry clipped the bottom buttons (their text was cut off
        # vertically) whenever title + message + info frame + buttons exceeded
        # 350 px under the app's ttkbootstrap theme. Sizing to the requested
        # size guarantees every widget — buttons included — is fully visible.
        self._create_widgets()
        self._size_and_center_dialog()

    def _size_and_center_dialog(self):
        """Size the dialog to fit its content and center it on screen."""
        self.dialog.update_idletasks()
        width = max(500, self.dialog.winfo_reqwidth())
        height = self.dialog.winfo_reqheight()
        x = (self.dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (height // 2)
        self.dialog.geometry(f"{width}x{height}+{x}+{y}")
        # Lock the auto-computed size (no manual resize needed).
        self.dialog.resizable(False, False)

    def _create_widgets(self):
        """Create dialog widgets."""
        # Main container
        main_frame = ttk.Frame(self.dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Title
        title_label = ttk.Label(
            main_frame, text="Reutilizar Zonas Existentes?", font=("Segoe UI", 12, "bold")
        )
        title_label.pack(pady=(0, 15))

        # Message
        message_label = ttk.Label(
            main_frame,
            text=(
                "Zonas já foram definidas anteriormente.\n\n"
                "Deseja reutilizar para esta gravação?\n"
                "(Use se o aquário não foi movido)"
            ),
            font=("Segoe UI", 10),
            justify=tk.CENTER,
        )
        message_label.pack(pady=(0, 15))

        # Zone info frame
        info_frame = ttk.LabelFrame(main_frame, text="Informações das Zonas", padding=10)
        info_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        # Zone details
        self._create_zone_info(info_frame)

        # Buttons. The dialog auto-sizes to its content (see
        # _size_and_center_dialog), so the buttons are never clipped by a
        # too-short window. Keep plain ttk.Buttons for theme consistency.
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side=tk.BOTTOM, pady=(15, 0))

        redefine_btn = ttk.Button(
            button_frame, text="Redefinir", command=self._on_redefine, width=15
        )
        redefine_btn.pack(side=tk.LEFT, padx=5)

        reuse_btn = ttk.Button(button_frame, text="Reutilizar", command=self._on_reuse, width=15)
        reuse_btn.pack(side=tk.LEFT, padx=5)

        # Bind keys
        self.dialog.bind("<Return>", lambda e: self._on_reuse())
        self.dialog.bind("<Escape>", lambda e: self._on_redefine())

    def _create_zone_info(self, parent_frame: ttk.LabelFrame):
        """Create zone information display.

        Args:
            parent_frame: Parent frame to add info to
        """
        # Arena polygon info
        polygon = self.zone_data.polygon
        num_vertices = len(polygon) if polygon else 0

        arena_label = ttk.Label(
            parent_frame, text=f"✓ Arena Principal: {num_vertices} vértices", font=("Segoe UI", 9)
        )
        arena_label.pack(anchor=tk.W, pady=2)

        # ROI count - use roi_polygons attribute
        roi_count = len(self.zone_data.roi_polygons) if self.zone_data.roi_polygons else 0
        roi_label = ttk.Label(
            parent_frame, text=f"✓ ROIs definidas: {roi_count}", font=("Segoe UI", 9)
        )
        roi_label.pack(anchor=tk.W, pady=2)

        # Calibration info - Get from project calibration data
        width_cm = None
        height_cm = None
        if self.project_manager and self.project_manager.project_data:
            calibration = self.project_manager.project_data.get("calibration", {})
            width_cm = calibration.get("aquarium_width_cm")
            height_cm = calibration.get("aquarium_height_cm")

        if width_cm and height_cm:
            calib_text = f"✓ Calibrado: {width_cm:.1f} x {height_cm:.1f} cm"
        else:
            calib_text = "○ Calibração métrica: Não definida"

        calib_label = ttk.Label(parent_frame, text=calib_text, font=("Segoe UI", 9))
        calib_label.pack(anchor=tk.W, pady=2)

        # Detection method (if available in metadata)
        metadata = getattr(self.zone_data, "metadata", {})
        if metadata:
            method = metadata.get("detection_method", "manual")
            method_text = "Auto-detectado" if method == "auto" else "Desenhado manualmente"

            method_label = ttk.Label(
                parent_frame,
                text=f"• Método: {method_text}",
                font=("Segoe UI", 9),
                foreground="gray",
            )
            method_label.pack(anchor=tk.W, pady=2)

        # Warning if no calibration - use the values we retrieved above
        if not (width_cm and height_cm):
            warning_label = ttk.Label(
                parent_frame,
                text="⚠ Recomenda-se calibração métrica para análises precisas",
                font=("Segoe UI", 8),
                foreground="orange",
            )
            warning_label.pack(anchor=tk.W, pady=(10, 0))

    def _on_reuse(self):
        """Handle reuse button click."""
        self.result = {"reuse": True}
        self.dialog.destroy()

    def _on_redefine(self):
        """Handle redefine button click."""
        self.result = {"reuse": False}
        self.dialog.destroy()

    def show(self) -> dict[str, bool] | None:
        """Show the dialog and wait for user response.

        Returns:
            dict with 'reuse' key (True or False), or None if dialog closed
        """
        self.dialog.wait_window()
        return self.result
