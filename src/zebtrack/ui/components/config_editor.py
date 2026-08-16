"""
Configuration editor widget component - advanced settings editor.

Provides a form-based interface for editing application configuration
parameters across multiple categories: video processing, trajectory
smoothing, recorder settings, and ROI parameters.
"""

from pathlib import Path
from tkinter import BooleanVar, StringVar, TclError, ttk
from typing import Any

import structlog

from zebtrack.core.services.roi_rule_resolver import (
    DEFAULT_BBOX_OVERLAP_BASIS,
    DEFAULT_BUFFER_RADIUS_VALUE,
    DEFAULT_MIN_BBOX_OVERLAP_RATIO,
    DEFAULT_ROI_INCLUSION_RULE,
)
from zebtrack.i18n import _
from zebtrack.ui import payloads
from zebtrack.ui.components.base import BaseWidget
from zebtrack.ui.components.behavioral_config_widget import BehavioralConfigWidget
from zebtrack.ui.event_bus_v2 import EventBusV2, UIEvents
from zebtrack.ui.wizard.tooltip import create_help_label

log = structlog.get_logger()


def seg_overlap_missing_masks_warning() -> str:
    """Warning shown when ``seg_overlap`` is picked without the mask sidecar.

    A function rather than a module constant: a constant would call ``_()``
    at import time and freeze the text in whatever language was installed
    then -- usually none.
    """
    return _(
        "⚠️ 'seg_overlap' without 'Save Masks' enabled: the analysis will "
        "degrade to 'bbox_intersects'. Turn the option on in the 'Data "
        "Recording' section and confirm the model does segmentation "
        "(model_selection.animal_method = 'seg')."
    )


