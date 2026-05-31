"""
Analysis display widget component - video analysis tab UI.

Provides the analysis tab interface including status display, metadata labels,
track selection, progress tracking, and video display area.
"""

# Standard library imports
from tkinter import Label, StringVar, ttk

# Third-party imports
import structlog

from zebtrack.ui import payloads

# Local imports
from zebtrack.ui.components.base import BaseWidget
from zebtrack.ui.event_bus_v2 import EventBusV2, UIEvents
from zebtrack.ui.wizard.tooltip import ToolTip, create_help_label

log = structlog.get_logger()

ANALYSIS_PROFILE_TOOLTIP = (
    "Mostra a configuração de análise aplicada a esta sessão. "
    "Quando nenhuma regra específica combina com grupo, dia ou indivíduo, "
    "o projeto usa o perfil padrão. Quando aparecer 'padrão do projeto (default)', "
    "isso significa exatamente esse fallback."
)


class AnalysisDisplayWidget(BaseWidget):
    """
    Reusable analysis display widget for the video analysis tab.

    Provides:
    - Analysis status display
    - Metadata labels (task, group, day, subject, profile, tracking mode)
    - Track selector combobox
    - Social proximity summary
    - Progress bar with detailed statistics
    - Cancel analysis button
    - Video display area

    Events emitted:
    - analysis.track_selected: User selected a track ID
    - analysis.cancel_requested: User clicked cancel button
    """

    def __init__(
        self,
        parent,
        event_bus: EventBusV2 | None = None,
        available_track_options: list[str] | None = None,
        **kwargs,
    ):
        """
        Initialize the analysis display widget.

        Args:
            parent: Parent Tkinter widget
            event_bus: Optional event bus for emitting events
            available_track_options: Initial list of available tracks (default: ["Todos"])
            **kwargs: Additional arguments passed to BaseWidget
        """
        # State variables for display
        stringvar_master = parent
        self.status_var = StringVar(master=stringvar_master, value="Nenhuma análise em andamento.")
        self.task_var = StringVar(master=stringvar_master, value="Nenhuma tarefa em andamento.")
        self.group_var = StringVar(master=stringvar_master, value="Grupo: --")
        self.day_var = StringVar(master=stringvar_master, value="Dia: --")
        self.subject_var = StringVar(master=stringvar_master, value="Indivíduo: --")
        self.profile_var = StringVar(
            master=stringvar_master,
            value="Configuração de análise: default",
        )
        self.tracking_mode_var = StringVar(
            master=stringvar_master,
            value="Modo de rastreamento: --",
        )
        self.social_summary_var = StringVar(
            master=stringvar_master,
            value="Interações sociais: não aplicável no momento.",
        )
        self.track_selector_var = StringVar(master=stringvar_master, value="Todos")

        # Progress statistics
        self.progress_labels: dict[str, StringVar] = {}

        # Available track options
        self._available_track_options = available_track_options or ["Todos"]

        # Widget references
        self.status_label: ttk.Label | None = None
        self.task_label: ttk.Label | None = None
        self.group_label: ttk.Label | None = None
        self.day_label: ttk.Label | None = None
        self.subject_label: ttk.Label | None = None
        self.profile_label: ttk.Label | None = None
        self.profile_help_label: Label | None = None
        self.tracking_mode_label: ttk.Label | None = None
        self.track_selector_widget: ttk.Combobox | None = None
        self.progress_frame: ttk.Frame | None = None
        self.progress_bar: ttk.Progressbar | None = None
        self.cancel_btn: ttk.Button | None = None
        self.video_container: ttk.Frame | None = None
        self.video_label: Label | None = None

        super().__init__(parent, event_bus=event_bus, **kwargs)

    def _build_ui(self) -> None:
        """Build the analysis display widget UI."""
        # Status label at top
        self.status_label = ttk.Label(self, textvariable=self.status_var, padding=(0, 6))
        self.status_label.pack(fill="x")

        # Metadata info grid
        self._build_metadata_info()

        # Track controls
        self._build_track_controls()

        # Progress section (initially hidden)
        self._build_progress_section()

        # Video display area
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
        self.task_label = ttk.Label(info_frame, textvariable=self.task_var, padding=(0, 2))
        self.task_label.grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 2))

        # Group, day, subject, profile (second row)
        self.group_label = ttk.Label(info_frame, textvariable=self.group_var)
        self.group_label.grid(row=1, column=0, sticky="w", padx=(0, 12))

        self.day_label = ttk.Label(info_frame, textvariable=self.day_var)
        self.day_label.grid(row=1, column=1, sticky="w", padx=(0, 12))

        self.subject_label = ttk.Label(info_frame, textvariable=self.subject_var)
        self.subject_label.grid(row=1, column=2, sticky="w", padx=(0, 12))

        profile_frame = ttk.Frame(info_frame)
        profile_frame.grid(row=1, column=3, sticky="w")

        self.profile_label = ttk.Label(profile_frame, textvariable=self.profile_var)
        self.profile_label.pack(side="left")
        self.profile_help_label = create_help_label(profile_frame, ANALYSIS_PROFILE_TOOLTIP)
        self.profile_help_label.pack(side="left", padx=(4, 0))
        ToolTip(self.profile_label, ANALYSIS_PROFILE_TOOLTIP)

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
            values=self._available_track_options,
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

    def _build_progress_section(self) -> None:
        """Build the progress bar and statistics section."""
        self.progress_frame = ttk.Frame(self, padding=(0, 6))
        self.progress_frame.columnconfigure(0, weight=1)
        self.progress_frame.columnconfigure(1, weight=0)

        # Progress bar
        self.progress_bar = ttk.Progressbar(
            self.progress_frame,
            orient="horizontal",
            mode="determinate",
        )
        self.progress_bar.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 3),
        )

        # Statistics grid
        stats_container = ttk.Frame(self.progress_frame)
        stats_container.grid(row=1, column=0, sticky="ew")
        stats_container.columnconfigure((0, 1, 2), weight=1, uniform="analysis_stats")

        stats_items = [
            ("total", "Total de Frames:"),
            ("processed", "Processados:"),
            ("detected", "Frames Detectados:"),
            ("percent", "Concluído:"),
            ("elapsed", "Tempo Decorrido:"),
            ("eta", "Tempo Estimado:"),
        ]

        for idx, (key, label_text) in enumerate(stats_items):
            row = idx // 3
            col = idx % 3
            cell = ttk.Frame(stats_container, padding=(0, 2))
            pad_x = (0, 12) if col < 2 else (0, 0)
            cell.grid(row=row, column=col, padx=pad_x, sticky="w")
            ttk.Label(cell, text=label_text).pack(anchor="w")
            var = StringVar(master=self, value="-")
            ttk.Label(cell, textvariable=var, font=("Arial", 9, "bold")).pack(anchor="w")
            self.progress_labels[key] = var

        # Cancel button
        self.cancel_btn = ttk.Button(
            self.progress_frame,
            text="Cancelar Análise",
            command=self._on_cancel_clicked,
            state="disabled",
        )
        self.cancel_btn.grid(row=1, column=1, sticky="ne", padx=(12, 0))

        # Hide progress frame until analysis starts
        self.progress_frame.pack_forget()

    def _build_video_display(self) -> None:
        """Build the video display area."""
        # Video display area (fills remaining space)
        self.video_container = ttk.Frame(self)
        self.video_container.pack(expand=True, fill="both")

        self.video_label = Label(self.video_container, bg="black")
        self.video_label.pack(expand=True, fill="both")

    # Event handlers

    def _on_track_selection_changed(self, _event=None) -> None:
        """Handle track selection change."""
        selected_track = self.track_selector_var.get()
        try:
            track_id = int(selected_track)
        except (ValueError, TypeError):
            track_id = -1
        self.emit_event(
            UIEvents.ANALYSIS_TRACK_SELECTED, payloads.TrackIdPayload(track_id=track_id)
        )

    def _on_cancel_clicked(self) -> None:
        """Handle cancel button click."""
        self.emit_event(UIEvents.ANALYSIS_CANCEL_REQUESTED, payloads.EmptyPayload())

    # Public API for updating widget state

    def set_status(self, status: str) -> None:
        """Update the analysis status text."""
        self.status_var.set(status)

    def set_task(self, task: str) -> None:
        """Update the task description."""
        self.task_var.set(task)

    def set_metadata(self, group: str, day: str, subject: str, profile: str | None = None) -> None:
        """
        Update the metadata display.

        Args:
            group: Group identifier
            day: Day identifier
            subject: Subject identifier
            profile: Optional profile name
        """
        self.group_var.set(f"Grupo: {group}")
        self.day_var.set(f"Dia: {day}")
        self.subject_var.set(f"Indivíduo: {subject}")
        if profile:
            self.profile_var.set(f"Configuração de análise: {profile}")

    def set_tracking_mode(self, mode: str) -> None:
        """Update the tracking mode display."""
        self.tracking_mode_var.set(f"Modo de rastreamento: {mode}")

    def set_profile(self, profile: str) -> None:
        """Update the analysis profile display."""
        self.profile_var.set(f"Configuração de análise: {profile}")

    def set_social_summary(self, summary: str) -> None:
        """Update the social proximity summary text."""
        self.social_summary_var.set(summary)

    def update_track_options(self, tracks: list[str]) -> None:
        """
        Update the available track options in the selector.

        Args:
            tracks: List of track IDs (e.g., ["Todos", "1", "2", "3"])
        """
        self._available_track_options = tracks
        if self.track_selector_widget:
            self.track_selector_widget.config(values=tracks)

    def show_progress(self) -> None:
        """Show the progress bar and statistics section."""
        if self.progress_frame and self.video_container:
            self.progress_frame.pack(fill="x", pady=(4, 0), before=self.video_container)

    def hide_progress(self) -> None:
        """Hide the progress bar and statistics section."""
        if self.progress_frame:
            self.progress_frame.pack_forget()

    def update_progress(self, value: float) -> None:
        """
        Update the progress bar value.

        Args:
            value: Progress value between 0.0 and 1.0
        """
        if self.progress_bar:
            self.progress_bar["value"] = value * 100

    def update_progress_stats(
        self,
        total_frames: int | None = None,
        processed_frames: int | None = None,
        detected_frames: int | None = None,
        percent: str | None = None,
        elapsed: str | None = None,
        eta: str | None = None,
    ) -> None:
        """
        Update progress statistics labels.

        Args:
            total_frames: Total frame count
            processed_frames: Processed frame count
            detected_frames: Detected frame count
            percent: Completion percentage string
            elapsed: Elapsed time string
            eta: ETA time string
        """
        if total_frames is not None:
            self.progress_labels["total"].set(str(total_frames))
        if processed_frames is not None:
            self.progress_labels["processed"].set(str(processed_frames))
        if detected_frames is not None:
            self.progress_labels["detected"].set(str(detected_frames))
        if percent is not None:
            self.progress_labels["percent"].set(percent)
        if elapsed is not None:
            self.progress_labels["elapsed"].set(elapsed)
        if eta is not None:
            self.progress_labels["eta"].set(eta)

    def enable_cancel_button(self) -> None:
        """Enable the cancel button."""
        if self.cancel_btn:
            self.cancel_btn.config(state="normal")

    def disable_cancel_button(self) -> None:
        """Disable the cancel button."""
        if self.cancel_btn:
            self.cancel_btn.config(state="disabled")

    def clear_video_display(self) -> None:
        """Clear the video display."""
        if self.video_label:
            self.video_label.config(image="")
            self.video_label.image = None  # type: ignore[attr-defined]

    def update_frame(self, image) -> None:
        """
        Update the video display with a new frame.

        Args:
            image: PIL.Image or ImageTk.PhotoImage object to display
        """
        if not self.video_label:
            return

        try:
            from PIL import ImageTk

            # If it's already a PhotoImage, use it directly
            if isinstance(image, ImageTk.PhotoImage):
                tk_image = image
            else:
                # Convert PIL Image to PhotoImage
                tk_image = ImageTk.PhotoImage(image)

            self.video_label.configure(image=tk_image)
            self.video_label.image = tk_image  # type: ignore[attr-defined]  # Keep reference to prevent garbage collection
        except Exception as e:
            log.error("analysis_display.update_frame.error", error=str(e))

    def reset_to_defaults(self) -> None:
        """Reset all displays to default values."""
        self.set_status("Nenhuma análise em andamento.")
        self.set_task("Nenhuma tarefa em andamento.")
        self.set_metadata("--", "--", "--")
        self.set_tracking_mode("--")
        self.set_profile("default")
        self.set_social_summary("Interações sociais: aguardando dados.")
        self.track_selector_var.set("Todos")
        self.hide_progress()
        self.disable_cancel_button()
        self.clear_video_display()

        # Reset progress stats
        for var in self.progress_labels.values():
            var.set("-")
