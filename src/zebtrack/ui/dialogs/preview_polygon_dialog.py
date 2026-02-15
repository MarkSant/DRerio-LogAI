"""Preview Polygon Dialog - Show detected aquarium for approval.

This dialog displays a preview of the auto-detected aquarium polygon
overlaid on a camera frame, allowing user to approve or reject the detection.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np
from PIL import Image, ImageTk

if TYPE_CHECKING:
    from tkinter import Misc


class PreviewPolygonDialog:
    """Dialog for previewing and approving auto-detected aquarium polygon.

    Shows camera frame with detected polygon overlay. User can approve
    to use the polygon or reject to manually draw.

    Returns:
        dict with 'approved' (bool) and 'polygon' (list) keys
    """

    def __init__(self, parent: Misc, frame: np.ndarray, polygon: list[list[float]]):
        """Initialize the preview polygon dialog.

        Args:
            parent: Parent Tkinter widget (typically root window)
            frame: Camera frame (numpy array) to display
            polygon: Detected polygon vertices [[x1, y1], [x2, y2], ...]
        """
        self.parent = parent
        self.frame = frame
        self.polygon = polygon
        self.result: dict[str, Any] | None = None

        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Aquário Detectado - Confirmar?")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)  # type: ignore[call-overload]
        self.dialog.grab_set()

        # Build UI
        self._create_widgets()

        # Center dialog after creating widgets (dimensions known)
        self._center_dialog()

    def _center_dialog(self):
        """Center the dialog on screen."""
        self.dialog.update_idletasks()
        width = self.dialog.winfo_width()
        height = self.dialog.winfo_height()
        x = (self.dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (height // 2)
        self.dialog.geometry(f"+{x}+{y}")

    def _create_widgets(self):
        """Create dialog widgets."""
        # Main container
        main_frame = ttk.Frame(self.dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Title
        title_label = ttk.Label(
            main_frame, text="Aquário Detectado - Confirmar?", font=("Segoe UI", 12, "bold")
        )
        title_label.pack(pady=(0, 10))

        # Preview canvas
        self._create_preview_canvas(main_frame)

        # Success message
        success_frame = ttk.Frame(main_frame)
        success_frame.pack(pady=(10, 0))

        success_label = ttk.Label(
            success_frame,
            text="✓ Aquário detectado com sucesso!",
            font=("Segoe UI", 10, "bold"),
            foreground="green",
        )
        success_label.pack()

        # Question
        question_label = ttk.Label(
            main_frame,
            text="Deseja usar este polígono ou ajustar manualmente?",
            font=("Segoe UI", 9),
        )
        question_label.pack(pady=(5, 15))

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side=tk.BOTTOM)

        reject_btn = ttk.Button(
            button_frame, text="Rejeitar/Ajustar", command=self._on_reject, width=18
        )
        reject_btn.pack(side=tk.LEFT, padx=5)

        approve_btn = ttk.Button(
            button_frame, text="Aprovar e Usar", command=self._on_approve, width=18
        )
        approve_btn.pack(side=tk.LEFT, padx=5)

        # Bind keys
        self.dialog.bind("<Return>", lambda e: self._on_approve())
        self.dialog.bind("<Escape>", lambda e: self._on_reject())

    def _create_preview_canvas(self, parent_frame: ttk.Frame):
        """Create canvas with frame and polygon preview.

        Args:
            parent_frame: Parent frame to add canvas to
        """
        # Draw polygon on frame
        preview_frame = self._draw_polygon_on_frame()

        # Convert to PIL Image
        preview_frame_rgb = cv2.cvtColor(preview_frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(preview_frame_rgb)

        # Resize if too large (max 800x600)
        max_width, max_height = 800, 600
        width, height = pil_image.size

        if width > max_width or height > max_height:
            ratio = min(max_width / width, max_height / height)
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            pil_image = pil_image.resize((new_width, new_height), Image.LANCZOS)  # type: ignore[attr-defined]

        # Convert to PhotoImage
        self.photo = ImageTk.PhotoImage(pil_image)

        # Create canvas
        canvas_frame = ttk.Frame(parent_frame, relief=tk.SUNKEN, borderwidth=2)
        canvas_frame.pack(pady=(0, 10))

        canvas = tk.Canvas(
            canvas_frame, width=pil_image.width, height=pil_image.height, highlightthickness=0
        )
        canvas.pack()

        # Display image
        canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)

    def _draw_polygon_on_frame(self) -> np.ndarray:
        """Draw polygon overlay on frame.

        Returns:
            Frame with polygon drawn
        """
        # Make copy of frame
        frame_copy = self.frame.copy()

        # Convert polygon to integer coordinates
        polygon_np = np.array(self.polygon, dtype=np.int32)

        # Draw polygon outline (thick green line)
        cv2.polylines(
            frame_copy,
            [polygon_np],
            isClosed=True,
            color=(0, 255, 0),  # Green in BGR
            thickness=3,
        )

        # Draw semi-transparent fill
        overlay = frame_copy.copy()
        cv2.fillPoly(
            overlay,
            [polygon_np],
            color=(0, 255, 0),  # Green
        )
        cv2.addWeighted(overlay, 0.2, frame_copy, 0.8, 0, frame_copy)

        # Draw vertices (small circles)
        for point in polygon_np:
            cv2.circle(
                frame_copy,
                tuple(point),
                radius=5,
                color=(0, 255, 255),  # Yellow in BGR
                thickness=-1,  # Filled
            )

        # Add label
        cv2.putText(
            frame_copy,
            "Aquario Detectado",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )

        return frame_copy

    def _on_approve(self):
        """Handle approve button click."""
        self.result = {"approved": True, "polygon": self.polygon}
        self.dialog.destroy()

    def _on_reject(self):
        """Handle reject button click."""
        self.result = {"approved": False, "polygon": None}
        self.dialog.destroy()

    def show(self) -> dict[str, Any] | None:
        """Show the dialog and wait for user response.

        Returns:
            dict with 'approved' (bool) and 'polygon' (list or None) keys,
            or None if dialog closed without action
        """
        self.dialog.wait_window()
        return self.result
