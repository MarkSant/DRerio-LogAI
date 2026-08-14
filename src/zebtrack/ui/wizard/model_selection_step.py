"""Wizard step for selecting detection models, weights, and detector parameters."""

from __future__ import annotations

from tkinter import BooleanVar, Label, LabelFrame, StringVar, TclError, ttk
from tkinter import font as tkfont
from typing import TYPE_CHECKING

import structlog

from zebtrack.core.services.weight_manager import WeightManager
from zebtrack.i18n import _
from zebtrack.ui.wizard.base import WizardStep
from zebtrack.ui.wizard.enums import WizardStepID
from zebtrack.ui.wizard.templates import format_template_banner
from zebtrack.ui.wizard.tooltip import ToolTip
from zebtrack.utils.hardware_detection import get_openvino_devices, recommend_backend

if TYPE_CHECKING:
    from zebtrack.settings import Settings

log = structlog.get_logger()

# Defaults for ByteTrack - MUST match config.yaml values
DEFAULT_TRACK_THRESHOLD = 0.25
DEFAULT_MATCH_THRESHOLD = 0.95  # Higher = more permissive for fast-moving objects
DEFAULT_TRACK_BUFFER = 150  # Frames to keep lost tracks
DEFAULT_MAX_CENTER_DISTANCE = 200.0  # Pixels, ~6 body lengths for 30px zebrafish
DEFAULT_IOU_THRESHOLD = 0.1  # Low for small objects with little overlap


def _method_options() -> dict[str, str]:
    """Map a detector method key to the label shown in the combobox.

    A module-level dict would call _() at import time and freeze the language
    (see docs/guides/developer/i18n.md). It is also the single source for
    _method_key_from_label(), which maps the displayed label back to the key --
    the two must never be able to drift.
    """
    return {
        "seg": _("Segmentation (seg)"),
        "det": _("Detection (det)"),
    }


def _recommended_suffix() -> str:
    """Marker appended to the perspective-recommended weight in the dropdown.

    This string is BOTH displayed and parsed back off again: the combobox shows
    "<weight><suffix>", and _strip_annotation() removes it before the name is
    validated and stored. Translating the display without the parser would glue
    the marker onto the weight name, so validate() would reject a weight the
    user picked from the list. One definition, three call sites.
    """
    return _("  ⭐ Recommended")


