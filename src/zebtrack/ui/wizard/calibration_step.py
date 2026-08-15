"""
Step 3: Physical Calibration Dialog.

Allows user to configure physical dimensions of the arena for pixel-to-cm conversion.
Provides input fields for aquarium dimensions and number of animals.
"""

from tkinter import (
    DoubleVar,
    Entry,
    Frame,
    IntVar,
    Label,
    LabelFrame,
    StringVar,
)
from tkinter import (
    font as tkfont,
)
from typing import TYPE_CHECKING, Any

from zebtrack.core.services.wizard_service import WizardService
from zebtrack.i18n import _
from zebtrack.ui.components.behavioral_config_widget import BehavioralConfigWidget
from zebtrack.ui.wizard.base import WizardStep
from zebtrack.ui.wizard.enums import ProjectType, WizardStepID
from zebtrack.ui.wizard.templates import format_template_banner
from zebtrack.ui.wizard.tooltip import ToolTip

if TYPE_CHECKING:
    from zebtrack.ui.event_bus_v2 import EventBusV2


class CalibrationStep(WizardStep):
    """
    Physical Calibration step - configure arena dimensions and animal count.

    Questions:
        - How many videos will be analyzed?
        - How many animals per video?
        - What are the physical dimensions of the arena?

    Output:
        {
            "num_aquariums": int,  # Number of videos to analyze
            "animals_per_aquarium": int,
            "aquarium_width_cm": float,
            "aquarium_height_cm": float,
        }
    """

    def __init__(
        self,
        parent: "Frame",
        wizard_data: dict[str, Any],
        event_bus: "EventBusV2 | None" = None,
    ):
        """Initialize calibration step."""
        super().__init__(parent, wizard_data)
        self.step_id = WizardStepID.CALIBRATION
        self.event_bus = event_bus

        # UI state
        self.num_aquariums_var = IntVar(value=1)
        self.animals_per_aquarium_var = IntVar(value=1)
        self.aquarium_width_var = DoubleVar(value=10.0)
        self.aquarium_height_var = DoubleVar(value=10.0)
        # Processing intervals — now consolidated here for ALL project types
        # (live and pre-recorded). Initial value is the pre-recorded default
        # (5); ``on_show`` upgrades it to 10 for live projects on first visit
        # when ``wizard_data`` doesn't already carry a saved value.
        self.analysis_interval_var = IntVar(value=5)
        self.display_interval_var = IntVar(value=5)
        self.template_info_var = StringVar(value="")
        self.template_info_label: Label | None = None

        # Behavioral analysis widget reference
        self.behavioral_config_widget: BehavioralConfigWidget | None = None

    def build_ui(self):
        """Build calibration UI - horizontal 2-column layout for better space usage."""
        # Title (full width)
        title_font = tkfont.Font(size=14, weight="bold")
        title = Label(self, text=_("Physical Calibration"), font=title_font)
        title.pack(pady=(0, 5))

        subtitle = Label(
            self,
            text=_("Set the physical dimensions of the arena to convert pixels into centimetres."),
            fg="gray",
            wraplength=700,
        )
        subtitle.pack(pady=(0, 10))

        self.template_info_label = Label(
            self,
            textvariable=self.template_info_var,
            fg="#555555",
            wraplength=700,
            justify="left",
        )
        self.template_info_label.pack_forget()

        # HORIZONTAL 2-COLUMN LAYOUT: Basic config (left) + Behavioral (right)
        content_frame = Frame(self)
        content_frame.pack(fill="both", expand=True, pady=(5, 0))
        content_frame.columnconfigure(0, weight=1, minsize=420)  # Left column (45%)
        content_frame.columnconfigure(1, weight=1, minsize=580)  # Right column (55%)
        content_frame.rowconfigure(0, weight=1)

        # LEFT COLUMN: Basic configuration sections (stacked vertically)
        left_panel = Frame(content_frame)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        # Video and animal configuration
        video_frame = LabelFrame(
            left_panel, text=_("Video and Animal Configuration"), padx=10, pady=8
        )
        video_frame.pack(fill="x", pady=(0, 8))

        # Number of aquariums (videos)
        aquarium_row = Frame(video_frame)
        aquarium_row.pack(fill="x", pady=3)

        Label(aquarium_row, text=_("Number of aquariums (videos):"), width=30, anchor="w").pack(
            side="left"
        )
        aquarium_entry = Entry(aquarium_row, textvariable=self.num_aquariums_var, width=10)
        aquarium_entry.pack(side="left", padx=(5, 0))
        ToolTip(
            aquarium_entry,
            _(
                "🎬 Number of Aquariums (Videos)\n\n"
                "How many independent videos will be analyzed in this project.\n\n"
                "• Each aquarium = 1 separate video\n"
                "• LIVE project: typically 1 (a single recording)\n"
                "• PRE-RECORDED project: may be several videos\n\n"
                "Examples:\n"
                "  • 1 aquarium: a single experiment/recording\n"
                "  • 6 aquariums: 6 different recordings (e.g. 3 groups x 2 days)\n"
                "  • 24 aquariums: a full battery of experiments\n\n"
                "💡 Tip: if you are unsure, start with 1 and add more videos later."
            ),
        )

        # Animals per aquarium
        animals_row = Frame(video_frame)
        animals_row.pack(fill="x", pady=3)

        Label(animals_row, text=_("Animals per aquarium:"), width=30, anchor="w").pack(side="left")
        animals_entry = Entry(animals_row, textvariable=self.animals_per_aquarium_var, width=10)
        animals_entry.pack(side="left", padx=(5, 0))
        ToolTip(
            animals_entry,
            _(
                "🐟 Animals per Aquarium\n\n"
                "How many animals will be present in EACH video/aquarium.\n\n"
                "Impact on the analysis:\n"
                "  • 1 animal: simplified individual tracking\n"
                "    → Ideal for: individual behavioural studies\n"
                "    → Recommended method: detection (det)\n\n"
                "  • 2-5 animals: moderate multi-animal tracking\n"
                "    → Ideal for: social interaction, small-group behaviour\n"
                "    → Recommended method: segmentation (seg)\n\n"
                "  • 6+ animals: shoal tracking\n"
                "    → Ideal for: shoal dynamics, collective behaviour\n"
                "    → Recommended method: segmentation (seg) with high confidence\n\n"
                "⚠️ IMPORTANT: this value must be the SAME for every video in the project.\n"
                "If you have videos with different animal counts, "
                "create separate projects.\n\n"
                "💡 Tip: for several animals, prefer segmentation (seg) in the "
                "model selection step."
            ),
        )

        # Physical dimensions
        dimensions_frame = LabelFrame(
            left_panel, text=_("Physical Aquarium Dimensions"), padx=10, pady=8
        )
        dimensions_frame.pack(fill="x", pady=(0, 8))

        # Width
        width_row = Frame(dimensions_frame)
        width_row.pack(fill="x", pady=3)

        Label(width_row, text=_("Width (cm):"), width=30, anchor="w").pack(side="left")
        width_entry = Entry(width_row, textvariable=self.aquarium_width_var, width=10)
        width_entry.pack(side="left", padx=(5, 0))
        ToolTip(
            width_entry,
            _(
                "📏 Aquarium Width (horizontal axis)\n\n"
                "The REAL physical size of the arena visible in the video, in centimetres.\n\n"
                "How to measure:\n"
                "  1. Identify the area visible in the video (inside the field of view)\n"
                "  2. Measure the HORIZONTAL width of that area with a ruler/tape\n"
                "  3. Measure in a straight line, from the left side to the right\n\n"
                "Typical values:\n"
                "  • Larvae (Petri dish): 5-10 cm\n"
                "  • Adults (small tank): 15-30 cm\n"
                "  • Adults (medium tank): 30-50 cm\n"
                "  • Large experimental setup: 50-100 cm\n\n"
                "Use in the analysis:\n"
                "  • Converts pixel coordinates → centimetres\n"
                "  • Allows real travelled distances to be computed\n"
                "  • Essential for speed (cm/s) and acceleration\n"
                "  • Required to compare experiments filmed with different cameras\n\n"
                "💡 Tip: if you do not know exactly, use an estimate. "
                "You can adjust it later."
            ),
        )

        # Height
        height_row = Frame(dimensions_frame)
        height_row.pack(fill="x", pady=3)

        Label(height_row, text=_("Height (cm):"), width=30, anchor="w").pack(side="left")
        height_entry = Entry(height_row, textvariable=self.aquarium_height_var, width=10)
        height_entry.pack(side="left", padx=(5, 0))
        ToolTip(
            height_entry,
            _(
                "📏 Aquarium Height (vertical axis)\n\n"
                "The REAL physical size of the arena visible in the video, in centimetres.\n\n"
                "How to measure:\n"
                "  1. Identify the area visible in the video (inside the field of view)\n"
                "  2. Measure the VERTICAL height of that area with a ruler/tape\n"
                "  3. Measure in a straight line, from top to bottom\n\n"
                "Typical values:\n"
                "  • Larvae (Petri dish): 5-10 cm\n"
                "  • Adults (small tank): 10-20 cm\n"
                "  • Adults (medium tank): 20-40 cm\n"
                "  • Large experimental setup: 40-80 cm\n\n"
                "Use in the analysis:\n"
                "  • Converts pixel coordinates → centimetres\n"
                "  • Allows real vertical distances to be computed\n"
                "  • Essential for heatmaps at real scale\n"
                "  • Required for spatial metrics (time in zones, etc.)\n\n"
                "⚠️ IMPORTANT: width and height must describe the SAME arena.\n"
                "Use the dimensions of the area VISIBLE in the video, not of the whole tank.\n\n"
                "💡 Tip: for a top-down camera, width ≈ height "
                "(a square/rectangular field of view)."
            ),
        )

        # Advanced processing settings (shown for both live and pre-recorded
        # projects so the intervals live in a single place in the wizard).
        advanced_frame = LabelFrame(
            left_panel,
            text=_("⚙️ Advanced Settings"),
            padx=10,
            pady=8,
        )
        advanced_frame.pack(fill="x", pady=(0, 8))

        # Analysis interval
        analysis_row = Frame(advanced_frame)
        analysis_row.pack(fill="x", pady=3)

        Label(analysis_row, text=_("Analysis interval (frames):"), width=30, anchor="w").pack(
            side="left"
        )
        analysis_entry = Entry(analysis_row, textvariable=self.analysis_interval_var, width=10)
        analysis_entry.pack(side="left", padx=(5, 0))
        ToolTip(
            analysis_entry,
            _(
                "🎬 Analysis Interval\n\n"
                "Processes 1 frame out of every N original frames.\n\n"
                "• N=1: analyzes every frame (maximum precision, slowest)\n"
                "• N=10: analyzes 1 frame and skips 9 (faster, ideal for long videos)\n\n"
                "💡 Tip: use 5 or 10 for a good balance between speed and precision."
            ),
        )

        # O "Intervalo de Exibição" NÃO aparece aqui de propósito: ele só regula
        # a frequência com que o overlay/preview é redesenhado na tela (ver
        # ``processing_worker`` e ``frame_processing_pipeline``) e nunca afeta os
        # dados gravados nem as métricas. Como decisão de criação de projeto ele
        # só confundia; quem precisa aliviar a UI em máquina modesta ajusta no
        # Editor de Configurações. ``display_interval_var`` segue viva e é
        # exportada por ``get_data`` para o valor continuar fluindo ao projeto.

        # RIGHT COLUMN: Behavioral analysis configuration (full height)
        behavioral_frame = LabelFrame(
            content_frame, text=_("🧠 Behavioural Analysis"), padx=10, pady=8
        )
        behavioral_frame.grid(row=0, column=1, sticky="nsew")

        # Determine defaults from global settings
        from zebtrack.settings import load_settings

        settings = load_settings()

        def_thig = settings.behavioral_analysis.default_thigmotaxis_distance_cm
        def_geo = settings.behavioral_analysis.default_geotaxis_distance_cm
        def_geo_zones = settings.behavioral_analysis.default_geotaxis_num_zones
        def_geo_btm = settings.behavioral_analysis.default_geotaxis_bottom_zones

        # Defaults for perspective and mode (added in Phase 9)
        def_perspective = "lateral"
        def_geotaxis_mode = "zones"
        if hasattr(settings.behavioral_analysis, "aquarium_perspective"):
            def_perspective = settings.behavioral_analysis.aquarium_perspective
        if hasattr(settings.behavioral_analysis, "geotaxis_mode"):
            def_geotaxis_mode = settings.behavioral_analysis.geotaxis_mode

        self.behavioral_config_widget = BehavioralConfigWidget(
            behavioral_frame,
            default_thigmotaxis_cm=def_thig,
            default_geotaxis_cm=def_geo,
            default_num_zones=def_geo_zones,
            default_bottom_zones=def_geo_btm,
            default_perspective=def_perspective,
            default_geotaxis_mode=def_geotaxis_mode,
            event_bus=self.event_bus,
        )
        self.behavioral_config_widget.pack(fill="x", expand=True)

        # Help text
        help_frame = LabelFrame(self, text=_("About Calibration"), padx=15, pady=10)
        help_frame.pack(fill="x", pady=(15, 0))

        help_text = Label(
            help_frame,
            text=_(
                "Physical calibration makes it possible to convert pixel coordinates "
                "into centimetres.\n\n"
                "This is needed to:\n"
                "• Compute real travelled distances\n"
                "• Compute speeds in cm/s\n"
                "• Compare results across different camera setups\n\n"
                "💡 Tip: if you do not know the exact dimensions, you can use "
                "the default values and adjust them later in the project settings."
            ),
            fg="gray",
            wraplength=500,
            justify="left",
        )
        help_text.pack()
        self._update_template_banner()

    def validate(self) -> tuple[bool, str]:
        """
        Validate calibration using WizardService.

        Returns:
            tuple[bool, str]: (True, "") if all inputs are valid,
                             (False, error_message) otherwise
        """
        try:
            # Get current data and use WizardService for validation
            data = self.get_data()
            is_valid, error_msg = WizardService.validate_basic_calibration(data)

            return (is_valid, error_msg)

        except Exception as e:
            return (False, _("Error validating data: {error}").format(error=str(e)))

    def get_data(self) -> dict[str, Any]:
        """
        Extract calibration data.

        Returns:
            dict: Calibration data with keys:
                - num_aquariums (int)
                - animals_per_aquarium (int)
                - aquarium_width_cm (float)
                - aquarium_height_cm (float)
                - behavioral_analysis (dict)
        """
        data: dict[str, Any] = {
            "num_aquariums": self.num_aquariums_var.get(),
            "animals_per_aquarium": self.animals_per_aquarium_var.get(),
            "aquarium_width_cm": self.aquarium_width_var.get(),
            "aquarium_height_cm": self.aquarium_height_var.get(),
            "analysis_interval_frames": self.analysis_interval_var.get(),
            "display_interval_frames": self.display_interval_var.get(),
        }

        # Add behavioral analysis configuration
        if self.behavioral_config_widget:
            data["behavioral_analysis"] = self.behavioral_config_widget.get_values()

        return data

    def set_data(self, data: dict[str, Any]) -> None:
        """
        Restore UI from data (for back navigation).

        Args:
            data: Previously collected calibration data
        """
        if "num_aquariums" in data:
            self.num_aquariums_var.set(data["num_aquariums"])

        if "animals_per_aquarium" in data:
            self.animals_per_aquarium_var.set(data["animals_per_aquarium"])

        if "aquarium_width_cm" in data:
            self.aquarium_width_var.set(data["aquarium_width_cm"])

        if "aquarium_height_cm" in data:
            self.aquarium_height_var.set(data["aquarium_height_cm"])

        if "analysis_interval_frames" in data:
            self.analysis_interval_var.set(data["analysis_interval_frames"])

        if "display_interval_frames" in data:
            self.display_interval_var.set(data["display_interval_frames"])

        # Restore behavioral analysis configuration
        if "behavioral_analysis" in data and self.behavioral_config_widget:
            self.behavioral_config_widget.set_values(data["behavioral_analysis"])

        self._update_template_banner()

    def on_show(self) -> None:
        """Execute actions when step becomes visible."""
        self._update_template_banner()

        if "num_aquariums" in self.wizard_data:
            self.num_aquariums_var.set(self.wizard_data["num_aquariums"])

        if "animals_per_aquarium" in self.wizard_data:
            self.animals_per_aquarium_var.set(self.wizard_data["animals_per_aquarium"])

        if "aquarium_width_cm" in self.wizard_data:
            self.aquarium_width_var.set(self.wizard_data["aquarium_width_cm"])

        if "aquarium_height_cm" in self.wizard_data:
            self.aquarium_height_var.set(self.wizard_data["aquarium_height_cm"])

        # Pick the right interval default once project_type is known. Live
        # projects get 10/10 (lighter real-time load); pre-recorded keeps the
        # 5/5 default. Persisted wizard_data values always win so back/forward
        # navigation preserves user edits.
        live_default = 10 if self._is_live_project() else 5
        self.analysis_interval_var.set(
            self.wizard_data.get("analysis_interval_frames", live_default)
        )
        self.display_interval_var.set(self.wizard_data.get("display_interval_frames", live_default))

        # Auto-detect number of aquariums from video count
        video_count = self.wizard_data.get("video_count", 0)
        if video_count > 0 and "num_aquariums" not in self.wizard_data:
            # Only set if user hasn't modified it yet
            current_value = self.num_aquariums_var.get()
            if current_value == 1 and video_count > 1:
                self.num_aquariums_var.set(video_count)

        # Restore behavioral analysis configuration
        if "behavioral_analysis" in self.wizard_data and self.behavioral_config_widget:
            self.behavioral_config_widget.set_values(self.wizard_data["behavioral_analysis"])

    def _update_template_banner(self):
        banner_text = format_template_banner(self.wizard_data.get("template_metadata"))

        if banner_text:
            self.template_info_var.set(banner_text)
            if self.template_info_label and not self.template_info_label.winfo_ismapped():
                self.template_info_label.pack(pady=(0, 10))
        else:
            self.template_info_var.set("")
            if self.template_info_label and self.template_info_label.winfo_ismapped():
                self.template_info_label.pack_forget()

    def _is_live_project(self) -> bool:
        """Return True when current wizard flow is for live projects."""
        return self.wizard_data.get("project_type") == ProjectType.LIVE.value
