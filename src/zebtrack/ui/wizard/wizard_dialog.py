"""
Main wizard dialog orchestrator.

Manages 5-step wizard flow, navigation, and data accumulation.
"""

from datetime import UTC, datetime
from tkinter import Frame, messagebox
from tkinter.simpledialog import Dialog
from typing import TYPE_CHECKING, Any

import structlog

from zebtrack.ui.wizard.base import WizardStep
from zebtrack.ui.wizard.cache import WizardCache

if TYPE_CHECKING:
    from zebtrack.settings import Settings
from zebtrack.ui.wizard.calibration_step import CalibrationStep
from zebtrack.ui.wizard.confirmation_step import ConfirmationStep
from zebtrack.ui.wizard.detection_step import DetectionStep
from zebtrack.ui.wizard.discovery_step import DiscoveryStep
from zebtrack.ui.wizard.enums import ProjectType, WizardStepID
from zebtrack.ui.wizard.experimental_design_step import ExperimentalDesignStep
from zebtrack.ui.wizard.file_selection_step import FileSelectionStep
from zebtrack.ui.wizard.import_config_step import ImportConfigStep
from zebtrack.ui.wizard.live_config_step import LiveConfigStep
from zebtrack.ui.wizard.model_selection_step import ModelSelectionStep

if TYPE_CHECKING:
    from zebtrack.ui.event_bus import EventBus

log = structlog.get_logger()


