"""
Live Preview Window for Camera Analysis.

Shows real-time video feed with object detections during camera analysis.
Allows manual stop or auto-stop after configured duration.
"""

from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    import numpy as np

log = structlog.get_logger()


class LivePreviewWindow:
    """Window showing live camera feed with detections during analysis."""

    def __init__(
        self,
        parent,
        camera_index: int,
        duration_s: float,
        on_stop_callback=None,
    ):
        """
        Initialize live preview window.

        Args:
            parent: Parent tkinter widget
            camera_index: Index of camera being analyzed
            duration_s: Maximum duration in seconds
            on_stop_callback: Callback when user stops or time expires
        """
        self.parent = parent
        self.camera_index = camera_index
        self.duration_s = duration_s
        self.on_stop_callback = on_stop_callback

        self.window = tk.Toplevel(parent)
        self.window.title(f"Análise ao Vivo - Câmera {camera_index}")
        self.window.geometry("800x700")
        self.window.protocol("WM_DELETE_WINDOW", self._on_window_close)

        # Start time for timer
        self.start_time = None
        self.is_stopped = False

        # Create UI
        self._create_ui()

        # Start timer update
        self._update_timer()

        log.info(
            "live_preview.window_created",
            camera_index=camera_index,
            duration_s=duration_s,
        )

    def start_timer(self):
        """Start the session timer."""
        self.start_time = time.time()
        log.info("live_preview.timer_started")

    def _create_ui(self):
        """Create the UI components."""
        # Main container
        main_frame = ttk.Frame(self.window, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Info panel at top
        info_frame = ttk.Frame(main_frame)
        info_frame.pack(fill=tk.X, pady=(0, 10))

        # Camera info
        ttk.Label(
            info_frame,
            text=f"Câmera: {self.camera_index}",
            font=("Arial", 10, "bold"),
        ).pack(side=tk.LEFT, padx=5)

        # Timer label
        self.timer_label = ttk.Label(
            info_frame,
            text="Tempo: Aguardando...",
            font=("Arial", 10),
        )
        self.timer_label.pack(side=tk.LEFT, padx=20)

        # Status label
        self.status_label = ttk.Label(
            info_frame,
            text="● Gravando",
            foreground="red",
            font=("Arial", 10, "bold"),
        )
        self.status_label.pack(side=tk.LEFT, padx=5)

        # Video display area
        video_frame = ttk.Frame(main_frame, relief=tk.SUNKEN, borderwidth=2)
        video_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Canvas for video display
        self.canvas = tk.Canvas(
            video_frame,
            bg="black",
            width=640,
            height=480,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # Info text
        self.canvas.create_text(
            320,
            240,
            text="Aguardando frames...",
            fill="white",
            font=("Arial", 12),
            tags="waiting",
        )

        # Stats panel
        stats_frame = ttk.LabelFrame(main_frame, text="Estatísticas", padding=10)
        stats_frame.pack(fill=tk.X, pady=(0, 10))

        # Stats labels
        stats_grid = ttk.Frame(stats_frame)
        stats_grid.pack(fill=tk.X)

        ttk.Label(stats_grid, text="Frames processados:").grid(
            row=0, column=0, sticky=tk.W, padx=5, pady=2
        )
        self.frames_label = ttk.Label(stats_grid, text="0")
        self.frames_label.grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)

        ttk.Label(stats_grid, text="Objetos detectados:").grid(
            row=1, column=0, sticky=tk.W, padx=5, pady=2
        )
        self.detections_label = ttk.Label(stats_grid, text="0")
        self.detections_label.grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)

        ttk.Label(stats_grid, text="FPS:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.fps_label = ttk.Label(stats_grid, text="0.0")
        self.fps_label.grid(row=2, column=1, sticky=tk.W, padx=5, pady=2)

        # Control buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)

        self.stop_button = ttk.Button(
            button_frame,
            text="⏹ Parar Gravação",
            command=self._on_stop_clicked,
            style="Accent.TButton",
        )
        self.stop_button.pack(side=tk.LEFT, padx=5)

        ttk.Button(
            button_frame,
            text="Fechar",
            command=self._on_window_close,
        ).pack(side=tk.RIGHT, padx=5)

        # Stats tracking
        self.frame_count = 0
        self.detection_count = 0
        self.last_frame_time = time.time()
        self.current_fps = 0.0

    def _update_timer(self):
        """Update the timer display."""
        if self.is_stopped:
            return

        if self.start_time is None:
            self.timer_label.config(text="Tempo: Aguardando...")
        else:
            elapsed = time.time() - self.start_time
            remaining = max(0, self.duration_s - elapsed)

            # Update timer label
            self.timer_label.config(
                text=f"Tempo: {elapsed:.1f}s / {self.duration_s:.1f}s (Restante: {remaining:.1f}s)"
            )

            # Check if time has expired
            if remaining <= 0:
                self._auto_stop()
                return  # Don't schedule another update

        # Schedule next update
        self.window.after(100, self._update_timer)

    def _auto_stop(self):
        """Handle automatic stop when time expires."""
        if self.is_stopped:
            return

        elapsed = time.time() - self.start_time if self.start_time is not None else 0.0
        log.info("live_preview.auto_stop", elapsed=elapsed)
        self.is_stopped = True

        self.status_label.config(text="● Tempo Expirado", foreground="orange")
        self.stop_button.config(state=tk.DISABLED)

        if self.on_stop_callback:
            self.on_stop_callback()

    def _on_stop_clicked(self):
        """Handle manual stop button click."""
        if self.is_stopped:
            return

        elapsed = time.time() - self.start_time if self.start_time is not None else 0.0
        log.info("live_preview.manual_stop", elapsed=elapsed)
        self.is_stopped = True

        self.status_label.config(text="● Parado", foreground="gray")
        self.stop_button.config(state=tk.DISABLED)

        if self.on_stop_callback:
            self.on_stop_callback()

    def _on_window_close(self):
        """Handle window close event."""
        if not self.is_stopped:
            self._on_stop_clicked()
        self.window.destroy()

    def update_frame(self, frame: np.ndarray, detections: list | None = None):
        """
        Update the display with a new frame.

        Args:
            frame: BGR image frame from OpenCV
            detections: List of detection results (optional)
        """
        if self.is_stopped:
            return

        try:
            import cv2
            from PIL import Image, ImageTk

            # Remove waiting text if present
            self.canvas.delete("waiting")

            # Convert BGR to RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Draw detections if provided
            if detections:
                for det in detections:
                    x1, y1, x2, y2 = map(int, det[:4])
                    conf = det[4] if len(det) > 4 else 0

                    # Draw bounding box
                    cv2.rectangle(frame_rgb, (x1, y1), (x2, y2), (0, 255, 0), 2)

                    # Draw confidence label
                    label = f"{conf:.2f}"
                    cv2.putText(
                        frame_rgb,
                        label,
                        (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 255, 0),
                        2,
                    )

            # Resize to fit canvas
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()

            if canvas_width > 1 and canvas_height > 1:
                h, w = frame_rgb.shape[:2]
                scale = min(canvas_width / w, canvas_height / h)
                new_w = int(w * scale)
                new_h = int(h * scale)

                frame_resized = cv2.resize(frame_rgb, (new_w, new_h))

                # Convert to PhotoImage
                image = Image.fromarray(frame_resized)
                photo = ImageTk.PhotoImage(image)

                # Update canvas
                self.canvas.delete("frame")
                x = (canvas_width - new_w) // 2
                y = (canvas_height - new_h) // 2
                self.canvas.create_image(x, y, anchor=tk.NW, image=photo, tags="frame")
                self.canvas.image = photo  # Keep reference

            # Update stats
            self.frame_count += 1
            if detections:
                self.detection_count += len(detections)

            # Calculate FPS
            current_time = time.time()
            time_diff = current_time - self.last_frame_time
            if time_diff > 0:
                self.current_fps = 1.0 / time_diff
            self.last_frame_time = current_time

            # Update stat labels
            self.frames_label.config(text=str(self.frame_count))
            self.detections_label.config(text=str(self.detection_count))
            self.fps_label.config(text=f"{self.current_fps:.1f}")

        except Exception as e:
            log.error("live_preview.update_frame_error", error=str(e), exc_info=True)

    def update_status_text(self, text: str, color: str = "red"):
        """Update the status label text and color.

        Args:
            text: Status text to display
            color: Text color (default: "red" for recording)
        """
        if hasattr(self, "status_label"):
            self.status_label.config(text=text, foreground=color)

    def show(self):
        """Show the window."""
        self.window.deiconify()

    def hide(self):
        """Hide the window."""
        self.window.withdraw()

    def destroy(self):
        """Destroy the window."""
        self.is_stopped = True
        if self.window.winfo_exists():
            self.window.destroy()
