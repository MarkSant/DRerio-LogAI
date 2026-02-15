"""Control panel widget component - recording and detector controls."""

from tkinter import BooleanVar, Button, StringVar, ttk

import structlog

from zebtrack.ui.components.base import BaseWidget
from zebtrack.ui.event_bus import EventBus
from zebtrack.ui.events import Events

log = structlog.get_logger()


class ControlPanelWidget(BaseWidget):
    """
    Reusable control panel widget for recording and detector controls.

    Provides:
    - Start/Stop recording buttons
    - Process video button
    - Detector initialization controls
    - Preview and interval settings

    Events emitted:
    - control.start_recording: User clicked start recording
    - control.stop_recording: User clicked stop recording
    - control.process_video: User clicked process video
    - control.preview_toggled: User toggled preview checkbox
    - control.interval_changed: User changed processing interval
    """

    def __init__(self, parent, event_bus: EventBus | None = None, **kwargs):
        """
        Initialize the control panel widget.

        Args:
            parent: Parent Tkinter widget
            event_bus: Optional event bus for emitting events
            **kwargs: Additional arguments passed to BaseWidget
        """
        # State variables
        self.show_preview_var = BooleanVar(value=True)
        self.processing_interval_var = StringVar(value="10")

        # Widget references
        self.start_rec_btn: Button | None = None
        self.stop_rec_btn: Button | None = None
        self.process_video_btn: ttk.Button | None = None

        super().__init__(parent, event_bus=event_bus, **kwargs)

    def _build_ui(self) -> None:
        """Build the control panel widget UI."""
        # Title
        title_label = ttk.Label(
            self,
            text="Controles de Gravação e Processamento",
            font=("TkDefaultFont", 10, "bold"),
        )
        title_label.pack(pady=(0, 10))

        # Recording controls
        recording_frame = ttk.LabelFrame(self, text="Gravação", padding=10)
        recording_frame.pack(fill="x", pady=5)

        btn_frame = ttk.Frame(recording_frame)
        btn_frame.pack(fill="x")

        self.start_rec_btn = Button(
            btn_frame,
            text="▶️ Iniciar Gravação",
            command=self._on_start_recording_clicked,
            bg="#4CAF50",
            fg="white",
            font=("TkDefaultFont", 10, "bold"),
            padx=20,
            pady=10,
        )
        self.start_rec_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.stop_rec_btn = Button(
            btn_frame,
            text="⏹️ Parar Gravação",
            command=self._on_stop_recording_clicked,
            bg="#f44336",
            fg="white",
            font=("TkDefaultFont", 10, "bold"),
            padx=20,
            pady=10,
            state="disabled",
        )
        self.stop_rec_btn.pack(side="left", fill="x", expand=True, padx=(5, 0))

        # Processing controls
        processing_frame = ttk.LabelFrame(self, text="Processamento", padding=10)
        processing_frame.pack(fill="x", pady=5)

        self.process_video_btn = ttk.Button(
            processing_frame,
            text="🎬 Processar Vídeo",
            command=self._on_process_video_clicked,
        )
        self.process_video_btn.pack(fill="x", pady=5)

        # Settings
        settings_frame = ttk.LabelFrame(self, text="Configurações", padding=10)
        settings_frame.pack(fill="x", pady=5)

        # Preview checkbox
        preview_check = ttk.Checkbutton(
            settings_frame,
            text="Mostrar Preview Durante Processamento",
            variable=self.show_preview_var,
            command=self._on_preview_toggled,
        )
        preview_check.pack(anchor="w")

        # Interval setting
        interval_frame = ttk.Frame(settings_frame)
        interval_frame.pack(fill="x", pady=(5, 0))

        ttk.Label(interval_frame, text="Intervalo de Processamento (frames):").pack(
            side="left", padx=(0, 5)
        )
        interval_entry = ttk.Entry(
            interval_frame, textvariable=self.processing_interval_var, width=10
        )
        interval_entry.pack(side="left")
        interval_entry.bind("<Return>", self._on_interval_changed)
        interval_entry.bind("<FocusOut>", self._on_interval_changed)

    # Event handlers

    def _on_start_recording_clicked(self) -> None:
        """Handle start recording button click."""
        if self.event_bus:
            self.event_bus.publish_event(Events.RECORDING_START, {})

    def _on_stop_recording_clicked(self) -> None:
        """Handle stop recording button click."""
        if self.event_bus:
            self.event_bus.publish_event(Events.RECORDING_STOP, {})

    def _on_process_video_clicked(self) -> None:
        """Handle process video button click."""
        if self.event_bus:
            self.event_bus.publish_event(Events.UI_REQUEST_PROCESS_VIDEOS, {})

    def _on_preview_toggled(self) -> None:
        """Handle preview checkbox toggle."""
        self.emit_event("control.preview_toggled", {"enabled": self.show_preview_var.get()})

    def _on_interval_changed(self, event=None) -> None:
        """Handle processing interval change."""
        try:
            interval = int(self.processing_interval_var.get())
            self.emit_event("control.interval_changed", {"interval": interval})
        except ValueError:
            self._log.warning(
                "control_panel.invalid_interval",
                value=self.processing_interval_var.get(),
            )

    # Public API for controlling widget state

    def set_recording_state(self, is_recording: bool) -> None:
        """Update button states based on recording state."""
        if is_recording:
            if self.start_rec_btn:
                self.start_rec_btn.config(state="disabled")
            if self.stop_rec_btn:
                self.stop_rec_btn.config(state="normal")
        else:
            if self.start_rec_btn:
                self.start_rec_btn.config(state="normal")
            if self.stop_rec_btn:
                self.stop_rec_btn.config(state="disabled")

    def set_processing_enabled(self, enabled: bool) -> None:
        """Enable or disable the process video button."""
        if self.process_video_btn:
            self.process_video_btn.config(state="normal" if enabled else "disabled")