class WizardDialog(Dialog):
    """
    Main wizard orchestrator for 7-step project creation (dynamic based on type).

    Architecture:
        - Each step is a WizardStep instance
        - wizard_data dict accumulates data across all steps
        - cache provides session-level caching for performance
        - Navigation via Back/Next buttons (validated transitions)
        - Conditional navigation: steps shown/hidden based on project type

    Steps (Pre-recorded: Experimental/Exploratory):
        1. Discovery: Project type, folder structure, parquet import scope
        2. File Selection: Select videos and folders
        3. Calibration: Physical dimensions and animal configuration
        4. Detection: Auto-detect design, analyze parquets
        5. Import Config: Configure per-video import strategy
        6. Confirmation: Final review and project creation

    Steps (Live):
        1. Discovery: Project type selection
        2. Live Config: Camera, Arduino, recording settings
        3. Calibration: Physical dimensions and animal configuration
        4. Confirmation: Final review and project creation

    Usage:
        >>> wizard = WizardDialog(root)
        >>> if wizard.result:
        ...     controller.create_new_project(**wizard.result)

    Attributes:
        all_steps (list[WizardStep]): All possible wizard steps
        current_step_index (int): Currently visible step index in active_steps
        active_steps (list[WizardStep]): Steps actually shown (filtered by project type)
        wizard_data (dict): Accumulated data from all steps
        cache (WizardCache): Session cache for performance
        result (dict | None): Final wizard output or None if cancelled
    """

    def __init__(
        self,
        parent,
        settings_obj: "Settings | None" = None,
        event_bus: "EventBus | None" = None,
    ):
        """
        Initialize wizard dialog.

        Args:
            parent: Parent Tkinter widget (usually root window)
            settings_obj: Settings instance (optional)
            event_bus: EventBus instance (optional)
        """
        self.all_steps: dict[
            WizardStepID, WizardStep
        ] = {}  # All possible steps indexed by WizardStepID
        self.active_steps: list[
            WizardStep
        ] = []  # Steps for current project type (updated dynamically)
        self.current_step_index = 0
        self.wizard_data: dict[str, Any] = {
            "wizard_schema_version": 3,  # v3.0: Model selection & detector params
            "created_at": datetime.now(UTC).isoformat(),
        }
        self.cache = WizardCache()
        self.result: dict[str, Any] | None = None  # Will be set on successful completion
        self._geometry_initialized = False
        self.settings = settings_obj  # Store settings for steps
        self.event_bus = event_bus

        log.info("wizard.opened")

        # Call parent constructor (will call body())
        super().__init__(parent, title="DRerio LogAI - Novo Projeto")

        # Set application icon
        from zebtrack.ui.icon_utils import set_window_icon

        set_window_icon(self)

    def body(self, master):
        """
        Build wizard UI (called by Dialog.__init__).

        Args:
            master: Parent widget for body content

        Returns:
            Widget: Widget to receive initial focus (or None)
        """
        try:
            self.resizable(True, True)
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("wizard.geometry.resizable_failed", error=str(exc))

        # Configure master grid so steps stretch while buttons stay anchored
        master.grid_rowconfigure(0, weight=1)
        master.grid_columnconfigure(0, weight=1)
        self._body_frame = master

        # Create container for steps
        self.steps_container = Frame(master)
        self.steps_container.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 8))

        # Initialize ALL possible steps (not all will be shown)
        self.all_steps = {
            WizardStepID.DISCOVERY: DiscoveryStep(self.steps_container, self.wizard_data),
            WizardStepID.FILE_SELECTION: FileSelectionStep(self.steps_container, self.wizard_data),
            WizardStepID.LIVE_CONFIG: LiveConfigStep(
                self.steps_container, self.wizard_data, settings_obj=self.settings
            ),
            WizardStepID.EXPERIMENTAL_DESIGN: ExperimentalDesignStep(
                self.steps_container, self.wizard_data
            ),
            WizardStepID.CALIBRATION: CalibrationStep(
                self.steps_container, self.wizard_data, event_bus=self.event_bus
            ),
            WizardStepID.DETECTION_VALIDATION: DetectionStep(
                self.steps_container, self.wizard_data
            ),
            WizardStepID.MODEL_SELECTION: ModelSelectionStep(
                self.steps_container, self.wizard_data, settings_obj=self.settings
            ),
            WizardStepID.IMPORT_CONFIG: ImportConfigStep(self.steps_container, self.wizard_data),
            WizardStepID.CONFIRMATION: ConfirmationStep(self.steps_container, self.wizard_data),
        }

        # Build UI for all steps (even if not shown)
        for step in self.all_steps.values():
            step.build_ui()

        # Initially set active steps for default project type
        # (experimental pre-recorded)
        self._update_active_steps()

        # Show first step
        self._show_step(0)

        # Return None (no specific focus)
        return None

    def buttonbox(self):
        """
        Create navigation buttons (overrides Dialog.buttonbox).

        Creates: [< Voltar] [Próximo >] [Cancelar]
        """
        from tkinter import Button

        body_frame = getattr(self, "_body_frame", self)
        body_frame.grid_rowconfigure(1, weight=0)

        box = Frame(body_frame)
        box.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))

        # Back button (disabled on first step)
        self.back_button = Button(box, text="< Voltar", width=10, command=self._on_back)
        self.back_button.pack(side="left", padx=5)

        # Next / Create Project button (text changes on last step)
        self.next_button = Button(box, text="Próximo >", width=15, command=self._on_next)
        self.next_button.pack(side="left", padx=5)

        # Cancel button
        cancel_button = Button(box, text="Cancelar", width=10, command=self._on_cancel)
        cancel_button.pack(side="right", padx=5)

        self._update_navigation_buttons()

        # Force geometry initialization after buttonbox is created
        # This ensures proper centering after Dialog has finished its setup
        self.after(1, self._initialize_geometry)

    def _update_active_steps(self):
        """
        Update the list of active steps based on project type.

        Called after Discovery step when project type is selected.
        """
        project_type = self.wizard_data.get("project_type", ProjectType.EXPERIMENTAL.value)

        if project_type == ProjectType.LIVE.value:
            # Live project flow: Discovery -> Experimental Design -> Live Config
            # -> Calibration -> Model Selection -> Confirmation
            self.active_steps = [
                self.all_steps[WizardStepID.DISCOVERY],
                self.all_steps[WizardStepID.EXPERIMENTAL_DESIGN],
                self.all_steps[WizardStepID.LIVE_CONFIG],
                self.all_steps[WizardStepID.CALIBRATION],
                self.all_steps[WizardStepID.MODEL_SELECTION],
                self.all_steps[WizardStepID.CONFIRMATION],
            ]
            log.info(
                "wizard.active_steps_updated",
                project_type="live",
                step_count=6,
            )
        else:
            # Pre-recorded flow (experimental or exploratory):
            # Discovery -> File Selection -> Calibration -> Detection ->
            # Model Selection -> Import Config -> Confirmation
            self.active_steps = [
                self.all_steps[WizardStepID.DISCOVERY],
                self.all_steps[WizardStepID.FILE_SELECTION],
                self.all_steps[WizardStepID.CALIBRATION],
                self.all_steps[WizardStepID.DETECTION_VALIDATION],
                self.all_steps[WizardStepID.MODEL_SELECTION],
                self.all_steps[WizardStepID.IMPORT_CONFIG],
                self.all_steps[WizardStepID.CONFIRMATION],
            ]
            log.info(
                "wizard.active_steps_updated",
                project_type=project_type,
                step_count=7,
            )

    def _show_step(self, step_index: int):
        """
        Show specific step and hide others.

        Args:
            step_index: Index of step to show in active_steps
        """
        # Hide all steps
        for step in self.all_steps.values():
            step.pack_forget()

        # Show selected step
        if 0 <= step_index < len(self.active_steps):
            self.current_step_index = step_index
            current_step = self.active_steps[step_index]
            current_step.pack(fill="both", expand=True)
            current_step.on_show()  # Lifecycle hook

            # Update window title with step number
            step_number = step_index + 1
            total_steps = len(self.active_steps)
            title_text = f"DRerio LogAI - Assistente de Projeto (Etapa {step_number}/{total_steps})"
            self.title(title_text)

            log.info(
                "wizard.step_shown",
                step=step_index + 1,
                step_id=current_step.step_id.value if current_step.step_id else None,
            )
            self._update_navigation_buttons()
            self._update_minimum_size()

    def _update_navigation_buttons(self):
        """Update navigation button states based on current step."""
        # Buttons are created in buttonbox() which is called after body()
        # So we need to check if they exist first
        if not hasattr(self, "back_button") or not hasattr(self, "next_button"):
            return

        # Back button: disabled on first step
        if self.current_step_index == 0:
            self.back_button.config(state="disabled")
        else:
            self.back_button.config(state="normal")

        # Next button: changes to "Criar Projeto" on last step
        if self.current_step_index == len(self.active_steps) - 1:
            self.next_button.config(text="Criar Projeto")
        else:
            self.next_button.config(text="Próximo >")

    def _initialize_geometry(self):
        """
        Configure initial geometry with FIXED, conservative size.

        Forces window to center on screen after Dialog construction.
        """
        if not self.winfo_exists():
            return

        # Allow re-initialization to force centering after Dialog positioning
        if self._geometry_initialized:
            # Just re-apply centering without changing size
            self._center_window()
            return

        try:
            self.resizable(True, True)
        except Exception:
            return

        self.update_idletasks()

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        # Reserve MORE space for taskbar and decorations to ensure buttons visible
        # Vertical: 220px (taskbar ~40-50px + title bar ~30px + bottom margin ~100px)
        # Horizontal: 80px (margins)
        usable_w = screen_w - 80
        usable_h = screen_h - 220

        # FIXED SIZE STRATEGY: Optimized for 1080p screens with taskbar/scaling
        # Previous: 1150x850 (can overflow on 1080p with 125%+ scaling)
        # New: 1050x780 (fits 1080p reliably, increased 30px for calibration step)

        target_width = 1050
        target_height = 780

        # But don't exceed available space on smaller screens
        width = min(target_width, usable_w)
        height = min(target_height, usable_h)

        # Ensure absolute minimums for usability
        width = max(width, 900)
        if usable_h >= 650:
            height = max(height, 650)

        # Set resizable bounds (more conservative for better compatibility)
        min_width = max(int(target_width * 0.80), 850)
        min_height = max(int(target_height * 0.80), 520)
        max_width = int(target_width * 1.15)
        max_height = int(target_height * 1.1)

        # Center on screen with simple calculation
        # Reserve space only for Windows taskbar (typically 40-60px)
        taskbar_reserve = 70  # Conservative reserve for taskbar

        x = (screen_w - width) // 2
        # Center vertically but ensure bottom stays above taskbar
        y_center = (screen_h - height) // 2
        y_safe = screen_h - height - taskbar_reserve
        y = min(y_center, y_safe)

        # Ensure window doesn't go off top of screen
        y = max(y, 20)

        self.geometry(f"{int(width)}x{int(height)}+{int(x)}+{int(y)}")
        self.minsize(int(min_width), int(min_height))
        self.maxsize(int(max_width), int(max_height))

        self._geometry_initialized = True
        log.info(
            "wizard.geometry_initialized",
            size=f"{int(width)}x{int(height)}",
            screen=f"{screen_w}x{screen_h}",
            position=f"+{int(x)}+{int(y)}",
            centered=True,
        )

    def _center_window(self):
        """
        Center the window on screen using current window size.

        Called after Dialog has positioned itself to force centering.
        """
        self.update_idletasks()

        # Get current window size
        width = self.winfo_width()
        height = self.winfo_height()

        # Get screen dimensions
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        # Center on screen with simple calculation
        # Reserve space only for Windows taskbar (typically 40-60px)
        taskbar_reserve = 70  # Conservative reserve for taskbar

        x = (screen_w - width) // 2
        # Center vertically but ensure bottom stays above taskbar
        y_center = (screen_h - height) // 2
        y_safe = screen_h - height - taskbar_reserve
        y = min(y_center, y_safe)

        # Ensure window doesn't go off top of screen
        y = max(y, 20)

        # Apply new position only (keep current size)
        self.geometry(f"+{int(x)}+{int(y)}")

        log.info(
            "wizard.window_centered",
            size=f"{width}x{height}",
            position=f"+{int(x)}+{int(y)}",
        )

    def _update_minimum_size(self):
        """
        Maintain fixed window size when step changes.

        With fixed-size strategy, we DON'T resize the window between steps.
        Steps should be designed to fit within the allocated space (950x620).
        """
        # No-op: window maintains fixed size
        pass

    def _on_back(self):
        """Handle Back button click."""
        if self.current_step_index > 0:
            # Hide current step
            self.active_steps[self.current_step_index].on_hide()

            # Restore previous step with data
            prev_step = self.active_steps[self.current_step_index - 1]
            step_id = prev_step.step_id
            if step_id:
                prev_data: dict[str, Any] = self.wizard_data.get(step_id.name.lower(), {})
            else:
                prev_data = {}
            prev_step.set_data(prev_data)

            # Show previous step
            self._show_step(self.current_step_index - 1)

            log.info("wizard.step_back", from_step=self.current_step_index + 2)

    def _on_next(self):
        """Handle Next button click (or Create Project on last step)."""
        current_step = self.active_steps[self.current_step_index]

        # Validate current step
        is_valid, error_message = current_step.validate()
        if not is_valid:
            messagebox.showerror("Validação", error_message, parent=self)
            log.warning(
                "wizard.validation_failed",
                step=self.current_step_index + 1,
                error=error_message,
            )
            return

        # Extract and store step data
        step_data = current_step.get_data()
        self.wizard_data.update(step_data)

        log.info(
            "wizard.step_completed",
            step=self.current_step_index + 1,
            data_keys=list(step_data.keys()),
        )

        # Hide current step
        current_step.on_hide()

        # Special: Update active steps after Discovery (project type selected)
        if current_step.step_id == WizardStepID.DISCOVERY:
            self._update_active_steps()

        # Last step? Finish wizard
        if self.current_step_index == len(self.active_steps) - 1:
            self._finish()
        else:
            # Advance to next step
            self._show_step(self.current_step_index + 1)

    def _on_cancel(self):
        """Handle Cancel button click."""
        # Ask for confirmation if user has entered data
        if self.current_step_index > 0:
            confirm = messagebox.askyesno(
                "Cancelar",
                "Descartar rascunho do projeto?",
                parent=self,
                icon="warning",
            )
            if not confirm:
                return

        log.info("wizard.cancelled", step=self.current_step_index + 1)
        self.result = None
        self.destroy()

    def _finish(self):
        """
        Finish wizard and return result.

        Called when user clicks "Criar Projeto" on last step.
        Sets self.result and closes dialog.
        """
        log.info(
            "wizard.finished",
            total_steps=len(self.active_steps),
            data_size=len(str(self.wizard_data)),
        )

        self.result = self.wizard_data
        self.destroy()
