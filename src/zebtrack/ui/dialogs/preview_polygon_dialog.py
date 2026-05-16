"""Preview Polygon Dialog - Show detected aquarium for approval.

This dialog displays a preview of the auto-detected aquarium polygon
overlaid on a camera frame, allowing user to approve or reject the detection.

The dialog also exposes a confidence threshold slider and a "Retry" button.
When ``on_retry`` is supplied the user can run a fresh auto-detection from
the live camera with a different threshold without closing the dialog.

The polygon vertices are interactive: the user can drag any vertex on the
canvas to adjust the shape manually. Once any vertex is moved, the dialog
flips the header badge from "Auto-detectado" to "Editado manualmente" and
the approval result reports ``source = "manual"`` so downstream consumers
can record the provenance of the polygon.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np
from PIL import Image, ImageTk

if TYPE_CHECKING:
    from tkinter import Misc


RetryResult = tuple[np.ndarray, list[list[float]]] | None
RetryCallback = Callable[[float], RetryResult]

# Pick radius (canvas pixels) for selecting a vertex with the mouse. Matches
# the visible vertex marker drawn by ``_draw_polygon_on_frame`` (radius 5 px
# on the native frame) with extra slack to make picking comfortable.
_VERTEX_PICK_RADIUS_PX = 14

_BADGE_AUTO_TEXT = "✓ Auto-detectado"
_BADGE_MANUAL_TEXT = "✎ Editado manualmente"
_BADGE_AUTO_BG = "#2ecc71"
_BADGE_MANUAL_BG = "#e67e22"


class PreviewPolygonDialog:
    """Dialog for previewing and approving auto-detected aquarium polygon.

    Shows camera frame with detected polygon overlay. User can:
    - Approve the detection,
    - Adjust the confidence threshold via a slider and retry detection live,
    - Reject (fall back to manual drawing).

    Returns:
        dict with ``approved`` (bool), ``polygon`` (list), ``confidence``
        (float — last slider value) and ``frame`` (np.ndarray | None — latest
        frame used during retry, or None when no retry was triggered).
    """

    def __init__(
        self,
        parent: Misc,
        frame: np.ndarray,
        polygon: list[list[float]],
        *,
        initial_confidence: float = 0.05,
        confidence_min: float = 0.01,
        confidence_max: float = 0.95,
        on_retry: RetryCallback | None = None,
    ):
        """Initialize the preview polygon dialog.

        Args:
            parent: Parent Tkinter widget (typically root window).
            frame: Camera frame (numpy array) to display.
            polygon: Detected polygon vertices ``[[x1, y1], ...]``.
            initial_confidence: Initial slider value (typically the project
                default ``settings.yolo_model.confidence_threshold``).
            confidence_min/confidence_max: Slider bounds. Clamped to ``[0.01, 0.95]``.
            on_retry: Optional callback invoked when the user clicks "Tentar
                novamente". Receives the slider's current confidence and returns
                ``(frame, polygon)`` on success or ``None`` on failure.
        """
        self.parent = parent
        self.frame = frame
        self.polygon = polygon
        self.result: dict[str, Any] | None = None

        # Clamp slider bounds to the AquariumDetector's accepted range so the
        # downstream call never receives values outside [0.01, 0.95].
        self._conf_min = max(0.01, min(0.95, float(confidence_min)))
        self._conf_max = max(self._conf_min, min(0.95, float(confidence_max)))
        clamped_initial = max(self._conf_min, min(self._conf_max, float(initial_confidence)))

        self._on_retry = on_retry
        self._retried_frame: np.ndarray | None = None

        # Manual-edit tracking. Flips to True the first time the user drags a
        # vertex; reset to False when a successful retry replaces the polygon.
        self._edited: bool = False
        self._dragging_vertex_idx: int | None = None
        # Uniform scale factor applied by ``_build_preview_image`` when the
        # native frame exceeds the 800x600 preview budget. Mouse coordinates
        # arrive in canvas (post-scale) space and must be divided by this to
        # mutate ``self.polygon`` (stored in native frame coords).
        self._scale: float = 1.0
        self._vertex_pick_radius_px: int = _VERTEX_PICK_RADIUS_PX

        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Aquário Detectado - Confirmar?")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)  # type: ignore[call-overload]
        self.dialog.grab_set()

        # Tk variables (must exist before _create_widgets builds the slider).
        self._conf_var = tk.DoubleVar(value=clamped_initial)
        self._conf_text_var = tk.StringVar(value=f"{clamped_initial:.2f}")
        self._status_var = tk.StringVar(value="")
        self._badge_var = tk.StringVar(value=_BADGE_AUTO_TEXT)

        # UI references populated by _create_widgets
        self.photo: ImageTk.PhotoImage | None = None
        self._canvas: tk.Canvas | None = None
        self._retry_button: ttk.Button | None = None
        self._badge_label: tk.Label | None = None

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
        main_frame = ttk.Frame(self.dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        title_label = ttk.Label(
            main_frame, text="Aquário Detectado - Confirmar?", font=("Segoe UI", 12, "bold")
        )
        title_label.pack(pady=(0, 6))

        # Provenance badge — green "auto" by default, flips to orange "manual"
        # the first time the user drags a vertex.
        self._badge_label = tk.Label(
            main_frame,
            textvariable=self._badge_var,
            font=("Segoe UI", 9, "bold"),
            bg=_BADGE_AUTO_BG,
            fg="white",
            padx=10,
            pady=3,
        )
        self._badge_label.pack(pady=(0, 8))

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
        question_label.pack(pady=(5, 10))

        # Confidence threshold panel (only shown when retry is supported).
        if self._on_retry is not None:
            self._create_confidence_panel(main_frame)

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

    def _create_confidence_panel(self, parent: ttk.Frame) -> None:
        """Build the confidence threshold slider + retry button + status."""
        panel = ttk.LabelFrame(parent, text="Limiar de confiança da auto-detecção", padding=10)
        panel.pack(fill=tk.X, pady=(0, 10))

        slider_row = ttk.Frame(panel)
        slider_row.pack(fill=tk.X)

        ttk.Label(slider_row, text=f"{self._conf_min:.2f}").pack(side=tk.LEFT)

        scale = ttk.Scale(
            slider_row,
            from_=self._conf_min,
            to=self._conf_max,
            orient="horizontal",
            variable=self._conf_var,
            command=self._on_slider_changed,
        )
        scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)

        ttk.Label(slider_row, text=f"{self._conf_max:.2f}").pack(side=tk.LEFT)

        value_label = ttk.Label(
            panel,
            textvariable=self._conf_text_var,
            font=("Segoe UI", 10, "bold"),
        )
        value_label.pack(pady=(4, 0))

        self._retry_button = ttk.Button(
            panel,
            text="🔁 Tentar novamente com este limiar",
            command=self._on_retry_click,
        )
        self._retry_button.pack(pady=(6, 2))

        status_label = ttk.Label(
            panel,
            textvariable=self._status_var,
            font=("Segoe UI", 9, "italic"),
            foreground="#555",
        )
        status_label.pack(pady=(2, 0))

    def _on_slider_changed(self, raw_value: str) -> None:
        """Mirror the slider value into a numeric label (no detection trigger)."""
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return
        self._conf_text_var.set(f"{value:.2f}")

    def _on_retry_click(self) -> None:
        """Re-run aquarium auto-detection with the slider's confidence value."""
        if self._on_retry is None:
            return

        confidence = float(self._conf_var.get())
        self._status_var.set("Detectando…")
        if self._retry_button is not None:
            self._retry_button.state(["disabled"])
        self.dialog.update_idletasks()

        try:
            outcome = self._on_retry(confidence)
        # except Exception justified: callback may invoke ML inference; we
        # must not let it crash the dialog.
        except Exception as exc:
            outcome = None
            self._status_var.set(f"Falha na detecção: {exc!s}")
        else:
            if outcome is None:
                self._status_var.set(
                    "Nenhum aquário encontrado — ajuste o limiar e tente novamente."
                )
            else:
                new_frame, new_polygon = outcome
                self.frame = new_frame
                self._retried_frame = new_frame
                self.polygon = new_polygon
                # Successful retry replaces the polygon with a fresh model
                # output → clear any prior manual-edit flag and reset badge.
                self._edited = False
                self._set_badge_auto()
                self._refresh_canvas()
                self._status_var.set(f"Aquário re-detectado com limiar {confidence:.2f}")

        if self._retry_button is not None:
            self._retry_button.state(["!disabled"])

    def _create_preview_canvas(self, parent_frame: ttk.Frame):
        """Create canvas with frame and polygon preview."""
        canvas_frame = ttk.Frame(parent_frame, relief=tk.SUNKEN, borderwidth=2)
        canvas_frame.pack(pady=(0, 10))

        # Initial draw — sizes the canvas to the frame.
        pil_image = self._build_preview_image()
        self.photo = ImageTk.PhotoImage(pil_image)

        canvas = tk.Canvas(
            canvas_frame,
            width=pil_image.width,
            height=pil_image.height,
            highlightthickness=0,
            cursor="crosshair",
        )
        canvas.pack()
        canvas.create_image(0, 0, anchor=tk.NW, image=self.photo, tags=("preview_image",))

        # Vertex drag handlers — let the user nudge individual polygon vertices.
        canvas.bind("<Button-1>", self._on_canvas_press)
        canvas.bind("<B1-Motion>", self._on_canvas_drag)
        canvas.bind("<ButtonRelease-1>", self._on_canvas_release)

        self._canvas = canvas

    def _build_preview_image(self) -> Image.Image:
        """Render the current frame + polygon into a sized PIL image."""
        preview_frame = self._draw_polygon_on_frame()
        preview_frame_rgb = cv2.cvtColor(preview_frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(preview_frame_rgb)

        max_width, max_height = 800, 600
        width, height = pil_image.size
        if width > max_width or height > max_height:
            ratio = min(max_width / width, max_height / height)
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            pil_image = pil_image.resize((new_width, new_height), Image.LANCZOS)  # type: ignore[attr-defined]
            self._scale = ratio
        else:
            self._scale = 1.0
        return pil_image

    def _refresh_canvas(self) -> None:
        """Replace the canvas image after a successful retry."""
        if self._canvas is None:
            return
        pil_image = self._build_preview_image()
        # Keep a reference to prevent GC.
        self.photo = ImageTk.PhotoImage(pil_image)
        self._canvas.config(width=pil_image.width, height=pil_image.height)
        self._canvas.delete("preview_image")
        self._canvas.create_image(0, 0, anchor=tk.NW, image=self.photo, tags=("preview_image",))

    def _draw_polygon_on_frame(self) -> np.ndarray:
        """Draw polygon overlay on frame."""
        frame_copy = self.frame.copy()
        polygon_np = np.array(self.polygon, dtype=np.int32)

        cv2.polylines(
            frame_copy,
            [polygon_np],
            isClosed=True,
            color=(0, 255, 0),
            thickness=3,
        )

        overlay = frame_copy.copy()
        cv2.fillPoly(overlay, [polygon_np], color=(0, 255, 0))
        cv2.addWeighted(overlay, 0.2, frame_copy, 0.8, 0, frame_copy)

        for point in polygon_np:
            cv2.circle(
                frame_copy,
                tuple(point),
                radius=5,
                color=(0, 255, 255),
                thickness=-1,
            )

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
        self.result = {
            "approved": True,
            "polygon": self.polygon,
            "confidence": float(self._conf_var.get()),
            "frame": self._retried_frame,
            "source": "manual" if self._edited else "auto",
            "edited": self._edited,
        }
        self.dialog.destroy()

    def _on_reject(self):
        """Handle reject button click."""
        self.result = {
            "approved": False,
            "polygon": None,
            "confidence": float(self._conf_var.get()),
            "frame": None,
            # Rejection routes the user to manual drawing — tag accordingly.
            "source": "manual",
            "edited": self._edited,
        }
        self.dialog.destroy()

    # ------------------------------------------------------------------
    # Vertex drag / badge helpers
    # ------------------------------------------------------------------

    def _on_canvas_press(self, event: Any) -> None:
        """Pick the polygon vertex nearest the click, if within pick radius."""
        idx = self._find_nearest_vertex(event.x, event.y)
        self._dragging_vertex_idx = idx

    def _on_canvas_drag(self, event: Any) -> None:
        """Move the currently-picked vertex to the cursor (native-frame coords)."""
        idx = self._dragging_vertex_idx
        if idx is None or not self.polygon or not 0 <= idx < len(self.polygon):
            return
        img_x, img_y = self._canvas_to_image_coords(event.x, event.y)
        self.polygon[idx] = [float(img_x), float(img_y)]
        self._mark_edited()
        self._refresh_canvas()

    def _on_canvas_release(self, _event: Any) -> None:
        """Drop the picked vertex (drag ends)."""
        self._dragging_vertex_idx = None

    def _find_nearest_vertex(self, canvas_x: float, canvas_y: float) -> int | None:
        """Return the index of the polygon vertex within pick radius, or None."""
        if not self.polygon:
            return None
        pick_radius = self._vertex_pick_radius_px
        best_idx: int | None = None
        best_dist_sq = float(pick_radius) ** 2
        for i, point in enumerate(self.polygon):
            cx, cy = self._image_to_canvas_coords(point[0], point[1])
            dist_sq = (cx - canvas_x) ** 2 + (cy - canvas_y) ** 2
            if dist_sq <= best_dist_sq:
                best_dist_sq = dist_sq
                best_idx = i
        return best_idx

    def _canvas_to_image_coords(self, canvas_x: float, canvas_y: float) -> tuple[float, float]:
        """Convert canvas (post-scale) coords to native frame coords."""
        scale = self._scale if self._scale else 1.0
        return (canvas_x / scale, canvas_y / scale)

    def _image_to_canvas_coords(self, image_x: float, image_y: float) -> tuple[float, float]:
        """Convert native frame coords to canvas (post-scale) coords."""
        scale = self._scale if self._scale else 1.0
        return (image_x * scale, image_y * scale)

    def _mark_edited(self) -> None:
        """Flip provenance to manual on the first vertex drag of this attempt."""
        if self._edited:
            return
        self._edited = True
        self._set_badge_manual()

    def _set_badge_auto(self) -> None:
        """Show the green ✓ Auto-detectado badge."""
        self._badge_var.set(_BADGE_AUTO_TEXT)
        if self._badge_label is not None:
            try:
                self._badge_label.config(bg=_BADGE_AUTO_BG)
            except tk.TclError:
                # Badge label was destroyed (e.g. during dialog teardown).
                pass

    def _set_badge_manual(self) -> None:
        """Show the orange ✎ Editado manualmente badge."""
        self._badge_var.set(_BADGE_MANUAL_TEXT)
        if self._badge_label is not None:
            try:
                self._badge_label.config(bg=_BADGE_MANUAL_BG)
            except tk.TclError:
                pass

    def show(self) -> dict[str, Any] | None:
        """Show the dialog and wait for user response."""
        self.dialog.wait_window()
        return self.result
