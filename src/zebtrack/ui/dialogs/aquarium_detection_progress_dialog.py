"""Aquarium detection progress dialog for live camera sessions.

Shows real-time progress during automatic arena detection phase:
- Frame counter (0-100)
- Progress bar
- Thumbnail of last frame with detected bboxes
- Valid/invalid detection counts

Version: 2.2.0
Author: ZebTrack-AI Team
Date: January 2026
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

import cv2
import numpy as np
import structlog
from PIL import Image, ImageTk

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


class AquariumDetectionProgressDialog(tk.Toplevel):
    """Progress dialog for automatic aquarium detection phase.

    Displays:
    - Frame progress (0/100)
    - Progress bar
    - Live thumbnail with detected aquarium bboxes
    - Valid/invalid detection counters
    - Status messages

    Non-blocking: Updates via after() calls from LiveCameraService.
    """

    def __init__(
        self,
        parent: tk.Misc,
        experiment_id: str,
        max_frames: int = 100,
    ):
        """Initialize progress dialog.

        Args:
            parent: Parent Tkinter widget
            experiment_id: Current experiment identifier
            max_frames: Maximum frames to collect before consensus
        """
        super().__init__(parent)

        self.experiment_id = experiment_id
        self.max_frames = max_frames
        self.current_frame = 0
        self.valid_detections = 0
        self.invalid_detections = 0
        self._thumbnail_photo: ImageTk.PhotoImage | None = None  # Keep reference to prevent GC

        self.title("Detectando Aquário")
        self.geometry("600x500")
        self.resizable(False, False)

        # Make modal
        self.transient(parent.winfo_toplevel())
        self.grab_set()

        self._create_widgets()

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

        logger.info(
            "aquarium_detection_dialog.created",
            experiment_id=experiment_id,
            max_frames=max_frames,
        )

    def _create_widgets(self) -> None:
        """Create dialog widgets."""
        # Main frame
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Title
        title_label = ttk.Label(
            main_frame,
            text="⏳ Detectando Aquário Automaticamente",
            font=("Arial", 14, "bold"),
        )
        title_label.pack(pady=(0, 10))

        # Description
        desc_label = ttk.Label(
            main_frame,
            text=(
                f"Sessão: {self.experiment_id}\n"
                "Analisando frames para identificar região do aquário..."
            ),
            justify=tk.CENTER,
        )
        desc_label.pack(pady=(0, 15))

        # Progress frame
        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=(0, 15))

        # Frame counter
        self.frame_label = ttk.Label(
            progress_frame,
            text=f"Frame: 0 / {self.max_frames}",
            font=("Arial", 11),
        )
        self.frame_label.pack()

        # Progress bar
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            mode="determinate",
            maximum=self.max_frames,
            length=400,
        )
        self.progress_bar.pack(pady=5)

        # Stats frame
        stats_frame = ttk.Frame(main_frame)
        stats_frame.pack(fill=tk.X, pady=(0, 15))

        stats_label = ttk.Label(
            stats_frame,
            text="Detecções:",
            font=("Arial", 10, "bold"),
        )
        stats_label.pack(side=tk.LEFT, padx=(0, 10))

        self.valid_label = ttk.Label(
            stats_frame,
            text="✓ Válidas: 0",
            foreground="green",
        )
        self.valid_label.pack(side=tk.LEFT, padx=5)

        self.invalid_label = ttk.Label(
            stats_frame,
            text="✗ Inválidas: 0",
            foreground="red",
        )
        self.invalid_label.pack(side=tk.LEFT, padx=5)

        # Thumbnail frame
        thumbnail_frame = ttk.LabelFrame(
            main_frame,
            text="Último Frame Analisado",
            padding=10,
        )
        thumbnail_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        self.thumbnail_label = ttk.Label(
            thumbnail_frame,
            text="Aguardando frames...",
            anchor=tk.CENTER,
        )
        self.thumbnail_label.pack(fill=tk.BOTH, expand=True)

        # Status label
        self.status_label = ttk.Label(
            main_frame,
            text="Iniciando detecção...",
            font=("Arial", 9, "italic"),
            foreground="blue",
        )
        self.status_label.pack()

        # Prevent window close
        self.protocol("WM_DELETE_WINDOW", lambda: None)

    def update_progress(
        self,
        frame_number: int,
        frame_image: np.ndarray | None = None,
        detected_bbox: tuple[int, int, int, int] | None = None,
        is_valid: bool = False,
        status_message: str | None = None,
    ) -> None:
        """Update progress display.

        Args:
            frame_number: Current frame index
            frame_image: Optional frame image to display
            detected_bbox: Optional detected bbox (x1, y1, x2, y2)
            is_valid: Whether detection is valid (area > threshold)
            status_message: Optional status text override
        """
        self.current_frame = frame_number
        self.progress_bar.config(value=frame_number)
        self.frame_label.config(text=f"Frame: {frame_number} / {self.max_frames}")

        # Update stats
        if detected_bbox is not None:
            if is_valid:
                self.valid_detections += 1
            else:
                self.invalid_detections += 1

        self.valid_label.config(text=f"✓ Válidas: {self.valid_detections}")
        self.invalid_label.config(text=f"✗ Inválidas: {self.invalid_detections}")

        # Update thumbnail
        if frame_image is not None:
            self._update_thumbnail(frame_image, detected_bbox, is_valid)

        # Update status
        if status_message:
            self.status_label.config(text=status_message)
        elif detected_bbox:
            if is_valid:
                self.status_label.config(
                    text="✓ Aquário detectado (área válida)",
                    foreground="green",
                )
            else:
                self.status_label.config(
                    text="✗ Detecção ignorada (área insuficiente)",
                    foreground="orange",
                )

    def _update_thumbnail(
        self,
        frame: np.ndarray,
        bbox: tuple[int, int, int, int] | None,
        is_valid: bool,
    ) -> None:
        """Update thumbnail with frame and bbox overlay.

        Args:
            frame: Frame image (BGR)
            bbox: Optional bounding box (x1, y1, x2, y2)
            is_valid: Whether bbox is valid
        """
        try:
            # Resize frame to fit thumbnail area (max 400x300)
            h, w = frame.shape[:2]
            max_w, max_h = 400, 300
            scale = min(max_w / w, max_h / h)
            new_w, new_h = int(w * scale), int(h * scale)

            resized = cv2.resize(frame, (new_w, new_h))

            # Draw bbox if provided
            if bbox:
                x1, y1, x2, y2 = bbox
                # Scale bbox to thumbnail size
                x1_s = int(x1 * scale)
                y1_s = int(y1 * scale)
                x2_s = int(x2 * scale)
                y2_s = int(y2 * scale)

                # Choose color based on validity
                color = (0, 255, 0) if is_valid else (0, 165, 255)  # Green or Orange (BGR)
                thickness = 2

                cv2.rectangle(resized, (x1_s, y1_s), (x2_s, y2_s), color, thickness)

                # Add label
                label = "VÁLIDO" if is_valid else "INVÁLIDO"
                cv2.putText(
                    resized,
                    label,
                    (x1_s, y1_s - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    color,
                    2,
                )

            # Convert BGR to RGB for PIL
            rgb_frame = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

            # Convert to PIL Image
            pil_image = Image.fromarray(rgb_frame)

            # Convert to PhotoImage
            photo = ImageTk.PhotoImage(image=pil_image)

            # Update label (keep reference to prevent GC)
            self.thumbnail_label.config(image=photo, text="")
            self._thumbnail_photo = photo

        except Exception as e:
            logger.warning(
                "aquarium_detection_dialog.thumbnail_update_failed",
                error=str(e),
            )

    def show_completion(self, success: bool, message: str) -> None:
        """Show completion status.

        Args:
            success: Whether detection succeeded
            message: Completion message
        """
        if success:
            self.status_label.config(
                text=f"✓ {message}",
                foreground="green",
                font=("Arial", 10, "bold"),
            )
        else:
            self.status_label.config(
                text=f"✗ {message}",
                foreground="red",
                font=("Arial", 10, "bold"),
            )

        # Auto-close after 2 seconds
        self.after(2000, self.destroy)

    def close_dialog(self) -> None:
        """Programmatically close dialog."""
        try:
            self.destroy()
        except tk.TclError:
            logger.debug("aquarium_progress_dialog.close.already_destroyed", exc_info=True)