class ModelSelectionStep(WizardStep):
    """Allow users to review or adjust model strategy, weight usage, and thresholds."""

    _responsive_labels: dict[str, list[Label]]

    def __init__(self, parent, wizard_data: dict, settings_obj: Settings | None = None):
        """Initialize the model selection wizard step.

        Args:
            parent: Parent widget.
            wizard_data: Shared wizard data dictionary.
            settings_obj: Settings object with configuration.
        """
        super().__init__(parent, wizard_data)
        self.step_id = WizardStepID.MODEL_SELECTION
        self.settings = settings_obj

        self.weight_manager = WeightManager(settings_obj=settings_obj)
        self.seg_weight_names: list[str] = []
        self.det_weight_names: list[str] = []

        # UI state variables
        self.aquarium_method_var = StringVar()
        self.aquarium_weight_var = StringVar()
        self.animal_method_var = StringVar()
        self.animal_weight_var = StringVar()
        self.use_openvino_var = BooleanVar(value=False)
        self.openvino_device_var = StringVar(value="AUTO")

        self.confidence_var = StringVar()
        self.nms_var = StringVar()

        # ByteTrack Params
        self.use_bytetrack_var = BooleanVar(value=True)
        self.track_var = StringVar()
        self.match_var = StringVar()
        self.track_buffer_var = StringVar()
        self.max_center_dist_var = StringVar()
        self.iou_thresh_var = StringVar()

        self.template_info_var = StringVar(value="")
        self.template_info_label: Label | None = None
        self.animal_method_hint_var = StringVar(value="")
        self._responsive_labels: dict[str, list[Label]] = {"left": [], "right": []}

        self._aquarium_weight_combo: ttk.Combobox | None = None
        self._animal_weight_combo: ttk.Combobox | None = None
        self._methods_frame: LabelFrame | None = None
        self._content_frame: ttk.Frame | None = None
        self._left_column: ttk.Frame | None = None
        self._right_column: ttk.Frame | None = None
        self._bytetrack_frame: LabelFrame | None = None
        self._resize_after_id: str | None = None  # Debouncing for resize events

        # Validation tracking: Entry widgets and error labels
        self._threshold_entries: dict[str, ttk.Entry] = {}
        self._threshold_error_labels: dict[str, Label] = {}

        self._load_weight_catalog()
        self._prefill_from_wizard_data()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _get_active_perspective(self) -> str | None:
        """Read the camera perspective from upstream wizard data.

        The calibration step's ``get_data()`` returns ``behavioral_analysis``
        at the top level, and the wizard merges step data into ``wizard_data``
        with ``dict.update`` (see ``WizardDialog._on_next``). So the canonical
        location is ``wizard_data["behavioral_analysis"]["aquarium_perspective"]``.

        We also accept the nested ``wizard_data["calibration"]
        ["behavioral_analysis"]`` form as a fallback because templates/imports
        sometimes shovel a project-data-shaped dict in via ``set_data``.

        Returns:
            ``"lateral"`` or ``"top_down"``, or *None* if not set.
        """
        ba = self.wizard_data.get("behavioral_analysis") or {}
        raw = ba.get("aquarium_perspective")
        if raw is None:
            # Fallback: project-data-style nested layout
            calibration = self.wizard_data.get("calibration") or {}
            ba_nested = calibration.get("behavioral_analysis") or {}
            raw = ba_nested.get("aquarium_perspective")

        if raw in ("lateral", "top_down"):
            return raw
        # Handle enum-style values (e.g. AquariumPerspective.LATERAL)
        if raw is not None:
            raw_str = str(raw).lower()
            if "lateral" in raw_str:
                return "lateral"
            if "top" in raw_str:
                return "top_down"
        return None

    def _load_weight_catalog(self) -> None:
        """Populate cached segmentation/detection weight name lists."""
        self.seg_weight_names.clear()
        self.det_weight_names.clear()

        for name in self.weight_manager.get_all_weights():
            details = self.weight_manager.get_weight_details(name) or {}
            weight_type = details.get("type")
            if weight_type == "seg":
                self.seg_weight_names.append(name)
            elif weight_type == "det":
                self.det_weight_names.append(name)

        self.seg_weight_names.sort()
        self.det_weight_names.sort()

        log.info(
            "wizard.model_step.weights_loaded",
            seg=len(self.seg_weight_names),
            det=len(self.det_weight_names),
        )

    def _method_display(self, method_key: str | None) -> str:
        """Format method labels for display."""
        options = _method_options()
        if method_key in options:
            return options[method_key]
        if method_key:
            return method_key
        return options["seg"]

    def _recommended_use_bytetrack(self, animal_method: str) -> bool:
        """Return recommended ByteTrack default for current wizard context."""
        default_use_bytetrack = True
        if self.settings and hasattr(self.settings, "tracking"):
            default_use_bytetrack = bool(self.settings.tracking.use_bytetrack)

        animals_per_aquarium = int(self.wizard_data.get("animals_per_aquarium", 1) or 1)
        method_key = self._method_key_from_label(animal_method)

        # Performance-oriented default for simple scenario:
        # single animal + detection (det) in one aquarium context.
        if animals_per_aquarium == 1 and method_key == "det":
            return False

        return default_use_bytetrack

    def _prefill_from_wizard_data(self) -> None:
        """Initialise state variables from wizard data or global defaults."""
        selection = dict(self.wizard_data.get("model_selection", {}) or {})
        weight_assignments = dict(self.wizard_data.get("weight_assignments", {}) or {})

        # Get defaults from settings or use hardcoded defaults
        if self.settings and hasattr(self.settings, "model_selection"):
            aquarium_method_default = self.settings.model_selection.aquarium_method
            animal_method_default = self.settings.model_selection.animal_method
        else:
            aquarium_method_default = "seg"
            animal_method_default = "seg"

        aquarium_method = selection.get("aquarium_method", aquarium_method_default)
        animal_method = selection.get("animal_method", animal_method_default)
        use_openvino = selection.get("use_openvino")
        if (
            use_openvino is None
            and self.settings
            and hasattr(self.settings, "model_selection")
            and self.settings.model_selection.use_openvino
        ):
            # Herdar a configuração global persistida antes do auto-detect,
            # para que projetos novos nasçam coerentes com o padrão global.
            use_openvino = True
            log.info(
                "wizard.model_selection.openvino_from_global_settings",
                use_openvino=True,
            )
        if use_openvino is None:
            # Auto-detect hardware and recommend backend if not explicitly set
            recommended = recommend_backend()
            use_openvino = recommended == "openvino"
            log.info(
                "wizard.model_selection.hardware_auto_detect",
                recommended_backend=recommended,
                use_openvino=use_openvino,
            )

        self.aquarium_method_var.set(self._method_display(aquarium_method))
        self.animal_method_var.set(self._method_display(animal_method))
        self.use_openvino_var.set(bool(use_openvino))

        openvino_device = selection.get("openvino_device")
        if not openvino_device and self.settings and hasattr(self.settings, "openvino"):
            openvino_device = self.settings.openvino.device
        self.openvino_device_var.set(self._normalize_openvino_device(openvino_device))

        aquarium_weight = weight_assignments.get("aquarium")
        animal_weight = weight_assignments.get("animal")

        if aquarium_weight:
            self.aquarium_weight_var.set(aquarium_weight)
        else:
            self.aquarium_weight_var.set(self._default_weight_for_method(aquarium_method))

        if animal_weight:
            self.animal_weight_var.set(animal_weight)
        else:
            self.animal_weight_var.set(self._default_weight_for_method(animal_method))

        detector_params = dict(self.wizard_data.get("detector_parameters", {}) or {})

        # Get default thresholds from settings or use hardcoded defaults
        default_confidence = 0.25
        default_nms = 0.45
        default_use_bytetrack = self._recommended_use_bytetrack(animal_method)

        if self.settings and hasattr(self.settings, "yolo_model"):
            default_confidence = self.settings.yolo_model.confidence_threshold
            default_nms = self.settings.yolo_model.nms_threshold

        confidence_threshold = float(
            detector_params.get("confidence_threshold", default_confidence)
        )
        self.confidence_var.set(f"{confidence_threshold:.3f}")

        nms_threshold = float(detector_params.get("nms_threshold", default_nms))
        self.nms_var.set(f"{nms_threshold:.3f}")

        # ByteTrack params
        self.use_bytetrack_var.set(
            bool(detector_params.get("use_bytetrack", default_use_bytetrack))
        )

        track_threshold = float(detector_params.get("track_threshold", DEFAULT_TRACK_THRESHOLD))
        self.track_var.set(f"{track_threshold:.3f}")

        match_threshold = float(detector_params.get("match_threshold", DEFAULT_MATCH_THRESHOLD))
        self.match_var.set(f"{match_threshold:.3f}")

        track_buffer = int(detector_params.get("track_buffer", DEFAULT_TRACK_BUFFER))
        self.track_buffer_var.set(str(track_buffer))

        max_center_dist = float(
            detector_params.get("max_center_distance", DEFAULT_MAX_CENTER_DISTANCE)
        )
        self.max_center_dist_var.set(f"{max_center_dist:.1f}")

        iou_threshold = float(detector_params.get("iou_threshold", DEFAULT_IOU_THRESHOLD))
        self.iou_thresh_var.set(f"{iou_threshold:.3f}")

    def _default_weight_for_method(self, method_key: str) -> str:
        perspective = self._get_active_perspective()
        if perspective:
            name, _details = self.weight_manager.get_weight_by_perspective_and_type(
                perspective,
                method_key,
            )
            if name:
                return name
        if method_key == "seg":
            name, _details = self.weight_manager.get_default_seg_weight()
            return name or (self.seg_weight_names[0] if self.seg_weight_names else "")
        if method_key == "det":
            name, _details = self.weight_manager.get_default_det_weight()
            return name or (self.det_weight_names[0] if self.det_weight_names else "")
        return ""

    def _available_openvino_devices(self) -> list[str]:
        """Return UI options for OpenVINO target device."""
        options = ["AUTO"]
        try:
            devices = tuple(get_openvino_devices())
        except Exception:  # pragma: no cover - defensive fallback
            devices = ()

        for candidate in ("CPU", "GPU", "NPU"):
            if any(candidate in device for device in devices):
                options.append(candidate)

        return options

    def _normalize_openvino_device(self, device: str | None) -> str:
        """Normalize arbitrary device value into a supported combo option."""
        normalized = (device or "AUTO").strip().upper()
        options = self._available_openvino_devices()
        if normalized in options:
            return normalized
        return "AUTO"

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def build_ui(self) -> None:
        """Build the UI for this step with model selection controls."""
        title_font = tkfont.Font(size=14, weight="bold")
        title = Label(self, text=_("Models and Weights"), font=title_font)
        title.pack(pady=(0, 10))

        subtitle = Label(
            self,
            text=_(
                "Adjust how ZebTrack will use each detection model.\n"
                "If you prefer, keep the recommended defaults and move on."
            ),
            fg="gray",
            wraplength=560,
            justify="left",
        )
        subtitle.pack(pady=(0, 15))
        self._responsive_labels["left"].append(subtitle)

        # Use Frame with grid for responsive layout (not PanedWindow to avoid conflicts)
        content_frame = ttk.Frame(self)
        content_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self._content_frame = content_frame

        # Configure grid columns
        content_frame.columnconfigure(0, weight=3, minsize=420)
        content_frame.columnconfigure(1, weight=2, minsize=300)
        content_frame.rowconfigure(0, weight=1)

        # Left column: Methods and Weights
        left_column = ttk.Frame(content_frame)
        left_column.columnconfigure(0, weight=1)
        self._left_column = left_column
        left_column.grid(row=0, column=0, sticky="nsew", padx=(0, 15))

        # Right column: Quick Guide
        right_column = ttk.Frame(content_frame)
        right_column.columnconfigure(0, weight=1)
        self._right_column = right_column
        right_column.grid(row=0, column=1, sticky="nsew")

        self.template_info_label = Label(
            left_column,
            textvariable=self.template_info_var,
            fg="#555555",
            wraplength=560,
            justify="left",
        )
        self.template_info_label.pack_forget()
        self._responsive_labels["left"].append(self.template_info_label)

        methods_frame = LabelFrame(
            left_column,
            text=_("Methods and Weights per Role"),
            padx=10,
            pady=5,
        )
        methods_frame.pack(fill="x", pady=(0, 8))
        self._methods_frame = methods_frame

        self._build_method_row(
            parent=methods_frame,
            row=0,
            title=_("Aquarium (arena detection)"),
            method_var=self.aquarium_method_var,
            weight_var=self.aquarium_weight_var,
            combo_attr="_aquarium_weight_combo",
        )

        self._build_method_row(
            parent=methods_frame,
            row=1,
            title=_("Animals (tracking)"),
            method_var=self.animal_method_var,
            weight_var=self.animal_weight_var,
            combo_attr="_animal_weight_combo",
        )

        animal_hint = Label(
            methods_frame,
            textvariable=self.animal_method_hint_var,
            fg="#bb6600",
            wraplength=520,
            justify="left",
        )
        animal_hint.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self._responsive_labels["left"].append(animal_hint)

        acceleration_frame = LabelFrame(
            left_column,
            text=_("Acceleration / OpenVINO"),
            padx=10,
            pady=5,
        )
        acceleration_frame.pack(fill="x", pady=(0, 8))

        openvino_check = ttk.Checkbutton(
            acceleration_frame,
            text=_("Use OpenVINO (requires converting the weight)"),
            variable=self.use_openvino_var,
        )
        openvino_check.pack(anchor="w")
        ToolTip(
            openvino_check,
            _(
                "Enable this once the matching OpenVINO model has been converted."
                " It allows faster inference on compatible CPUs."
            ),
        )

        device_row = ttk.Frame(acceleration_frame)
        device_row.pack(fill="x", pady=(6, 0))
        ttk.Label(device_row, text=_("OpenVINO device:")).pack(side="left")

        device_combo = ttk.Combobox(
            device_row,
            textvariable=self.openvino_device_var,
            values=self._available_openvino_devices(),
            state="readonly",
            width=10,
        )
        device_combo.pack(side="left", padx=(8, 0))
        ToolTip(
            device_combo,
            _(
                "AUTO lets OpenVINO choose the target automatically.\n"
                "Pick CPU/GPU/NPU to force the target, when available."
            ),
        )

        detector_frame = LabelFrame(
            left_column,
            text=_("Detection Parameters (YOLO)"),
            padx=10,
            pady=5,
        )
        detector_frame.pack(fill="x", pady=(0, 8))

        self._build_detector_param_row(
            detector_frame,
            label=_("Minimum confidence (0-1):"),
            var=self.confidence_var,
            column=0,
            tooltip=_(
                "🎯 Minimum Confidence (Confidence Threshold)\n\n"
                "Filters out detections the model is unsure about.\n\n"
                "• HIGH value (0.5-0.9): fewer detections, more precise\n"
                "  → Use when: large animals, clear contrast\n"
                "  → Downside: may lose fast-moving animals\n\n"
                "• LOW value (0.1-0.4): more detections, less precise\n"
                "  → Use when: small animals, low contrast\n"
                "  → Downside: more false positives (noise)\n\n"
                "💡 Recommended default: 0.25"
            ),
            param_key="confidence",
        )
        self._build_detector_param_row(
            detector_frame,
            label=_("NMS (overlap, 0-1):"),
            var=self.nms_var,
            column=1,
            tooltip=_(
                "🔲 NMS - Non-Maximum Suppression\n\n"
                "Removes duplicate boxes on the same object.\n\n"
                "• HIGH value (0.6-0.9): allows more overlap\n"
                "  → Use when: animals are very close together\n"
                "  → Downside: several detections on the same animal\n\n"
                "• LOW value (0.1-0.4): removes overlaps aggressively\n"
                "  → Use when: animals are well separated\n"
                "  → Downside: may merge nearby animals\n\n"
                "💡 Recommended default: 0.45"
            ),
            param_key="nms",
        )

        # ByteTrack Section - positioned in right column to use the guide space
        self._bytetrack_frame = LabelFrame(
            right_column,
            text=_("Tracking Parameters (ByteTrack)"),
            padx=10,
            pady=8,
        )
        self._bytetrack_frame.pack(fill="both", expand=True)
        assert self._bytetrack_frame is not None

        # Configure grid for better distribution in larger space
        self._bytetrack_frame.columnconfigure(0, weight=1)
        self._bytetrack_frame.columnconfigure(1, weight=1)

        bytetrack_check = ttk.Checkbutton(
            self._bytetrack_frame,
            text=_("Use ByteTrack (Recommended)"),
            variable=self.use_bytetrack_var,
            command=self._toggle_bytetrack_options,
        )
        bytetrack_check.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))
        ToolTip(
            bytetrack_check,
            _(
                "Enables the ByteTrack algorithm for robust tracking with a Kalman filter.\n"
                "Recommended for most experiments."
            ),
        )

        self.bytetrack_hint_var = StringVar()
        self.bytetrack_hint_label = Label(
            self._bytetrack_frame,
            textvariable=self.bytetrack_hint_var,
            fg="#555555",
            font=("TkDefaultFont", 8, "italic"),
            justify="left",
            wraplength=280,
        )
        self.bytetrack_hint_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 8))

        self._build_detector_param_row(
            self._bytetrack_frame,
            label=_("Track Threshold (0-1):"),
            var=self.track_var,
            column=0,
            row=2,
            tooltip=_(
                "🛤️ Track Threshold\n\n"
                "Minimum confidence to START or KEEP a trajectory.\n"
                "Low values help keep the trail of animals that are hard to detect.\n\n"
                "💡 Default: 0.25"
            ),
            param_key="track",
        )
        self._build_detector_param_row(
            self._bytetrack_frame,
            label=_("Match Threshold (0-1):"),
            var=self.match_var,
            column=1,
            row=2,
            tooltip=_(
                "🔗 Match Threshold\n\n"
                "Tolerance when associating boxes.\n"
                "HIGH values (close to 1.0) are more permissive for fast movement.\n\n"
                "💡 Default: 0.95 (for fast zebrafish)"
            ),
            param_key="match",
        )

        self._build_detector_param_row(
            self._bytetrack_frame,
            label=_("Track Buffer (frames):"),
            var=self.track_buffer_var,
            column=0,
            row=3,
            tooltip=_(
                "🧠 Track Buffer\n\n"
                "The tracker's memory: how many frames an animal may 'vanish' for "
                "before its ID is forgotten.\n\n"
                "💡 Default: 90 frames (~3 seconds at 30fps)"
            ),
            param_key="track_buffer",
        )
        self._build_detector_param_row(
            self._bytetrack_frame,
            label=_("Max distance (px):"),
            var=self.max_center_dist_var,
            column=1,
            row=3,
            tooltip=_(
                "📏 Maximum Centre Distance\n\n"
                "The furthest (in pixels) an animal may move between frames and still "
                "be considered the same one, when overlap fails.\n\n"
                "💡 Default: 200.0 px"
            ),
            param_key="max_center_dist",
        )

        self._build_detector_param_row(
            self._bytetrack_frame,
            label=_("IoU Threshold (0-1):"),
            var=self.iou_thresh_var,
            column=0,
            row=4,
            tooltip=_(
                "🔳 IoU Threshold\n\n"
                "Minimum overlap to prefer a box match over a distance match.\n"
                "For small, fast fish, low values work better.\n\n"
                "💡 Default: 0.1"
            ),
            param_key="iou_thresh",
        )

        # Quick guide tips integrated into ByteTrack frame
        guide_separator = ttk.Separator(self._bytetrack_frame, orient="horizontal")
        guide_separator.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(12, 8))

        guide_text = _(
            "📊 Quick Guide:\n"
            "• Track Thresh: ↓ to keep a weak trail\n"
            "• Match Thresh: ↑ to accept abrupt movements\n"
            "• Buffer: ↑ to 'remember' the fish for longer\n"
            "• Distance: ↑ for very fast fish"
        )

        guide_label = Label(
            self._bytetrack_frame,
            text=guide_text,
            fg="#333333",
            justify="left",
            font=("TkDefaultFont", 8),
            anchor="nw",
        )
        guide_label.grid(row=6, column=0, columnspan=2, sticky="w", pady=(0, 5))

        # Footer Tip
        tip_label = Label(
            self._bytetrack_frame,
            text=_("💡 Tip: adjust ONE parameter at a time (±0.05) and test!"),
            fg="#006600",
            font=("TkDefaultFont", 9, "bold"),
        )
        tip_label.grid(row=7, column=0, columnspan=2, pady=(5, 0), sticky="w")

        # Get current defaults for display
        display_confidence = 0.25
        display_nms = 0.45
        if self.settings and hasattr(self.settings, "yolo_model"):
            display_confidence = self.settings.yolo_model.confidence_threshold
            display_nms = self.settings.yolo_model.nms_threshold

        defaults_label = Label(
            left_column,
            text=_("Current YOLO defaults: confidence {confidence}, NMS {nms}.").format(
                confidence=f"{display_confidence:.2f}",
                nms=f"{display_nms:.2f}",
            ),
            fg="#555555",
            wraplength=560,
            justify="left",
        )
        defaults_label.pack(fill="x", padx=10, pady=(3, 0))
        self._responsive_labels["left"].append(defaults_label)

        # Restore defaults button
        from tkinter import Button

        restore_btn = Button(
            left_column,
            text=_("🔄 Restore Recommended Defaults"),
            command=self._restore_default_thresholds,
            bg="#E3F2FD",
            fg="#1565C0",
            font=("TkDefaultFont", 9, "bold"),
            relief="raised",
            cursor="hand2",
        )
        restore_btn.pack(fill="x", padx=10, pady=(5, 0))
        ToolTip(
            restore_btn,
            _(
                "Restores every threshold to its recommended default value.\n\n"
                "Useful if you have made adjustments and want to start over."
            ),
        )

        footer = Label(
            left_column,
            text=_(
                "Tip: keep the defaults if you are still setting up the videos."
                " You can review these values later in the project settings."
            ),
            fg="#555555",
            wraplength=560,
            justify="left",
        )
        footer.pack(fill="x", pady=(3, 0), padx=10)
        self._responsive_labels["left"].append(footer)

        self.aquarium_method_var.trace_add("write", self._on_aquarium_method_change)
        self.animal_method_var.trace_add("write", self._on_animal_method_change)

        self._update_template_banner()
        self._refresh_weight_dropdowns()
        self._update_animal_method_hint()

        # Setup validation callbacks after UI is built
        self._setup_validation_callbacks()
        self._toggle_bytetrack_options()  # Init state

        self.bind("<Configure>", self._on_resize)
        # Trigger an initial layout recalculation once geometry settles.
        self.after(0, self._refresh_layout_mode)

    def _toggle_bytetrack_options(self) -> None:
        """Enable/Disable ByteTrack parameter inputs based on checkbox."""
        if not self._bytetrack_frame:
            return

        enabled = self.use_bytetrack_var.get()
        state = "normal" if enabled else "disabled"

        # Iterate over entry widgets related to tracking
        for key in ["track", "match", "track_buffer", "max_center_dist", "iou_thresh"]:
            entry = self._threshold_entries.get(key)
            if entry:
                entry.configure(state=state)

        if not enabled:
            self.bytetrack_hint_var.set(
                _(
                    "ℹ️ ByteTrack disabled. The system will use a simplified hybrid "
                    "tracker that relies only on '{distance}' and '{iou}' to keep the ID "
                    "stable. Ideal for 1 animal per aquarium."
                ).format(
                    distance=_("Max distance (px):").rstrip(":"),
                    iou=_("IoU Threshold (0-1):").rstrip(":"),
                )
            )
            # Re-enable distance and iou for the simple tracker
            for key in ["max_center_dist", "iou_thresh"]:
                entry = self._threshold_entries.get(key)
                if entry:
                    entry.configure(state="normal")
        else:
            self.bytetrack_hint_var.set(
                _(
                    "💡 ByteTrack uses a Kalman filter to predict positions even when the "
                    "fish briefly disappears. Adjust the fields below for more stability."
                )
            )

    def _build_method_row(
        self,
        parent,
        row: int,
        title: str,
        method_var: StringVar,
        weight_var: StringVar,
        combo_attr: str,
    ) -> None:
        Label(parent, text=title, anchor="w").grid(row=row, column=0, sticky="w")

        method_combo = ttk.Combobox(
            parent,
            textvariable=method_var,
            values=list(_method_options().values()),
            state="readonly",
            width=24,
        )
        method_combo.grid(row=row, column=1, padx=(10, 10), pady=5, sticky="w")
        ToolTip(
            method_combo,
            _(
                "Segmentation supports several animals per aquarium.\n"
                "Detection is optimized for one animal per aquarium and uses ByteTrack."
            ),
        )

        weight_combo = ttk.Combobox(
            parent,
            textvariable=weight_var,
            values=[],
            state="readonly",
            width=28,
        )
        weight_combo.grid(row=row, column=2, pady=5, sticky="w")
        ToolTip(
            weight_combo,
            _("Select the weight file loaded for this role."),
        )
        setattr(self, combo_attr, weight_combo)

    def _build_detector_param_row(
        self,
        parent,
        label: str,
        var: StringVar,
        column: int,
        row: int = 0,
        tooltip: str = "",
        param_key: str = "",
    ) -> None:
        # Create a container frame for label + entry + error message
        container = ttk.Frame(parent)
        container.grid(row=row, column=column, padx=(0, 12), pady=5, sticky="w")

        # Horizontal frame for label and entry
        input_frame = ttk.Frame(container)
        input_frame.pack(fill="x")

        Label(input_frame, text=label).pack(side="left")
        entry = ttk.Entry(input_frame, textvariable=var, width=8)
        entry.pack(side="left", padx=(5, 0))
        if tooltip:
            ToolTip(entry, tooltip)

        # Store entry reference for validation highlighting
        if param_key:
            self._threshold_entries[param_key] = entry

            # Create error label (initially hidden)
            error_label = Label(
                container,
                text="",
                fg="red",
                font=("TkDefaultFont", 8),
                justify="left",
            )
            error_label.pack(fill="x", pady=(2, 0))
            self._threshold_error_labels[param_key] = error_label

    # ------------------------------------------------------------------
    # Validation and error highlighting
    # ------------------------------------------------------------------
    def _setup_validation_callbacks(self) -> None:
        """Set up real-time validation callbacks for threshold parameters."""
        # Add trace callbacks to validate on value change
        self.confidence_var.trace_add(
            "write", lambda *_: self._validate_threshold_field("confidence")
        )
        self.nms_var.trace_add("write", lambda *_: self._validate_threshold_field("nms"))
        self.track_var.trace_add("write", lambda *_: self._validate_threshold_field("track"))
        self.match_var.trace_add("write", lambda *_: self._validate_threshold_field("match"))

    def _validate_threshold_field(self, param_key: str) -> bool:
        """
        Validate a single threshold field and update visual feedback.

        Args:
            param_key: The threshold parameter key ("confidence", "nms", "track", "match")

        Returns:
            bool: True if valid, False otherwise
        """
        # Get the StringVar and Entry widget
        # One finished sentence per field instead of splicing a noun into a
        # template: capitalising a translated word (the old .capitalize() call)
        # is not safe across languages, and the Portuguese needs its own wording.
        var_map = {
            "confidence": (self.confidence_var, _("❌ Confidence must be between 0 and 1")),
            "nms": (self.nms_var, _("❌ NMS must be between 0 and 1")),
            "track": (self.track_var, _("❌ Track must be between 0 and 1")),
            "match": (self.match_var, _("❌ Match must be between 0 and 1")),
        }

        if param_key not in var_map:
            return True

        var, range_error = var_map[param_key]
        entry = self._threshold_entries.get(param_key)
        error_label = self._threshold_error_labels.get(param_key)

        if not entry or not error_label:
            return True

        # Get current value
        value_str = var.get().strip()

        # Empty is allowed (will be caught by main validation)
        if not value_str:
            self._clear_threshold_error(param_key)
            return True

        # Try to parse as float
        try:
            value = float(value_str)
        except ValueError:
            # Invalid number format - highlight with light red background
            try:
                entry.configure(background="#FFE0E0")  # Light red
            except TclError:
                log.debug("model_selection.entry_highlight.error", exc_info=True)
            error_label.configure(text=_("❌ Value must be a decimal (e.g. 0.25)"))
            return False

        # Check range (0, 1) exclusive
        if not 0.0 < value < 1.0:
            try:
                entry.configure(background="#FFE0E0")  # Light red
            except TclError:
                log.debug("model_selection.entry_highlight_range.error", exc_info=True)
            error_label.configure(text=range_error)
            return False

        # Valid - clear error
        self._clear_threshold_error(param_key)
        return True

    def _clear_threshold_error(self, param_key: str) -> None:
        """Clear error highlighting for a specific threshold field."""
        entry = self._threshold_entries.get(param_key)
        error_label = self._threshold_error_labels.get(param_key)

        if entry:
            try:
                entry.configure(background="white")  # Reset to default
            except TclError:
                log.debug("model_selection.entry_reset.error", exc_info=True)
        if error_label:
            error_label.configure(text="")

    def _clear_all_threshold_errors(self) -> None:
        """Clear all threshold error highlights."""
        for param_key in ["confidence", "nms", "track", "match"]:
            self._clear_threshold_error(param_key)

    # ------------------------------------------------------------------
    # Event handlers and derived state
    # ------------------------------------------------------------------
    def _on_aquarium_method_change(self, *_):
        self._refresh_weight_dropdowns(role="aquarium")

    def _on_animal_method_change(self, *_):
        self._refresh_weight_dropdowns(role="animal")
        self._update_animal_method_hint()

    def _refresh_weight_dropdowns(self, role: str | None = None) -> None:
        roles = [role] if role else ["aquarium", "animal"]
        perspective = self._get_active_perspective()

        for current in roles:
            if current == "aquarium":
                combo = self._aquarium_weight_combo
                method_var = self.aquarium_method_var
                weight_var = self.aquarium_weight_var
            else:
                combo = self._animal_weight_combo
                method_var = self.animal_method_var
                weight_var = self.animal_weight_var

            if combo is None:
                continue

            method_key = self._method_key_from_label(method_var.get())
            if method_key == "seg":
                raw_options = list(self.seg_weight_names)
            else:
                raw_options = list(self.det_weight_names)

            # Annotate perspective-recommended weights
            recommended_name: str | None = None
            if perspective:
                rec, _details = self.weight_manager.get_weight_by_perspective_and_type(
                    perspective,
                    method_key,
                )
                recommended_name = rec

            display_options: list[str] = []
            for opt in raw_options:
                if opt == recommended_name:
                    display_options.insert(0, f"{opt}{_recommended_suffix()}")
                else:
                    display_options.append(opt)

            combo.configure(values=display_options)

            if display_options:
                current_weight = weight_var.get()
                # Check if current value is still valid (strip annotation)
                valid = any(
                    current_weight == opt or opt == current_weight + _recommended_suffix()
                    for opt in display_options
                )
                if not valid:
                    # Auto-select the recommended weight (first in list)
                    weight_var.set(display_options[0])
                combo.configure(state="readonly")
            else:
                weight_var.set("")
                combo.configure(state="disabled")

    def _method_key_from_label(self, label_value: str) -> str:
        for key, label in _method_options().items():
            if label_value == label or label_value == key:
                return key
        return label_value or "seg"

    def _update_animal_method_hint(self) -> None:
        method_key = self._method_key_from_label(self.animal_method_var.get())
        animals_per_aquarium = int(self.wizard_data.get("animals_per_aquarium", 1) or 1)

        if method_key == "det" and animals_per_aquarium > 1:
            self.animal_method_hint_var.set(
                _(
                    "⚠️ Detection (det) is recommended for only 1 animal per aquarium."
                    " Consider segmentation (seg) for several animals."
                )
            )
        else:
            self.animal_method_hint_var.set("")

    def _on_resize(self, event) -> None:
        """Adjust wraplengths to keep text readable when the dialog resizes.

        Uses debouncing to avoid excessive reconfigurations that cause flickering.
        """
        if event.widget is not self:
            return

        # Cancel any pending resize update to avoid flickering
        if self._resize_after_id is not None:
            try:
                self.after_cancel(self._resize_after_id)
            except TclError:
                log.debug("model_selection.cancel_resize.error", exc_info=True)
            self._resize_after_id = None

        # Schedule actual resize update after a short delay (debouncing)
        self._resize_after_id = self.after(100, self._apply_resize, event.width)

    def _apply_resize(self, width: int) -> None:
        """Apply resize changes after debouncing period."""
        self._resize_after_id = None

        total_width = max(width, 600)

        # Calculate wraplengths for labels based on column widths
        # Left column is ~60% (weight=3), right is ~40% (weight=2)
        left_width = max(360, int(total_width * 0.6))
        right_width = max(240, total_width - left_width - 80)

        for label in self._responsive_labels.get("left", []):
            if label and label.winfo_exists():
                label.configure(wraplength=max(320, left_width - 40))

        for label in self._responsive_labels.get("right", []):
            if label and label.winfo_exists():
                label.configure(wraplength=max(220, right_width - 40))

    def _refresh_layout_mode(self) -> None:
        """Force a layout recalculation using the current widget width."""
        try:
            width = self.winfo_width()
            if width > 1:  # Valid width
                self._apply_resize(width)
        except TclError:
            return

    # ------------------------------------------------------------------
    # Wizard lifecycle overrides
    # ------------------------------------------------------------------
    def on_show(self) -> None:
        """Handle step visibility and refresh UI from shared wizard data."""
        # Refresh UI from shared wizard data so templates/back navigation stay in sync
        self._prefill_from_wizard_data()
        self._update_template_banner()
        self._refresh_weight_dropdowns()
        self._update_animal_method_hint()

    def set_data(self, data: dict):
        """Set wizard data for this step.

        Args:
            data: Dictionary with wizard configuration data.
        """
        if not data:
            return
        model_selection = self.wizard_data.setdefault("model_selection", {})
        model_selection.update(data.get("model_selection", {}))
        if "aquarium_method" in data:
            model_selection["aquarium_method"] = data["aquarium_method"]
        if "animal_method" in data:
            model_selection["animal_method"] = data["animal_method"]
        if "use_openvino" in data:
            model_selection["use_openvino"] = data["use_openvino"]
        if "openvino_device" in data:
            model_selection["openvino_device"] = data["openvino_device"]
        if "weight_assignments" in data:
            self.wizard_data["weight_assignments"] = data.get("weight_assignments")
        if "detector_parameters" in data:
            self.wizard_data["detector_parameters"] = data.get("detector_parameters")
        self._prefill_from_wizard_data()
        self._refresh_weight_dropdowns()
        self._update_animal_method_hint()

    def _update_template_banner(self) -> None:
        metadata = self.wizard_data.get("template_metadata")
        banner = format_template_banner(metadata)
        if banner:
            self.template_info_var.set(banner)
            label = self.template_info_label
            if label and not label.winfo_ismapped():
                target = self._methods_frame
                if target is not None:
                    label.pack(before=target)
                else:
                    label.pack()
        else:
            label = self.template_info_label
            if label and label.winfo_ismapped():
                label.pack_forget()

    # ------------------------------------------------------------------
    # Threshold management
    # ------------------------------------------------------------------
    def _restore_default_thresholds(self) -> None:
        """Restore all detector thresholds to recommended default values."""
        # Clear any validation errors first
        self._clear_all_threshold_errors()

        # Get default values from settings or use hardcoded defaults
        default_confidence = 0.25
        default_nms = 0.45
        if self.settings and hasattr(self.settings, "yolo_model"):
            default_confidence = self.settings.yolo_model.confidence_threshold
            default_nms = self.settings.yolo_model.nms_threshold

        # Set default values
        self.confidence_var.set(f"{default_confidence:.3f}")
        self.nms_var.set(f"{default_nms:.3f}")
        self.use_bytetrack_var.set(self._recommended_use_bytetrack(self.animal_method_var.get()))
        self.track_var.set(f"{DEFAULT_TRACK_THRESHOLD:.3f}")
        self.match_var.set(f"{DEFAULT_MATCH_THRESHOLD:.3f}")

        log.info(
            "wizard.model_selection.thresholds_restored",
            confidence=default_confidence,
            nms=default_nms,
            track=DEFAULT_TRACK_THRESHOLD,
            match=DEFAULT_MATCH_THRESHOLD,
        )

    # ------------------------------------------------------------------
    # Validation and data extraction
    # ------------------------------------------------------------------
    @staticmethod
    def _strip_annotation(value: str) -> str:
        """Remove the recommended-weight suffix from a weight name."""
        marker = _recommended_suffix()
        if value.endswith(marker):
            return value[: -len(marker)]
        return value

    def validate(self) -> tuple[bool, str]:
        """Validate model selection and detector parameters.

        Returns:
            Tuple of (is_valid, error_message). If valid, error_message is empty.
        """
        try:
            confidence = float(self.confidence_var.get())
            nms = float(self.nms_var.get())
            track = float(self.track_var.get())
            match = float(self.match_var.get())
        except ValueError:
            return False, _("Enter decimal values between 0 and 1 for the parameters.")

        for message, value in (
            (_("The confidence parameter must be between 0 and 1."), confidence),
            (_("The NMS parameter must be between 0 and 1."), nms),
            (_("The track parameter must be between 0 and 1."), track),
            (_("The match parameter must be between 0 and 1."), match),
        ):
            if not 0.0 < value < 1.0:
                return False, message

        for role_message, method_var, weight_var in (
            (
                _("Select a valid weight for the aquarium. The file must match the chosen method."),
                self.aquarium_method_var,
                self.aquarium_weight_var,
            ),
            (
                _("Select a valid weight for the animals. The file must match the chosen method."),
                self.animal_method_var,
                self.animal_weight_var,
            ),
        ):
            method_key = self._method_key_from_label(method_var.get())
            if method_key == "seg":
                options = self.seg_weight_names
            else:
                options = self.det_weight_names
            weight_name = self._strip_annotation(weight_var.get())
            if options and weight_name not in options:
                return False, role_message

        return True, ""

    def get_data(self) -> dict:
        """Get model selection data from this step.

        Returns:
            Dictionary with model_selection and weight_assignments data.
        """
        aquarium_method = self._method_key_from_label(self.aquarium_method_var.get())
        animal_method = self._method_key_from_label(self.animal_method_var.get())

        return {
            "aquarium_method": aquarium_method,
            "animal_method": animal_method,
            "use_openvino": bool(self.use_openvino_var.get()),
            "openvino_device": self._normalize_openvino_device(self.openvino_device_var.get()),
            "weight_assignments": {
                "aquarium": self._strip_annotation(self.aquarium_weight_var.get()) or None,
                "animal": self._strip_annotation(self.animal_weight_var.get()) or None,
            },
            "detector_parameters": {
                "confidence_threshold": float(self.confidence_var.get()),
                "nms_threshold": float(self.nms_var.get()),
                "track_threshold": float(self.track_var.get()),
                "match_threshold": float(self.match_var.get()),
                "use_bytetrack": self.use_bytetrack_var.get(),
                "track_buffer": int(self.track_buffer_var.get()),
                "max_center_distance": float(self.max_center_dist_var.get()),
                "iou_threshold": float(self.iou_thresh_var.get()),
            },
            "model_selection": {
                "aquarium_method": aquarium_method,
                "animal_method": animal_method,
                "use_openvino": bool(self.use_openvino_var.get()),
                "openvino_device": self._normalize_openvino_device(self.openvino_device_var.get()),
            },
        }
