"""Multi-Aquarium Live Preview Window.

Shows side-by-side real-time video feeds for multiple aquariums
during live camera analysis.

Version: 2.2.0
"""

from __future__ import annotations

import time
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING

import cv2
import numpy as np
import structlog
from PIL import Image, ImageTk

if TYPE_CHECKING:
    pass

log = structlog.get_logger()


class MultiAquariumLivePreviewWindow:
    """Window showing live camera feed with multiple aquarium views."""

    def __init__(
        self,
        parent,
        camera_index: int,
        num_aquariums: int,
        duration_s: float,
        on_stop_callback: Callable[[], None] | None = None,
    ):
        """Initialize multi-aquarium preview window.

        Args:
            parent: Parent tkinter widget
            camera_index: Index of camera being analyzed
            num_aquariums: Number of aquariums to display
            duration_s: Maximum duration in seconds
            on_stop_callback: Callback when user stops or time expires
        """
        self.parent = parent
        self.camera_index = camera_index
        self.num_aquariums = num_aquariums
        self.duration_s = duration_s
        self.on_stop_callback = on_stop_callback

        # Window setup
        self.window = tk.Toplevel(parent)
        self.window.title(f"Análise ao Vivo Multi-Aquário - Câmera {camera_index}")

        # Calculate window size based on aquarium count
        # Layout: 2 columns for 2-4 aquariums, 3 columns for 5-6
        cols = 2 if num_aquariums <= 4 else 3
        width = 400 * cols + 40  # 400px per aquarium + padding
        height = 350 * ((num_aquariums + cols - 1) // cols) + 150  # rows * height + controls

        self.window.geometry(f"{width}x{height}")
        self.window.protocol("WM_DELETE_WINDOW", self._on_window_close)

        # Timer
        self.start_time: float | None = None
        self.is_stopped = False

        # Aquarium canvases
        self.aquarium_canvases: dict[int, tk.Canvas] = {}
        self.aquarium_labels: dict[int, ttk.Label] = {}
        self.aquarium_photo_images: dict[int, ImageTk.PhotoImage] = {}

        # Status labels
        self.timer_label: ttk.Label | None = None
        self.status_label: ttk.Label | None = None
        self.start_time_label: ttk.Label | None = None
        self.stop_time_label: ttk.Label | None = None
        self.eta_label: ttk.Label | None = None
        self.recorded_frames_label: ttk.Label | None = None
        self.progress_bar: ttk.Progressbar | None = None

        # Create UI
        self._create_ui()

        # Start timer update
        self._update_timer()

        log.info(
            "multi_aquarium_preview.window_created",
            camera_index=camera_index,
            num_aquariums=num_aquariums,
            duration_s=duration_s,
        )

    def start_timer(self) -> None:
        """Start the session timer."""
        self.start_time = time.time()
        if self.start_time_label is not None:
            self.start_time_label.config(text=f"Início: {self._format_clock(self.start_time)}")
        log.info("multi_aquarium_preview.timer_started")

    @staticmethod
    def _format_clock(ts: float) -> str:
        """Format an epoch timestamp as HH:MM:SS local time."""
        return time.strftime("%H:%M:%S", time.localtime(ts))

    @staticmethod
    def _format_eta(seconds: float) -> str:
        """Render a remaining-time count as ``Xm Ys`` (or ``Xs`` when <60s)."""
        seconds = max(0, int(seconds))
        if seconds < 60:
            return f"{seconds}s"
        minutes, secs = divmod(seconds, 60)
        if minutes < 60:
            return f"{minutes}m {secs:02d}s"
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes:02d}m {secs:02d}s"

    def update_recorded_count(self, recorded_count: int) -> None:
        """Update the on-disk frame counter displayed in the footer.

        Threading: must be called on the Tk main thread. Workers should
        marshal via ``root.after(0, window.update_recorded_count, n)``.
        """
        if self.recorded_frames_label is not None:
            self.recorded_frames_label.config(text=f"Frames gravados: {int(recorded_count)}")

    def _create_ui(self) -> None:
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
            text=f"Câmera: {self.camera_index} | Aquários: {self.num_aquariums}",
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
            text="Status: Inicializando...",
            font=("Arial", 10),
        )
        self.status_label.pack(side=tk.LEFT, padx=10)

        # Aquarium grid
        grid_frame = ttk.Frame(main_frame)
        grid_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        cols = 2 if self.num_aquariums <= 4 else 3

        for aq_id in range(self.num_aquariums):
            row = aq_id // cols
            col = aq_id % cols

            aq_frame = ttk.LabelFrame(
                grid_frame,
                text=f"Aquário {aq_id + 1}",
                padding=5,
            )
            aq_frame.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")

            # Canvas for video
            canvas = tk.Canvas(
                aq_frame,
                width=360,
                height=270,
                bg="black",
            )
            canvas.pack()
            self.aquarium_canvases[aq_id] = canvas

            # Detection count label
            label = ttk.Label(
                aq_frame,
                text="Detecções: 0",
                font=("Arial", 9),
            )
            label.pack(pady=(5, 0))
            self.aquarium_labels[aq_id] = label

        # Configure grid weights for even distribution
        for c in range(cols):
            grid_frame.columnconfigure(c, weight=1)
        for r in range((self.num_aquariums + cols - 1) // cols):
            grid_frame.rowconfigure(r, weight=1)

        # Session footer: clock labels + recorded frames + progress bar
        footer_frame = ttk.LabelFrame(main_frame, text="Sessão", padding=8)
        footer_frame.pack(fill=tk.X, pady=(0, 8))

        clocks_row = ttk.Frame(footer_frame)
        clocks_row.pack(fill=tk.X)

        self.start_time_label = ttk.Label(clocks_row, text="Início: --:--:--")
        self.start_time_label.pack(side=tk.LEFT, padx=(0, 15))

        self.stop_time_label = ttk.Label(clocks_row, text="Fim: --:--:--")
        self.stop_time_label.pack(side=tk.LEFT, padx=(0, 15))

        self.eta_label = ttk.Label(clocks_row, text="ETA: --")
        self.eta_label.pack(side=tk.LEFT, padx=(0, 15))

        self.recorded_frames_label = ttk.Label(clocks_row, text="Frames gravados: 0")
        self.recorded_frames_label.pack(side=tk.LEFT)

        progress_mode = "determinate" if self.duration_s > 0 else "indeterminate"
        self.progress_bar = ttk.Progressbar(
            footer_frame,
            length=300,
            mode=progress_mode,  # type: ignore[arg-type]
            maximum=100.0,
        )
        self.progress_bar.pack(fill=tk.X, pady=(6, 0))
        if progress_mode == "indeterminate":
            self.progress_bar.start(80)

        # Control panel at bottom
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X)

        # Stop button
        self.stop_button = ttk.Button(
            control_frame,
            text="⏹ Parar Análise",
            command=self._on_stop_clicked,
        )
        self.stop_button.pack(side=tk.RIGHT, padx=5)

    def update_aquarium_frame(
        self,
        aquarium_id: int,
        frame: np.ndarray,
        num_detections: int = 0,
    ) -> None:
        """Update frame for specific aquarium.

        Args:
            aquarium_id: Aquarium ID (0-indexed)
            frame: Frame image (BGR numpy array)
            num_detections: Number of detections in frame
        """
        if aquarium_id not in self.aquarium_canvases:
            log.warning(
                "multi_aquarium_preview.invalid_aquarium_id",
                aquarium_id=aquarium_id,
                available=list(self.aquarium_canvases.keys()),
            )
            return

        try:
            # Convert BGR to RGB
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Resize to fit canvas (360x270)
            frame_resized = cv2.resize(frame_rgb, (360, 270))

            # Convert to PIL Image
            img = Image.fromarray(frame_resized)
            photo = ImageTk.PhotoImage(image=img)

            # Keep reference to prevent garbage collection
            self.aquarium_photo_images[aquarium_id] = photo

            # Update canvas
            canvas = self.aquarium_canvases[aquarium_id]
            canvas.delete("all")
            canvas.create_image(0, 0, anchor=tk.NW, image=photo)

            # Update detection count
            if aquarium_id in self.aquarium_labels:
                self.aquarium_labels[aquarium_id].config(text=f"Detecções: {num_detections}")

        except Exception as e:
            log.error(
                "multi_aquarium_preview.frame_update_failed",
                aquarium_id=aquarium_id,
                error=str(e),
            )

    def update_status_text(self, text: str, color: str = "black") -> None:
        """Update status text.

        Args:
            text: Status text to display
            color: Text color (default: black)
        """
        if self.status_label:
            self.status_label.config(text=f"Status: {text}", foreground=color)

    def _update_timer(self) -> None:
        """Update timer display."""
        if self.is_stopped:
            return

        if self.start_time:
            elapsed = time.time() - self.start_time
            remaining = max(0, self.duration_s - elapsed)

            elapsed_min = int(elapsed // 60)
            elapsed_sec = int(elapsed % 60)
            remaining_min = int(remaining // 60)
            remaining_sec = int(remaining % 60)

            if self.timer_label:
                self.timer_label.config(
                    text=(
                        f"Tempo: {elapsed_min:02d}:{elapsed_sec:02d} / "
                        f"{remaining_min:02d}:{remaining_sec:02d}"
                    )
                )

            self._update_progress(elapsed, remaining)

            # Auto-stop if time expired
            if self.duration_s > 0 and remaining <= 0 and self.on_stop_callback:
                log.info("multi_aquarium_preview.time_expired")
                self._on_stop_clicked()
                return

        # Schedule next update
        self.window.after(1000, self._update_timer)

    def _update_progress(self, elapsed: float, remaining: float) -> None:
        """Refresh determinate progress bar + ETA label."""
        if self.progress_bar is None:
            return
        if self.duration_s > 0:
            percent = max(0.0, min(100.0, (elapsed / self.duration_s) * 100.0))
            self.progress_bar.config(value=percent)
            if self.eta_label is not None:
                self.eta_label.config(text=f"ETA: {self._format_eta(remaining)}")
        elif self.eta_label is not None:
            self.eta_label.config(text="ETA: --")

    def _on_stop_clicked(self) -> None:
        """Handle stop button click."""
        if self.is_stopped:
            return

        self.is_stopped = True
        if self.stop_button:
            self.stop_button.config(state=tk.DISABLED)
        if self.status_label:
            self.status_label.config(text="Status: Parando...", foreground="orange")
        self._freeze_stop_time()

        log.info("multi_aquarium_preview.stop_clicked")

        if self.on_stop_callback:
            self.on_stop_callback()

    def _freeze_stop_time(self) -> None:
        """Record stop clock + halt indeterminate progress animation."""
        if self.stop_time_label is not None:
            self.stop_time_label.config(text=f"Fim: {self._format_clock(time.time())}")
        if self.progress_bar is not None:
            try:
                self.progress_bar.stop()
            # except Exception justified: Progressbar.stop can raise TclError
            # during teardown — defensive only.
            except Exception:  # pragma: no cover - defensive
                log.debug("multi_aquarium_preview.progress_stop_failed")
        if self.eta_label is not None:
            self.eta_label.config(text="ETA: --")

    def _on_window_close(self) -> None:
        """Handle window close event."""
        if not self.is_stopped:
            self._on_stop_clicked()
        else:
            self.window.destroy()

    def destroy(self) -> None:
        """Destroy the window."""
        try:
            self.window.destroy()
        except Exception as e:
            log.warning("multi_aquarium_preview.destroy_failed", error=str(e))