class ConfigEditorWidget(BaseWidget):
    """
    Reusable configuration editor widget.

    Provides:
    - Video processing settings (FPS, interval, offset)
    - Trajectory smoothing (window length, polynomial order)
    - Recorder settings (flush interval, row limit)
    - ROI parameters (inclusion rule, buffer, overlap)
    - Behavioral Analysis defaults (perspective, geotaxis)
    - Action buttons (save, reset)

    Events emitted:
    - config.save_requested: User clicked save (payload: dict of values)
    - config.reset_requested: User clicked reset
    - config.roi_rule_changed: ROI rule selection changed
    """

    def __init__(self, parent, event_bus: EventBusV2 | None = None, **kwargs):
        """
        Initialize configuration editor widget.

        Args:
            parent: Parent Tkinter widget
            event_bus: Optional event bus for event emission
            **kwargs: Additional arguments for ttk.Frame
        """
        # Initialize all StringVar instances with default values
        self.fps_var = StringVar(value="30")
        self.processing_interval_var = StringVar(value="10")
        self.display_interval_var = StringVar(value="10")
        self.processing_offset_var = StringVar(value="0")
        self.window_length_var = StringVar(value="7")
        self.polyorder_var = StringVar(value="3")
        self.flush_interval_var = StringVar(value="5.0")
        self.flush_rows_var = StringVar(value="500")
        # Default do modelo Pydantic (RecorderSettings.persist_masks): desligado.
        self.persist_masks_var = BooleanVar(value=False)
        # Defaults da fonte canônica: o formulário é repopulado por
        # ``set_values`` a partir do ``Settings``, mas até lá não deve exibir
        # números inventados aqui.
        self.roi_inclusion_rule_var = StringVar(value=DEFAULT_ROI_INCLUSION_RULE)
        self.roi_buffer_radius_var = StringVar(value=f"{DEFAULT_BUFFER_RADIUS_VALUE:g}")
        self.roi_overlap_ratio_var = StringVar(value=f"{DEFAULT_MIN_BBOX_OVERLAP_RATIO:g}")
        self.roi_overlap_basis_var = StringVar(value=DEFAULT_BBOX_OVERLAP_BASIS)

        # ROI rule widgets list for conditional enable/disable
        self._roi_rule_widgets: list[ttk.Widget] = []
        self._seg_overlap_warning_label: ttk.Label | None = None

        self.behavioral_config_widget: BehavioralConfigWidget | None = None
        self._detection_summary_frame: ttk.LabelFrame | None = None

        super().__init__(parent, event_bus=event_bus, **kwargs)

    def _build_ui(self) -> None:
        """Build the configuration editor UI with 2-column layout."""
        self._build_intro()

        # Create 2-column container for better horizontal space usage
        columns_frame = ttk.Frame(self)
        columns_frame.pack(fill="both", expand=True, pady=(0, 10))
        columns_frame.columnconfigure(0, weight=1)  # Left column
        columns_frame.columnconfigure(1, weight=1)  # Right column

        # LEFT COLUMN: Video Processing, Smoothing, Recorder
        left_column = ttk.Frame(columns_frame)
        left_column.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        self._build_video_processing_section(left_column)
        self._build_trajectory_smoothing_section(left_column)
        self._build_recorder_section(left_column)
        self._build_action_buttons(left_column)  # Place buttons in left column (empty space)

        # RIGHT COLUMN: ROI, Behavioral Analysis
        right_column = ttk.Frame(columns_frame)
        right_column.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        self._build_roi_section(right_column)
        self._build_behavioral_analysis_section(right_column)
        self._build_detection_summary_section(right_column)

    def _build_behavioral_analysis_section(self, parent=None) -> None:
        """Build behavioral analysis default settings."""
        container = parent if parent else self
        behavioral_frame = ttk.LabelFrame(
            container,
            text=_("Behavioural Analysis Defaults"),
            padding=10,
        )
        behavioral_frame.pack(fill="x", pady=6)

        self.behavioral_config_widget = BehavioralConfigWidget(
            behavioral_frame,
            event_bus=self.event_bus,
            default_perspective="lateral",
            default_geotaxis_mode="zones",
        )
        self.behavioral_config_widget.pack(fill="x", expand=True)

    def _build_intro(self) -> None:
        """Build introduction text."""
        intro = _(
            "Edit advanced config.yaml parameters without leaving the application. "
            "Changes are persisted to config.local.yaml and reloaded automatically "
            "by settings.load_settings()."
        )
        ttk.Label(
            self,
            text=intro,
            wraplength=560,
            justify="left",
        ).pack(fill="x", pady=(0, 12))

        config_path_hint = ttk.Label(
            self,
            text=_("Monitored files: {default} → {local}").format(
                default=Path("config.yaml").absolute(),
                local=Path("config.local.yaml").absolute(),
            ),
            wraplength=560,
            justify="left",
            font=("TkDefaultFont", 8),
        )
        config_path_hint.pack(fill="x", pady=(0, 12))

    def _build_video_processing_section(self, parent=None) -> None:
        """Build video processing settings frame."""
        container = parent if parent else self
        video_frame = ttk.LabelFrame(
            container,
            text=_("Video Processing"),
            padding=10,
        )
        video_frame.pack(fill="x", pady=6)

        # Grid: Label | Help | Entry | Extra
        video_frame.columnconfigure(1, weight=0)
        video_frame.columnconfigure(2, weight=0)
        video_frame.columnconfigure(3, weight=1)

        # FPS
        ttk.Label(video_frame, text=_("Output FPS (MP4):")).grid(
            row=0, column=0, sticky="w", padx=(0, 2), pady=2
        )
        create_help_label(
            video_frame,
            _(
                "Output FPS (Frames Per Second)\n\n"
                "Sets the playback speed of the .mp4 produced by the analysis.\n"
                "• Recommended: the same value as the original video (e.g. 30).\n"
                "• Higher: the video looks sped up.\n"
                "• Lower: the video looks like slow motion."
            ),
        ).grid(row=0, column=1, padx=2)
        ttk.Entry(video_frame, textvariable=self.fps_var, width=8).grid(
            row=0, column=2, sticky="w", padx=5
        )

        # Processing interval
        ttk.Label(video_frame, text=_("Processing Interval (N):")).grid(
            row=1, column=0, sticky="w", padx=(0, 2), pady=2
        )
        create_help_label(
            video_frame,
            _(
                "Processing Interval (Analysis)\n\n"
                "Processes 1 frame every N original frames.\n"
                "• N=1: processes EVERY frame (maximum precision, slowest).\n"
                "• N=10: processes 1 frame and skips 9 (faster, ideal for long videos).\n"
                "• Higher: cuts processing time dramatically.\n"
                "• Lower: improves the temporal resolution of speed metrics."
            ),
        ).grid(row=1, column=1, padx=2)
        ttk.Entry(video_frame, textvariable=self.processing_interval_var, width=8).grid(
            row=1, column=2, sticky="w", padx=5
        )

        # Display interval
        ttk.Label(video_frame, text=_("Display Interval (N):")).grid(
            row=2, column=0, sticky="w", padx=(0, 2), pady=2
        )
        create_help_label(
            video_frame,
            _(
                "Display Interval (UI)\n\n"
                "Refreshes the on-screen image every N processed frames.\n"
                "• N=1: smooth display (uses more CPU/GPU).\n"
                "• N=30: refreshes every 30 frames (lighter).\n"
                "• Useful to speed the analysis up by saving visual resources."
            ),
        ).grid(row=2, column=1, padx=2)
        ttk.Entry(video_frame, textvariable=self.display_interval_var, width=8).grid(
            row=2, column=2, sticky="w", padx=5
        )

        # Processing offset
        ttk.Label(video_frame, text=_("Initial Offset (frames):")).grid(
            row=3, column=0, sticky="w", padx=(0, 2), pady=2
        )
        create_help_label(
            video_frame,
            _(
                "Initial Offset\n\n"
                "Number of leading frames to ignore before tracking starts.\n"
                "• Use it to discard the water settling down or the experimenter's "
                "hand leaving the scene.\n"
                "• E.g. in a 30fps video, an offset of 90 frames skips the first "
                "3 seconds."
            ),
        ).grid(row=3, column=1, padx=2)
        ttk.Entry(video_frame, textvariable=self.processing_offset_var, width=8).grid(
            row=3, column=2, sticky="w", padx=5
        )

    def _build_trajectory_smoothing_section(self, parent=None) -> None:
        """Build trajectory smoothing settings frame."""
        container = parent if parent else self
        smoothing_frame = ttk.LabelFrame(
            container,
            text=_("Trajectory Smoothing (Savitzky-Golay Filter)"),
            padding=10,
        )
        smoothing_frame.pack(fill="x", pady=6)

        # Grid: Label | Help | Entry
        smoothing_frame.columnconfigure(1, weight=0)
        smoothing_frame.columnconfigure(2, weight=0)
        smoothing_frame.columnconfigure(3, weight=1)

        # Window Length
        ttk.Label(smoothing_frame, text=_("Smoothing Window:")).grid(
            row=0, column=0, sticky="w", padx=(0, 2), pady=2
        )
        create_help_label(
            smoothing_frame,
            _(
                "Smoothing Window (Window Length)\n\n"
                "Number of frames used to smooth the trajectory. MUST BE ODD.\n"
                "• Higher (e.g. 11, 15): removes more noise/jitter, but may round "
                "the curves off too much.\n"
                "• Lower (e.g. 3, 5): keeps more detail of abrupt movements.\n"
                "• Default: 7"
            ),
        ).grid(row=0, column=1, padx=2)
        ttk.Entry(smoothing_frame, textvariable=self.window_length_var, width=8).grid(
            row=0, column=2, sticky="w", padx=5
        )

        # Polynomial Order
        ttk.Label(smoothing_frame, text=_("Polynomial Order:")).grid(
            row=1, column=0, sticky="w", padx=(0, 2), pady=2
        )
        create_help_label(
            smoothing_frame,
            _(
                "Polynomial Order (Polyorder)\n\n"
                "Complexity of the curve fitted through the points. Must be SMALLER "
                "than the window.\n"
                "• 1: straight line (aggressive smoothing).\n"
                "• 2: simple curve (parabola).\n"
                "• 3: more complex curve (recommended).\n"
                "• Higher: the curve follows the original points more closely.\n"
                "• Default: 3"
            ),
        ).grid(row=1, column=1, padx=2)
        ttk.Entry(smoothing_frame, textvariable=self.polyorder_var, width=8).grid(
            row=1, column=2, sticky="w", padx=5
        )

        # Overall explanation
        ttk.Label(
            smoothing_frame,
            text=_(
                "ℹ️ This filter removes small detection jitter without losing the real "
                "track. Useful for more accurate distance and speed metrics."
            ),
            font=("TkDefaultFont", 8),
            foreground="#2563eb",
            justify="left",
            wraplength=550,
        ).grid(row=2, column=0, columnspan=4, sticky="w", padx=(0, 6), pady=(8, 0))

    def _build_recorder_section(self, parent=None) -> None:
        """Build recorder settings frame."""
        container = parent if parent else self
        recorder_frame = ttk.LabelFrame(
            container,
            text=_("Data Recording (Recorder)"),
            padding=10,
        )
        recorder_frame.pack(fill="x", pady=6)

        # Grid: Label | Help | Entry
        recorder_frame.columnconfigure(1, weight=0)
        recorder_frame.columnconfigure(2, weight=0)
        recorder_frame.columnconfigure(3, weight=1)

        # Flush interval
        ttk.Label(recorder_frame, text=_("Automatic Flush (s):")).grid(
            row=0, column=0, sticky="w", padx=(0, 2), pady=2
        )
        create_help_label(
            recorder_frame,
            _(
                "Flush Interval (Time)\n\n"
                "Every X seconds the system forces the in-memory data out to the "
                "Parquet file.\n"
                "• Protects against data loss if the app crashes.\n"
                "• Low values (e.g. 1.0) increase disk usage.\n"
                "• Default: 5.0s"
            ),
        ).grid(row=0, column=1, padx=2)
        ttk.Entry(recorder_frame, textvariable=self.flush_interval_var, width=8).grid(
            row=0, column=2, sticky="w", padx=5
        )

        # Flush rows
        ttk.Label(recorder_frame, text=_("Row Limit (Flush):")).grid(
            row=1, column=0, sticky="w", padx=(0, 2), pady=2
        )
        create_help_label(
            recorder_frame,
            _(
                "Row Limit for Flush\n\n"
                "Writes data out as soon as X rows are held in memory.\n"
                "• Default: 500 rows."
            ),
        ).grid(row=1, column=1, padx=2)
        ttk.Entry(recorder_frame, textvariable=self.flush_rows_var, width=8).grid(
            row=1, column=2, sticky="w", padx=5
        )

        # Persistência de máscaras de segmentação
        ttk.Label(recorder_frame, text=_("Save Masks (Segmentation):")).grid(
            row=2, column=0, sticky="w", padx=(0, 2), pady=2
        )
        create_help_label(
            recorder_frame,
            _(
                "Save Segmentation Masks\n\n"
                "Writes the 3b_Mascaras_<video>.parquet sidecar with the mask of "
                "every detection.\n"
                "• It is the ONLY source of masks for the 'seg_overlap' ROI rule.\n"
                "• Cost: an extra file on disk and mask decoding during tracking. "
                "Turned off it costs nothing.\n\n"
                "Turning this key on alone does NOT enable 'seg_overlap'. The three "
                "prerequisites must hold together:\n"
                "  1. recorder.persist_masks (this option)\n"
                "  2. model_selection.animal_method = 'seg' (segmentation model)\n"
                "  3. the 'seg_overlap' ROI rule selected\n"
                "If any is missing the analysis falls back to 'bbox_intersects' and "
                "records the warning in the report.\n"
                "• Default: off."
            ),
        ).grid(row=2, column=1, padx=2)
        ttk.Checkbutton(
            recorder_frame,
            variable=self.persist_masks_var,
            text=_("Required for the 'seg_overlap' ROI rule"),
        ).grid(row=2, column=2, columnspan=2, sticky="w", padx=5)

    def _build_roi_section(self, parent=None) -> None:
        """Build ROI parameters frame."""
        container = parent if parent else self
        roi_frame = ttk.LabelFrame(
            container,
            text=_("ROI Inclusion Logic (Default)"),
            padding=10,
        )
        roi_frame.pack(fill="x", pady=6)

        # Grid: Label | Help | Entry
        roi_frame.columnconfigure(1, weight=0)
        roi_frame.columnconfigure(2, weight=0)
        roi_frame.columnconfigure(3, weight=1)

        # Inclusion rule
        ttk.Label(roi_frame, text=_("Inclusion Rule:")).grid(
            row=0, column=0, sticky="w", padx=(0, 2), pady=2
        )
        create_help_label(
            roi_frame,
            _(
                "ROI Inclusion Logic\n\n"
                "Defines when the fish counts as 'inside' a zone.\n"
                "• Centroid (centroid_in): only if the centre point is in the zone.\n"
                "• Centroid w/ Buffer: expands the zone virtually for the calculation.\n"
                "• BBox Intersection: if any part of the fish's box touches the zone.\n"
                "• Seg Overlap: based on the pixel mask (most accurate).\n\n"
                "'seg_overlap' needs two more things besides this rule: "
                "recorder.persist_masks enabled (the 'Save Masks' option above) and "
                "model_selection.animal_method = 'seg'. If either is missing the "
                "analysis degrades to 'bbox_intersects' and warns in the report."
            ),
        ).grid(row=0, column=1, padx=2)

        config_roi_combo = ttk.Combobox(
            roi_frame,
            textvariable=self.roi_inclusion_rule_var,
            values=[
                "centroid_in",
                "centroid_in_on_buffered_roi",
                "bbox_intersects",
                "seg_overlap",
            ],
            state="readonly",
            width=28,
        )
        config_roi_combo.grid(row=0, column=2, sticky="w", padx=5)
        config_roi_combo.bind("<<ComboboxSelected>>", self._on_roi_rule_changed)
        self._roi_rule_widgets.append(config_roi_combo)
        # Kept so the Zone tab's "Configure in Advanced Settings" shortcut can
        # land the user directly on the control they came for.
        self._roi_rule_combo = config_roi_combo

        # Buffer radius
        ttk.Label(roi_frame, text=_("Buffer Radius (r):")).grid(
            row=1, column=0, sticky="w", padx=(0, 2), pady=2
        )
        create_help_label(
            roi_frame,
            _(
                "Buffer Radius\n\n"
                "Extra distance the ROI is expanded by in the 'Centroid w/ Buffer' "
                "rule.\n"
                "• Unit: centimetres (if calibrated) or pixels."
            ),
        ).grid(row=1, column=1, padx=2)
        ttk.Entry(roi_frame, textvariable=self.roi_buffer_radius_var, width=8).grid(
            row=1, column=2, sticky="w", padx=5
        )

        # Overlap ratio
        ttk.Label(roi_frame, text=_("Minimum Overlap:")).grid(
            row=2, column=0, sticky="w", padx=(0, 2), pady=2
        )
        create_help_label(
            roi_frame,
            _(
                "Minimum Overlap Fraction\n\n"
                "Minimum area (0 to 1) that must be inside the zone to count.\n"
                "• E.g. 0.50 means half of the reference area inside the zone.\n"
                "• 0 (only in the 'BBox Intersection' rule): any real overlap counts; "
                "merely touching the border does not."
            ),
        ).grid(row=2, column=1, padx=2)
        ttk.Entry(roi_frame, textvariable=self.roi_overlap_ratio_var, width=8).grid(
            row=2, column=2, sticky="w", padx=5
        )

        # Overlap basis (denominator of the fraction above)
        ttk.Label(roi_frame, text=_("Overlap Basis:")).grid(
            row=3, column=0, sticky="w", padx=(0, 2), pady=2
        )
        create_help_label(
            roi_frame,
            _(
                "Basis (denominator) of the Overlap Fraction\n\n"
                "Defines WHAT the fraction is measured against.\n"
                "• bbox: fraction of the fish's box that is in the zone (historical).\n"
                "• roi: fraction of the zone that is covered by the box.\n"
                "• max: the larger of the two — recommended for small zones, where "
                "'bbox' underestimates (a box 4x bigger than the zone, covering it "
                "entirely, scores only 0.25)."
            ),
        ).grid(row=3, column=1, padx=2)
        config_basis_combo = ttk.Combobox(
            roi_frame,
            textvariable=self.roi_overlap_basis_var,
            values=["bbox", "roi", "max"],
            state="readonly",
            width=28,
        )
        config_basis_combo.grid(row=3, column=2, sticky="w", padx=5)
        self._roi_rule_widgets.append(config_basis_combo)

        # Aviso pró-ativo de pré-requisito faltando para 'seg_overlap'. Vale a
        # pena aqui porque as duas chaves envolvidas moram NESTE mesmo widget:
        # sem ele o operador só descobre a degradação no relatório, depois da
        # sessão.
        self._seg_overlap_warning_label = ttk.Label(
            roi_frame,
            text="",
            font=("TkDefaultFont", 8),
            foreground="#b45309",
            justify="left",
            wraplength=520,
        )
        self._seg_overlap_warning_label.grid(row=4, column=0, columnspan=4, sticky="w", pady=(6, 0))
        self.persist_masks_var.trace_add("write", lambda *_: self._refresh_seg_overlap_warning())
        self._refresh_seg_overlap_warning()

        # Hint
        ttk.Label(
            roi_frame,
            text=_(
                "💡 Tip: these are GLOBAL settings. You can change them per project "
                "in the Zones tab."
            ),
            font=("TkDefaultFont", 8),
            foreground="#555555",
        ).grid(row=5, column=0, columnspan=4, sticky="w", pady=(6, 0))

    def focus_roi_section(self) -> None:
        """Give keyboard focus to the ROI inclusion-rule combobox.

        Target of the Zone tab's shortcut. The Advanced Settings tab is not
        scrollable, so "go to the ROI section" means focusing its first control;
        without this the user lands on a dense two-column page and has to hunt
        for the setting they explicitly asked to edit.
        """
        combo = getattr(self, "_roi_rule_combo", None)
        if combo is None:
            return
        try:
            combo.focus_set()
        # except TclError justified: the widget may be torn down mid-navigation;
        # failing to focus must never break tab switching.
        except TclError:
            log.debug("config_editor.focus_roi_section.failed", exc_info=True)

    def _build_detection_summary_section(self, parent=None) -> None:
        """Build read-only summary of detection/model parameters with edit button."""
        container = parent if parent else self
        det_frame = ttk.LabelFrame(
            container,
            text=_("Model and Detection"),
            padding=10,
        )
        det_frame.pack(fill="x", pady=6)
        self._detection_summary_frame = det_frame

        # Summary labels (updated via update_detection_summary)
        self._detection_labels: dict[str, ttk.Label] = {}
        params = [
            ("confidence", _("Minimum confidence:")),
            ("nms", _("NMS threshold:")),
            ("bytetrack", _("ByteTrack:")),
            ("track_thresh", _("Track threshold:")),
            ("match_thresh", _("Match threshold:")),
        ]
        for row, (key, text) in enumerate(params):
            ttk.Label(det_frame, text=text).grid(row=row, column=0, sticky="w", padx=(0, 6), pady=1)
            val_label = ttk.Label(det_frame, text="—", foreground="#555555")
            val_label.grid(row=row, column=1, sticky="w", pady=1)
            self._detection_labels[key] = val_label

        # Edit button
        ttk.Button(
            det_frame,
            text=_("⚙ Edit Calibration..."),
            command=self._on_open_calibration_clicked,
        ).grid(row=len(params), column=0, columnspan=2, sticky="w", pady=(8, 0))

        # Hint
        ttk.Label(
            det_frame,
            text=_("💡 Opens the Calibration and Detection dialog."),
            font=("TkDefaultFont", 8),
            foreground="#555555",
        ).grid(row=len(params) + 1, column=0, columnspan=2, sticky="w", pady=(2, 0))

    def set_detection_summary_visible(self, visible: bool) -> None:
        """Show the global-only detection summary section when appropriate."""
        if self._detection_summary_frame is None:
            return

        manager = self._detection_summary_frame.winfo_manager()
        if visible:
            if not manager:
                self._detection_summary_frame.pack(fill="x", pady=6)
            return

        if manager == "pack":
            self._detection_summary_frame.pack_forget()

    def update_detection_summary(self, settings_dict: dict[str, Any]) -> None:
        """Update the detection summary labels from a settings dictionary."""
        if not hasattr(self, "_detection_labels"):
            return
        yolo = settings_dict.get("yolo_model", {})
        bt = settings_dict.get("bytetrack", {})
        tracking = settings_dict.get("tracking", {})
        self._detection_labels["confidence"].configure(
            text=str(yolo.get("confidence_threshold", "—"))
        )
        self._detection_labels["nms"].configure(text=str(yolo.get("nms_threshold", "—")))
        use_bt = tracking.get("use_bytetrack", True)
        self._detection_labels["bytetrack"].configure(
            text=_("Enabled") if use_bt else _("Disabled")
        )
        self._detection_labels["track_thresh"].configure(text=str(bt.get("track_threshold", "—")))
        self._detection_labels["match_thresh"].configure(text=str(bt.get("match_threshold", "—")))

    def _on_open_calibration_clicked(self) -> None:
        """Emit event to open calibration dialog."""
        self.emit_event(UIEvents.CONFIG_OPEN_CALIBRATION_DIALOG, payloads.EmptyPayload())

    def _build_action_buttons(self, parent=None) -> None:
        """Build action buttons frame."""
        container = parent if parent else self
        actions_frame = ttk.Frame(container)
        actions_frame.pack(fill="x", pady=(12, 0))
        ttk.Button(
            actions_frame,
            text=_("Reload current values"),
            command=self._on_reset_clicked,
        ).pack(side="left")
        self.btn_save = ttk.Button(
            actions_frame,
            text=_("💾 Save Settings"),
            command=self._on_save_clicked,
            style="Accent.TButton",
        ).pack(side="right")

        # Validation info
        ttk.Label(
            container,
            text=_(
                "The advanced validations (offset < interval, polyorder < window, "
                "etc.) are applied automatically on save."
            ),
            wraplength=560,
            justify="left",
            font=("TkDefaultFont", 8),
        ).pack(fill="x", pady=(6, 0))

    def get_values(self) -> dict[str, Any]:
        """
        Get all form values as nested dict matching Settings structure.

        Returns:
            Dictionary with nested structure matching Settings model
        """
        return {
            "video_processing": {
                "fps": int(self.fps_var.get().strip()),
                "processing_interval": int(self.processing_interval_var.get().strip()),
                "display_interval": int(self.display_interval_var.get().strip()),
                "processing_offset": int(self.processing_offset_var.get().strip()),
            },
            "trajectory_smoothing": {
                "window_length": int(self.window_length_var.get().strip()),
                "polyorder": int(self.polyorder_var.get().strip()),
            },
            "recorder": {
                "flush_interval_seconds": float(self.flush_interval_var.get().strip()),
                "flush_row_threshold": int(self.flush_rows_var.get().strip()),
                "persist_masks": bool(self.persist_masks_var.get()),
            },
            "roi_inclusion_rule": self.roi_inclusion_rule_var.get(),
            "roi_buffer_radius_value": float(self.roi_buffer_radius_var.get().strip()),
            "roi_min_bbox_overlap_ratio": float(self.roi_overlap_ratio_var.get().strip()),
            "roi_bbox_overlap_basis": self.roi_overlap_basis_var.get(),
            "behavioral_analysis": self._get_behavioral_values(),
        }

    def _get_behavioral_values(self) -> dict[str, Any]:
        """Extract and map behavioral values."""
        if not self.behavioral_config_widget:
            return {}

        widget_values = self.behavioral_config_widget.get_values()
        return {
            "default_thigmotaxis_distance_cm": widget_values["thigmotaxis_distance_cm"],
            "default_geotaxis_distance_cm": widget_values["geotaxis_distance_cm"],
            "default_geotaxis_num_zones": widget_values["geotaxis_num_zones"],
            "default_geotaxis_bottom_zones": widget_values["geotaxis_bottom_zones"],
            "aquarium_perspective": widget_values["aquarium_perspective"],
            "geotaxis_mode": widget_values["geotaxis_mode"],
        }

    def set_values(self, values: dict[str, Any]) -> None:
        """
        Populate form from nested dict.

        Args:
            values: Nested dictionary matching Settings structure
        """
        self._set_video_processing(values.get("video_processing", {}))
        self._set_trajectory_smoothing(values.get("trajectory_smoothing", {}))
        self._set_recorder(values.get("recorder", {}))
        self._set_roi_settings(values)
        self._set_behavioral_analysis(values.get("behavioral_analysis", {}))
        self._refresh_seg_overlap_warning()
        self.update_detection_summary(values)

    def _set_video_processing(self, vp: dict[str, Any]) -> None:
        """Populate video processing settings."""
        if not vp:
            return
        if "fps" in vp:
            self.fps_var.set(str(vp["fps"]))
        if "processing_interval" in vp:
            self.processing_interval_var.set(str(vp["processing_interval"]))
        if "display_interval" in vp:
            self.display_interval_var.set(str(vp["display_interval"]))
        if "processing_offset" in vp:
            self.processing_offset_var.set(str(vp["processing_offset"]))

    def _set_trajectory_smoothing(self, ts: dict[str, Any]) -> None:
        """Populate trajectory smoothing settings."""
        if not ts:
            return
        if "window_length" in ts:
            self.window_length_var.set(str(ts["window_length"]))
        if "polyorder" in ts:
            self.polyorder_var.set(str(ts["polyorder"]))

    def _set_recorder(self, rec: dict[str, Any]) -> None:
        """Populate recorder settings."""
        if not rec:
            return
        if "flush_interval_seconds" in rec:
            self.flush_interval_var.set(str(rec["flush_interval_seconds"]))
        if "flush_row_threshold" in rec:
            self.flush_rows_var.set(str(rec["flush_row_threshold"]))
        if "persist_masks" in rec:
            self.persist_masks_var.set(bool(rec["persist_masks"]))

    def _set_roi_settings(self, values: dict[str, Any]) -> None:
        """Populate ROI settings."""
        if "roi_min_bbox_overlap_ratio" in values:
            self.roi_overlap_ratio_var.set(str(values["roi_min_bbox_overlap_ratio"]))

        if "roi_inclusion_rule" in values:
            self.roi_inclusion_rule_var.set(str(values["roi_inclusion_rule"]))

        if "roi_buffer_radius_value" in values:
            self.roi_buffer_radius_var.set(str(values["roi_buffer_radius_value"]))

        if "roi_bbox_overlap_basis" in values:
            self.roi_overlap_basis_var.set(str(values["roi_bbox_overlap_basis"]))

    def _set_behavioral_analysis(self, ba: dict[str, Any]) -> None:
        """Populate behavioral analysis settings."""
        if not ba or not self.behavioral_config_widget:
            return

        widget_values = {}
        # Map settings keys -> widget keys
        if "default_thigmotaxis_distance_cm" in ba:
            widget_values["thigmotaxis_distance_cm"] = ba["default_thigmotaxis_distance_cm"]
        if "default_geotaxis_distance_cm" in ba:
            widget_values["geotaxis_distance_cm"] = ba["default_geotaxis_distance_cm"]
        if "default_geotaxis_num_zones" in ba:
            widget_values["geotaxis_num_zones"] = ba["default_geotaxis_num_zones"]
        if "default_geotaxis_bottom_zones" in ba:
            widget_values["geotaxis_bottom_zones"] = ba["default_geotaxis_bottom_zones"]
        if "aquarium_perspective" in ba:
            widget_values["aquarium_perspective"] = ba["aquarium_perspective"]
        if "geotaxis_mode" in ba:
            widget_values["geotaxis_mode"] = ba["geotaxis_mode"]

        # We enable geotaxis in the editor so user can edit the values,
        # even if it's not "enabled" by default in a specific analysis.
        widget_values["geotaxis_enabled"] = True

        self.behavioral_config_widget.set_values(widget_values)

    def _on_save_clicked(self) -> None:
        """Handle save button click."""
        try:
            values = self.get_values()
            self.emit_event(
                UIEvents.CONFIG_SAVE_REQUESTED, payloads.ConfigSaveRequestedPayload(values=values)
            )
        except ValueError as e:
            self.emit_event(
                UIEvents.CONFIG_VALIDATION_ERROR,
                payloads.ConfigValidationErrorPayload(error=str(e)),
            )

    def _on_reset_clicked(self) -> None:
        """Handle reset button click."""
        self.emit_event(UIEvents.CONFIG_RESET_REQUESTED, payloads.EmptyPayload())

    def _refresh_seg_overlap_warning(self) -> None:
        """Show what is missing when 'seg_overlap' is selected without its prerequisites.

        Só cobre ``persist_masks`` — ``animal_method`` é editado noutro widget,
        então aqui ele é apenas NOMEADO, nunca inferido.

        O ``None`` do rótulo é defensivo (o trace da variável pode disparar
        antes de a seção de ROI existir, se a ordem de construção mudar); não é
        um estado alcançável hoje.
        """
        missing_masks = (
            self.roi_inclusion_rule_var.get() == "seg_overlap" and not self.persist_masks_var.get()
        )
        if self._seg_overlap_warning_label is not None:
            self._seg_overlap_warning_label.config(
                text=seg_overlap_missing_masks_warning() if missing_masks else ""
            )

    def _on_roi_rule_changed(self, event=None) -> None:
        """Handle ROI rule combobox change."""
        selected_rule = self.roi_inclusion_rule_var.get()
        self._refresh_seg_overlap_warning()
        self.emit_event(
            UIEvents.CONFIG_ROI_RULE_CHANGED,
            payloads.ConfigRoiRuleChangedPayload(rule=selected_rule),
        )
