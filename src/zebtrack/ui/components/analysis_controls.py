"""Analysis controls widget component - analysis tab controls and status display."""

from tkinter import Label, StringVar, ttk

import structlog
from PIL import Image, ImageTk

from zebtrack.ui.components.base import BaseWidget
from zebtrack.ui.event_bus import EventBus

log = structlog.get_logger()


class AnalysisControlsWidget(BaseWidget):
    """
    Reusable analysis controls widget for video analysis controls and display.

    Provides:
    - Analysis status display
    - Metadata labels (group, day, subject, task)
    - Tracking mode indicator
    - Track selector combobox
    - Social proximity summary
    - Video display label

    Events emitted:
    - analysis.track_selected: User selected a track ID
    """

    def __init__(self, parent, event_bus: EventBus | None = None, **kwargs):
        """
        Initialize the analysis controls widget.

        Args:
            parent: Parent Tkinter widget
            event_bus: Optional event bus for emitting events
            **kwargs: Additional arguments passed to BaseWidget
        """
        # State variables
        self.analysis_status_var = StringVar(value="Nenhuma análise em andamento.")
        self.analysis_metadata_var = StringVar(value="")
        self.analysis_group_var = StringVar(value="Grupo: --")
        self.analysis_day_var = StringVar(value="Dia: --")
        self.analysis_subject_var = StringVar(value="Indivíduo: --")
        self.analysis_task_var = StringVar(value="Tarefa: --")
        self.tracking_mode_var = StringVar(value="Modo de rastreamento: Multi-indivíduos")
        self.analysis_profile_var = StringVar(value="Perfil de análise: default")
        self.track_selector_var = StringVar(value="Todos")
        self.social_summary_var = StringVar(value="Interações sociais: aguardando dados.")

        # Widget references
        self.analysis_status_label: ttk.Label | None = None
        self.analysis_task_label: ttk.Label | None = None
        self.analysis_group_label: ttk.Label | None = None
        self.analysis_day_label: ttk.Label | None = None
        self.analysis_subject_label: ttk.Label | None = None
        self.tracking_mode_label: ttk.Label | None = None
        self.analysis_profile_label: ttk.Label | None = None
        self.track_selector_widget: ttk.Combobox | None = None
        self.analysis_video_label: Label | None = None

        super().__init__(parent, event_bus=event_bus, **kwargs)

    def _build_ui(self) -> None:
        """Build the analysis controls widget UI."""
        # Status label at top
        self.analysis_status_label = ttk.Label(
            self, textvariable=self.analysis_status_var, padding=(0, 6)
        )
        self.analysis_status_label.pack(fill="x")

        # Metadata info grid
        self._build_metadata_info()

        # Track controls
        self._build_track_controls()

        # Video display
        self._build_video_display()

    def _build_metadata_info(self) -> None:
        """Build the metadata information grid."""
        info_frame = ttk.Frame(self, padding=(0, 2))
        info_frame.pack(fill="x")
        info_frame.columnconfigure(0, weight=1, uniform="analysis_info")
        info_frame.columnconfigure(1, weight=1, uniform="analysis_info")
        info_frame.columnconfigure(2, weight=1, uniform="analysis_info")
        info_frame.columnconfigure(3, weight=1, uniform="analysis_info")

        # Task label (full width)
        self.analysis_task_label = ttk.Label(
            info_frame, textvariable=self.analysis_task_var, padding=(0, 2)
        )
        self.analysis_task_label.grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 2))

        # Group, day, subject, profile (second row)
        self.analysis_group_label = ttk.Label(info_frame, textvariable=self.analysis_group_var)
        self.analysis_group_label.grid(row=1, column=0, sticky="w", padx=(0, 12))

        self.analysis_day_label = ttk.Label(info_frame, textvariable=self.analysis_day_var)
        self.analysis_day_label.grid(row=1, column=1, sticky="w", padx=(0, 12))

        self.analysis_subject_label = ttk.Label(info_frame, textvariable=self.analysis_subject_var)
        self.analysis_subject_label.grid(row=1, column=2, sticky="w", padx=(0, 12))

        self.analysis_profile_label = ttk.Label(info_frame, textvariable=self.analysis_profile_var)
        self.analysis_profile_label.grid(row=1, column=3, sticky="w")

        # Tracking mode (third row)
        self.tracking_mode_label = ttk.Label(info_frame, textvariable=self.tracking_mode_var)
        self.tracking_mode_label.grid(row=2, column=0, columnspan=4, sticky="w", pady=(2, 2))

    def _build_track_controls(self) -> None:
        """Build the track selector controls."""
        controls_frame = ttk.Frame(self, padding=(0, 4))
        controls_frame.pack(fill="x", pady=(4, 0))

        ttk.Label(controls_frame, text="Track ID ativo:").grid(row=0, column=0, sticky="w")

        self.track_selector_widget = ttk.Combobox(
            controls_frame,
            textvariable=self.track_selector_var,
            state="readonly",
            values=["Todos"],
            width=14,
        )
        self.track_selector_widget.grid(row=0, column=1, padx=(6, 12), sticky="w")
        self.track_selector_widget.bind("<<ComboboxSelected>>", self._on_track_selection_changed)

        ttk.Label(
            controls_frame,
            textvariable=self.social_summary_var,
            wraplength=360,
            justify="left",
        ).grid(row=0, column=2, sticky="w")
        controls_frame.columnconfigure(2, weight=1)

    def _build_video_display(self) -> None:
        """Build the video display area."""
        video_frame = ttk.LabelFrame(self, text="Análise de Vídeo", padding=5)
        video_frame.pack(fill="both", expand=True, pady=(10, 0))

        self.analysis_video_label = Label(video_frame, bg="black")
        self.analysis_video_label.pack(fill="both", expand=True)

    # Event handlers

    def _on_track_selection_changed(self, event) -> None:
        """Handle track selection change."""
        selected_track = self.track_selector_var.get()
        self.emit_event("analysis.track_selected", {"track_id": selected_track})

    # Public API for updating widget state

    def set_status(self, status: str) -> None:
        """Update the analysis status text."""
        self.analysis_status_var.set(status)

    def set_metadata(self, group: str, day: str, subject: str, task: str = "") -> None:
        """
        Update the metadata display.

        Args:
            group: Group identifier
            day: Day identifier
            subject: Subject identifier
            task: Optional task description
        """
        self.analysis_group_var.set(f"Grupo: {group}")
        self.analysis_day_var.set(f"Dia: {day}")
        self.analysis_subject_var.set(f"Indivíduo: {subject}")
        if task:
            self.analysis_task_var.set(f"Tarefa: {task}")

    def set_tracking_mode(self, mode: str) -> None:
        """Update the tracking mode display."""
        self.tracking_mode_var.set(f"Modo de rastreamento: {mode}")

    def set_profile(self, profile: str) -> None:
        """Update the analysis profile display."""
        self.analysis_profile_var.set(f"Perfil de análise: {profile}")

    def set_social_summary(self, summary: str) -> None:
        """Update the social proximity summary text."""
        self.social_summary_var.set(summary)

    def update_track_options(self, tracks: list[str]) -> None:
        """
        Update the available track options in the selector.

        Args:
            tracks: List of track IDs (e.g., ["Todos", "1", "2", "3"])
        """
        if self.track_selector_widget:
            self.track_selector_widget.config(values=tracks)

    def display_frame(self, image: Image.Image) -> None:
        """
        Display a video frame in the analysis video label.

        Args:
            image: PIL Image to display
        """
        if not self.analysis_video_label:
            return

        # Convert to PhotoImage and display
        photo = ImageTk.PhotoImage(image)
        self.analysis_video_label.config(image=photo)
        self.analysis_video_label.image = photo  # Keep a reference

    def clear_frame(self) -> None:
        """Clear the video display."""
        if self.analysis_video_label:
            self.analysis_video_label.config(image="")
            self.analysis_video_label.image = None
