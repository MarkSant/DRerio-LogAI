"""Main graphical user interface (GUI) module for the Zebtrack application."""

from collections.abc import Callable
from tkinter import (
    BooleanVar,
    Button,
    Label,
    Menu,
    StringVar,
    TclError,
    ttk,
)
from tkinter import font as tkfont
from typing import Any, cast

import numpy as np
import structlog

try:
    import ttkbootstrap as ttkb
except ImportError:  # pragma: no cover - optional dependency fallback
    ttkb = cast(Any, None)

# Import custom modules
from zebtrack.core.detection import ZoneData
from zebtrack.core.video.processing_mode import ProcessingMode, ProcessingReport
from zebtrack.ui.builders import ButtonFactory, PanelBuilder, ZoneControlBuilder
from zebtrack.ui.components import (
    AnalysisDisplayWidget,
    ArduinoDashboardWidget,
    CanvasManager,
    ConfigEditorWidget,
    DialogManager,
    DrawingStateManager,
    EventDispatcher,
    MenuManager,
    PolygonDrawingService,
    ProjectOverviewWidget,
    ROITemplateManager,
    StateSynchronizer,
    TabBuilder,
    ValidationManager,
    WidgetFactory,
)
from zebtrack.ui.components.analysis_view_controller import AnalysisViewController
from zebtrack.ui.components.project_initializer import ProjectInitializer
from zebtrack.ui.components.project_views import (
    ReportsTreeManager,
    VideoSelectorTreeManager,
)
from zebtrack.ui.components.single_video_workflow import SingleVideoWorkflow
from zebtrack.ui.components.weight_hardware_manager import WeightHardwareManager
from zebtrack.ui.components.zone_edit_guard import ZoneEditGuard
from zebtrack.ui.decorators import public_api
from zebtrack.ui.dialogs import (
    CalibrationDialog,
    MissingMetadataDialog,
    SaveROITemplateDialog,
    StartRecordingDialog,
)
from zebtrack.ui.event_bus import EventBus
from zebtrack.ui.event_bus_v2 import Event, EventBusV2, UIEvents
from zebtrack.ui.ui_coordinator import UICoordinator

log = structlog.get_logger()

STATUS_SYMBOLS = {
    "arena": "\U0001f3df",  # 🏟
    "rois": "\U0001f3af",  # 🎯
    "trajectory": "\U0001f9ed",  # 🧭
    "summary": "\u03a3",  # Σ
}

PROJECT_STATUS_META: dict[str, tuple[str, str]] = {
    "pending": ("⏳", "Pendentes"),
    "processing": ("🔁", "Processando"),
    "processed": ("📦", "Com dados"),
    "complete": ("✅", "Concluídos"),
    "failed": ("⚠️", "Com falha"),
}

PROJECT_STATUS_WIDGET_ORDER: tuple[str, ...] = (
    "total",
    "pending",
    "processing",
    "processed",
    "complete",
    "failed",
    "arena",
    "rois",
    "trajectory",
    "summary",
)


class ApplicationGUI:
    """Main class that manages the graphical user interface (the View layer)."""

    DEFAULT_CANVAS_WIDTH = 800
    DEFAULT_CANVAS_HEIGHT = 600

    def __init__(
        self,
        root,
        controller,
        event_bus: EventBus | None = None,
        settings_obj=None,
        project_manager: Any | None = None,
    ):
        """Initialize the ApplicationGUI."""
        self.root = root
        self.controller = controller
        self.event_bus = event_bus
        self.settings = settings_obj
        # Use injected project_manager or fallback to controller (legacy)
        self.project_manager = project_manager or getattr(controller, "project_manager", None)
        self._event_bus_after_id: int | None = None
        self._event_bus_poll_interval_ms = 50
        self._event_bus_handlers: dict[str, Callable[[Any], None]] = {}

        # Initialize Event Bus V2 for Event-Driven Architecture (v4.0)
        self.event_bus_v2 = EventBusV2()

        # Subscribe to VideoProcessingService events (v2.2 UI decoupling)
        self.event_bus_v2.subscribe(
            UIEvents.ERROR_OCCURRED,
            lambda data: self.root.after(
                0,
                lambda: self.show_error(
                    data.get("title", "Erro"),
                    data.get("message", "Ocorreu um erro desconhecido."),
                ),
            ),
        )

        self.root.title("DRerio LogAI")
        self.root.protocol("WM_DELETE_WINDOW", self.controller.on_close)

        self._ttkbootstrap_style: Any | None = None
        self._ttkbootstrap_theme: Any | None = None
        self._initialize_theme()

        # Initialize state variables before components
        self.notebook: ttk.Notebook | None = None
        self.welcome_frame: ttk.Frame | None = None
        self.main_controls_frame: ttk.Frame | None = None
        self.zone_tab_frame: ttk.Frame | None = None
        self.analysis_tab_frame: ttk.Frame | None = None
        self.analysis_metadata_var: Any | None = None

        # Initialize component managers (extracted from God Object)
        # Phase 1 components
        self.menu_manager = MenuManager(self)
        self.canvas_manager = CanvasManager(self, event_bus_v2=self.event_bus_v2)
        self.state_synchronizer = StateSynchronizer(self)
        self.event_dispatcher = EventDispatcher(self)

        # Debug: Verify event_bus propagation to EventDispatcher
        log.info(
            "gui.init.event_dispatcher_created",
            gui_event_bus_id=id(self.event_bus) if self.event_bus else None,
            dispatcher_event_bus_id=id(self.event_dispatcher.event_bus)
            if self.event_dispatcher.event_bus
            else None,
            same_bus=self.event_bus is self.event_dispatcher.event_bus if self.event_bus else "N/A",
        )

        # Phase 2 components (with dependency injection)
        self.validation_manager = ValidationManager(self, settings_obj=self.settings)
        self.dialog_manager = DialogManager(self, event_bus_v2=self.event_bus_v2)
        self.widget_factory = WidgetFactory(self, settings_obj=self.settings)
        self.reports_tree_manager = ReportsTreeManager(self, event_bus_v2=self.event_bus_v2)
        self.video_selector_manager = VideoSelectorTreeManager(self, event_bus_v2=self.event_bus_v2)
        # Backward-compat alias used by shims and tests
        self.project_view_manager = self.video_selector_manager

        # Phase 2.5: Initialize UI Coordinator (Mediator)
        self.ui_coordinator = UICoordinator(
            event_bus=self.event_bus_v2,
            legacy_event_bus=self.event_bus,
            canvas_manager=self.canvas_manager,
            validation_manager=self.validation_manager,
            video_selector_manager=self.video_selector_manager,
            reports_tree_manager=self.reports_tree_manager,
            dialog_manager=self.dialog_manager,
            state_synchronizer=self.state_synchronizer,
            root=self.root,
        )

        # Phase 3 components
        self.drawing_state_manager = DrawingStateManager()
        self.polygon_drawing_service = PolygonDrawingService(event_bus_v2=self.event_bus_v2)

        # Phase 4 components
        self.roi_template_manager = ROITemplateManager(
            self.project_manager, self, event_bus_v2=self.event_bus_v2
        )

        # Phase 5 components
        self.tab_builder = TabBuilder(self)

        # Phase 5 builders (zone control widgets, buttons, panels)
        self.zone_control_builder = ZoneControlBuilder(self, event_bus_v2=self.event_bus_v2)
        self.button_factory = ButtonFactory()
        self.panel_builder = PanelBuilder()

        # Phase 6 components (extracted from gui.py — Phase 4.4 decomposition)
        self.analysis_view_controller = AnalysisViewController(self)
        self.project_initializer = ProjectInitializer(self)
        self.single_video_workflow = SingleVideoWorkflow(self)
        self.weight_hardware_manager = WeightHardwareManager(self)
        self.zone_edit_guard = ZoneEditGuard(self)

        # Create menu bar
        self.menu_manager.create_menu_bar()

        # --- Legacy Attributes (Shim Layer for Components) ---
        # These attributes are initialized here to prevent AttributeErrors in components
        # that still access them directly on the GUI object.
        self.edited_polygon_points: list[list[float]] = []
        self.interactive_polygon_item: Any | None = None
        self.polygon_handles: list[Any] = []
        self.current_editing_zone: Any | None = None
        self._dragged_handle_index: int | None = None
        self._drag_offset: tuple[float, float] = (0, 0)
        self._drag_start_mouse: tuple[float, float] = (0, 0)
        self._original_image: Any | None = None
        self._raw_bg_image: Any | None = None
        self._canvas_bg_image: Any | None = None
        self._roi_templates_cache: list[dict[str, Any]] = []
        self.roi_choice_var = StringVar(value="none")
        self.video_path: str | None = None
        self.video_display: Any | None = None
        self.controls_canvas: Any | None = None
        self.controls_canvas_window: Any | None = None
        self.zone_controls_frame: Any | None = None
        self._roi_canvas_widget: Any | None = None
        self.controls_scrollbar: Any | None = None  # Added for WidgetFactory
        self.fixed_button_frame: ttk.Frame | None = None
        self.roi_data: dict[str, Any] = {}  # Added for TabBuilder
        self.viz_frame: ttk.Frame | None = None  # Added for TabBuilder
        self.viz_top_container: ttk.Frame | None = None  # Added for TabBuilder
        self.viz_bottom_container: ttk.Frame | None = None  # Added for TabBuilder
        self._project_status_containers: dict[str, Any] = {}
        self._last_overview_counts: dict[str, int] = {}
        self._last_selected_tab_id: str | None = None
        # -----------------------------------------------------

        # Dynamic widgets / state variables
        self.zone_summary_frame: ttk.LabelFrame | None = None
        self.project_overview_frame: ttk.LabelFrame | None = None  # Added to fix AttributeError
        self.zone_controls: Any | None = None  # Added to fix AttributeError
        self.zone_summary_cards: dict[str, dict[str, StringVar]] = {}
        self.pipeline_tab_frame: ttk.Frame | None = None
        self.pipeline_video_tree: ttk.Treeview | None = None
        self.pipeline_video_vars: dict[str, dict[str, StringVar]] = {}
        self.pipeline_selection_label: ttk.Label | None = None
        self.pipeline_action_buttons: dict[str, ttk.Button] = {}
        # New unified Processing and Reports tab
        self.processing_reports_tab_frame: ttk.Frame | None = None
        self.processing_reports_widget = None
        self._processing_reports_tree_metadata: dict[str, dict] = {}
        self.drawing_instruction_label = None
        self.current_drawing_type = None
        self.status_var = StringVar()
        self.pending_single_video_path: str | None = None
        self.pending_single_video_config: dict[str, Any] | None = None
        self.start_single_analysis_btn: ttk.Button | None = None
        self._zone_prompt_history: set[str] = set()

        # Model management state (reflected across welcome + project views)
        self._available_weight_names: list[str] = []
        self._active_weight_display_var = StringVar(value="Peso ativo: Nenhum peso selecionado.")
        self._openvino_display_var = StringVar(value="OpenVINO: Desativado.")
        self._gpu_hardware_display_var = StringVar(value="Hardware: Detectando...")
        self._openvino_enabled = False
        self._openvino_status_message = "Desativado."

        # ROI Tab Widgets
        self.roi_listbox = None
        self.run_analysis_btn = None
        # Note: roi_template_combobox is now a @property that delegates to zone_controls

        # ROI Inclusion Rule Variables
        self.roi_inclusion_rule_var = StringVar(
            value=(self.settings.roi_inclusion_rule if self.settings else "bbox_intersects")
        )
        self.roi_buffer_radius_var = StringVar(
            value=str(self.settings.roi_buffer_radius_value if self.settings else 0.5)
        )
        self.roi_overlap_ratio_var = StringVar(
            value=str(self.settings.roi_min_bbox_overlap_ratio if self.settings else 0.10)
        )
        self.roi_template_var = StringVar(value="")
        # Add trace to log all changes to template var
        self.roi_template_var.trace_add("write", self._on_roi_template_var_changed)
        self.delete_template_btn: ttk.Button | None = None

        # Configuration editor widget (created in notebook)
        self.config_editor_widget: ConfigEditorWidget | None = None

        # Analysis display widget (created later in notebook)
        self.analysis_display_widget: AnalysisDisplayWidget | None = None
        self._active_processing_mode = ProcessingMode.MULTI_TRACK

        self._available_track_options: tuple[str, ...] = ("Todos",)
        self._current_detections: list[tuple] = []
        self._last_analysis_frame = None
        self._analysis_overlay_image = None

        # Analysis status widgets and variables
        self.analysis_status_var = StringVar(value="Nenhuma análise em andamento.")
        self.analysis_task_var = StringVar(value="Nenhuma tarefa em andamento.")
        self.analysis_profile_var = StringVar(value="Perfil de análise: default")
        self.analysis_video_label: Label | None = None

        # User options
        self.processing_interval_var = StringVar(
            value=str(self.settings.video_processing.processing_interval if self.settings else 10)
        )
        self.show_preview_var = BooleanVar(value=True)

        # New frame interval controls (defaults to 10 as per requirements)
        self.analysis_interval_var = StringVar(value="10")
        self.display_interval_var = StringVar(value="10")

        # View toggle state for analysis/zone switching
        self.canvas_view_mode = "zones"  # "zones" or "analysis"
        self.analysis_active = False

        self.start_rec_btn: Button | None = None
        self.stop_rec_btn: Button | None = None
        self.process_video_btn: ttk.Button | None = None

        # Interactive arena editing state
        self.stabilization_frames_var = StringVar(value="10")
        self.interactive_polygon_item = None
        self.polygon_handles = []
        self.edited_polygon_points = []
        self._dragged_handle_index = None
        self._drag_offset = (0, 0)
        self.current_editing_zone = None  # Track what zone is being edited
        self._zones_dirty = False  # Track unsaved zone changes (template applied, ROI drawn, etc.)
        self.project_overview_widget: ProjectOverviewWidget | None = None
        # Backward compatibility - delegate to widget
        self._project_status_containers = {}
        self._overview_refresh_job = None
        self._pending_overview_status: str | None = None
        self._overview_status_append = False
        self._last_overview_counts = {}
        self._overview_video_index: dict[str, dict] = {}
        self._overview_context_menu: Menu | None = None
        self._overview_menu_font: tkfont.Font | None = None

        # Arduino dashboard widget (live projects)
        self.arduino_dashboard_widget: ArduinoDashboardWidget | None = None
        self.external_trigger_notice_var = StringVar(value="")
        self.external_trigger_notice_label: Label | None = None
        self._external_notice_default_bg: str | None = None
        self._external_notice_default_fg: str | None = None

        # Defer controller state initialization to avoid tight coupling during __init__
        self.root.after(100, self._post_init)

        self.widget_factory.create_welcome_frame()

        log.info("gui.init.event_bus_setup", has_event_bus=self.event_bus is not None)
        if self.event_bus is not None:
            log.info("gui.init.registering_handlers")
            self.event_dispatcher.register_event_bus_handlers()
            log.info("gui.init.subscribing_to_ui_events")
            # New: Subscribe to Controller->UI events
            self.event_dispatcher.subscribe_to_ui_events()
            log.info("gui.init.scheduling_first_poll")
            self.event_dispatcher.schedule_event_bus_poll()
            log.info("gui.init.event_bus_setup_complete")
        else:
            log.warning("gui.init.no_event_bus")

        # Subscribe to StateManager state changes for reactive UI updates
        self.state_synchronizer.subscribe_to_state_changes()

    def _post_init(self) -> None:
        """
        Perform initialization tasks that require the controller or other dependencies
        to be fully ready. This helps decouple the GUI construction from the
        controller's state availability.
        """
        try:
            # Prefer hardware_vm if available (post-init),
            # else fallback to controller attrs (bootstrap)
            if hasattr(self.controller, "hardware_vm"):
                active_weight = self.controller.hardware_vm.active_weight_name
                use_openvino = self.controller.hardware_vm.use_openvino
                ov_status = self.controller.hardware_vm.get_openvino_status()
            else:
                active_weight = getattr(self.controller, "active_weight_name", None)
                use_openvino = getattr(self.controller, "use_openvino", False)
                ov_status = getattr(
                    self.controller, "get_openvino_status", lambda: "Desconhecido"
                )()

            self.set_active_weight_in_dropdown(active_weight)
            self.update_openvino_checkbox(use_openvino)
            self.update_openvino_status_display(ov_status)
        except (AttributeError, RuntimeError):
            log.warning("gui.post_init.controller_sync_failed", exc_info=True)

    # --- Weight & Hardware (Phase 4.4 → WeightHardwareManager) ---

    def handle_request_weight_type(self, filepath: str) -> None:
        """Delegates to WeightHardwareManager."""
        self.weight_hardware_manager.handle_request_weight_type(filepath)

    def handle_request_weight_action(self, filepath: str, weight_type: str) -> None:
        """Delegates to WeightHardwareManager."""
        self.weight_hardware_manager.handle_request_weight_action(filepath, weight_type)

    # --- Event bus helpers -------------------------------------------------

    @staticmethod
    def _extract_setting(root: Any, path: tuple[str, ...], default: Any) -> Any:
        current = root
        for attr in path:
            if current is None:
                return default
            current = getattr(current, attr, None)
        return current if current is not None else default

    @staticmethod
    def _deep_merge_dicts(
        base: dict[str, Any],
        override: dict[str, Any],
    ) -> dict[str, Any]:
        """Deep merge two dictionaries. Delegates to ValidationManager."""
        from zebtrack.ui.components.validation_manager import ValidationManager

        return ValidationManager._deep_merge_dicts(base, override)

    # --- Analysis View (Phase 4.4 → AnalysisViewController) ---

    def _cleanup_single_analysis_button(self):
        """Delegates to AnalysisViewController."""
        self.analysis_view_controller.cleanup_single_analysis_button()

    def _reset_analysis_widgets(self) -> None:
        """Delegates to AnalysisViewController."""
        self.analysis_view_controller.reset_analysis_widgets()

    def _initialize_theme(self) -> None:
        """Apply a modern ttkbootstrap theme if the library is available."""
        if ttkb is None:
            log.debug("ui.theme.bootstrap_missing")
            return

        preferred_theme = getattr(self.settings, "ui_theme_name", None) or getattr(
            self.settings, "ui_theme", None
        )
        theme_name = preferred_theme or "cosmo"

        try:
            # Resolving version for logging
            getattr(ttkb, "__version__", "unknown")
            try:
                from importlib.metadata import PackageNotFoundError
                from importlib.metadata import version as _pkg_version

                try:
                    _pkg_version("ttkbootstrap")
                except PackageNotFoundError:
                    log.debug("gui.ttkbootstrap_version.not_found")
            except ImportError:
                log.debug("gui.ttkbootstrap_version_check.suppressed", exc_info=True)

            try:
                self._ttkbootstrap_style = ttkb.Style(theme=theme_name)
            except TypeError:
                # Older versions might require master or behave differently
                try:
                    self._ttkbootstrap_style = ttkb.Style(  # type: ignore[call-arg]
                        theme=theme_name,
                        master=self.root,
                    )
                except Exception as e:
                    log.warning(
                        "ui.theme.bootstrap_failed_internal",
                        theme=theme_name,
                        error=str(e),
                    )
                    raise e  # Re-raise to be caught by outer block

            # Configure theme usage and root background
            active_theme = self._ttkbootstrap_style.theme_use()
            self._ttkbootstrap_theme = active_theme

            frame_bg = self._ttkbootstrap_style.lookup("TFrame", "background")
            if frame_bg:
                self.root.configure(background=frame_bg)

            log.debug("ui.theme.bootstrap_applied", theme=active_theme)

        except (TclError, TypeError, RuntimeError):
            log.error(
                "ui.theme.bootstrap_failed_global",
                theme=theme_name,
                exc_info=True,
                message="Falling back to standard Tkinter theme",
            )
            self._ttkbootstrap_style = None
            self._ttkbootstrap_theme = None
            # Ensure any partial changes don't break standard widgets if possible
            # Standard Tkinter doesn't need explicit cleanup usually

    def _open_global_calibration_window(self):
        with self.controller.global_calibration_session():
            CalibrationDialog(self.root, self.controller)

    def _open_project_calibration_window(self):
        if not getattr(self.controller.project_manager, "project_path", None):
            self.show_warning(
                "Nenhum Projeto",
                "Abra um projeto antes de ajustar a calibração específica.",
            )
            return

        with self.controller.project_calibration_session():
            CalibrationDialog(self.root, self.controller)
        self.update_openvino_checkbox(self.controller.hardware_vm.use_openvino)
        self.set_active_weight_in_dropdown(self.controller.hardware_vm.active_weight_name)
        self.update_openvino_status_display(self.controller.hardware_vm.get_openvino_status())

    # --- Zone Edit Guard (Phase 4.4 → ZoneEditGuard) ---

    def _on_tab_changed(self, event):
        """Handle tab change event. Delegates to ZoneEditGuard."""
        self.zone_edit_guard.on_tab_changed(event)

    def _has_pending_zone_edit(self) -> bool:
        """Delegates to ZoneEditGuard."""
        return self.zone_edit_guard.has_pending_zone_edit()

    def _warn_about_pending_zone_edit(self, *, context: str) -> None:
        """Delegates to ZoneEditGuard."""
        self.zone_edit_guard.warn_about_pending_zone_edit(context=context)

    def _confirm_pending_zone_edit_before_navigation(self, *, context: str) -> bool:
        """Delegates to ZoneEditGuard."""
        return self.zone_edit_guard.confirm_pending_zone_edit_before_navigation(context=context)

    # --- Project Initialization (Phase 4.4 → ProjectInitializer) ---

    def _create_main_control_frame(self):
        """Delegates to ProjectInitializer."""
        self.project_initializer.create_main_control_frame()

    def _on_canvas_configure(self, event):
        """Handle canvas resize events."""
        self.canvas_manager.on_canvas_configure(event)

    def _on_reset_global_config_form_widget(self) -> None:
        """Reset ConfigEditorWidget form fields to reflect current settings object."""
        self._reload_config_editor_values_widget()
        self.show_info(
            "Formulário recarregado",
            "Valores restaurados para refletir as configurações atuais.",
        )

    def _reload_config_editor_values_widget(self) -> None:
        """Reload the config editor with current settings."""
        if self.config_editor_widget and self.settings:
            try:
                # Use model_dump if it's a Pydantic model
                if hasattr(self.settings, "model_dump"):
                    self.config_editor_widget.set_values(self.settings.model_dump())
                else:
                    self.config_editor_widget.set_values(vars(self.settings))
            except (AttributeError, TypeError, ValueError) as e:
                log.error("gui.config_reload_error", error=str(e))

    def _on_roi_rule_change_widget(self, rule: str) -> None:
        """Handle ROI rule change from ConfigEditorWidget."""
        # This widget doesn't need conditional UI updates (unlike the zones tab)
        # But we keep this handler for future extensions
        pass

    def _navigate_to_processing_reports_tab(self) -> None:
        """Delegates to ProjectInitializer."""
        self.project_initializer.navigate_to_processing_reports_tab()

    def _create_project_overview_panel(self, parent: ttk.Frame | None) -> None:
        """Legacy helper preserved for TabBuilder/tests - delegates to WidgetFactory."""
        if parent is None:
            return
        if not self.widget_factory:
            log.warning("gui.project_overview.missing_widget_factory")
            return
        self.widget_factory.create_project_overview_panel(parent)

    def _on_project_overview_tree_double_click(self, event) -> None:
        """Handle double-click events on the overview tree (legacy handler)."""
        del event

        if not self.project_overview_tree:
            return

        item_id = self.project_overview_tree.focus()
        if item_id:
            self.video_selector_manager._on_project_overview_tree_double_click_impl(None)

    def _on_project_overview_right_click(self, event) -> None:
        """Handle right-click events on the overview tree (legacy handler)."""
        tree = self.project_overview_tree
        if not tree or not tree.winfo_exists():
            return

        item_id = tree.identify_row(event.y)
        if item_id:
            self.menu_manager.show_project_overview_context_menu(
                item_id, event.x_root, event.y_root
            )

    def _on_frame_configure(self, event=None):
        """Update scroll region when frame size changes."""
        if self.controls_canvas:
            self.controls_canvas.configure(scrollregion=self.controls_canvas.bbox("all"))

    def _on_canvas_configure_scroll(self, event=None):
        """Update frame width when canvas size changes."""
        if self.controls_canvas and self.controls_canvas_window:
            canvas_width = event.width if event else self.controls_canvas.winfo_width()
            self.controls_canvas.itemconfig(self.controls_canvas_window, width=canvas_width)

    def _bind_mousewheel(self):
        """Bind mouse wheel scrolling to the canvas."""

        def _on_mousewheel(event):
            if self.controls_canvas:
                # For Windows/macOS
                if hasattr(event, "delta"):
                    self.controls_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                # For Linux (Button-4, Button-5)
                elif event.num == 4:
                    self.controls_canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    self.controls_canvas.yview_scroll(1, "units")

        if self.controls_canvas:
            self.controls_canvas.bind("<MouseWheel>", _on_mousewheel)
            # For Linux
            self.controls_canvas.bind("<Button-4>", _on_mousewheel)
            self.controls_canvas.bind("<Button-5>", _on_mousewheel)

    def _recenter_canvas_image(self, canvas_width, canvas_height):
        """Recenter the canvas background image."""
        if not hasattr(self, "_canvas_bg_position"):
            return

        # Safety check: video_display may not exist yet
        if not hasattr(self, "video_display") or not self.video_display:
            return

        # Remove the old image
        self.video_display.canvas.delete("background_image")

        # Center the image in the new canvas size
        center_x = canvas_width // 2
        center_y = canvas_height // 2

        # Update stored position
        self._canvas_bg_position = (center_x, center_y, "center")

        # Create the centered image
        self.video_display.canvas.create_image(
            center_x,
            center_y,
            anchor="center",
            image=self._canvas_bg_image,
            tags="background_image",
        )

    def _on_video_tree_double_click(self, event):
        """Handle double click on video selector."""
        del event  # Event is not used directly
        self.canvas_manager.load_selected_video_frame()

    def _refresh_roi_templates(self, clear_selection: bool = False) -> None:
        """Refresh template list. Delegates to ROITemplateManager."""
        return self.roi_template_manager.refresh_templates(clear_selection)

    def _on_save_roi_template(self) -> None:
        """Save ROI template. Delegates to ROITemplateManager."""
        return self.roi_template_manager.save_template()

    def _format_roi_template_display(self, template: dict[str, Any]) -> str:
        """Format ROI template display. Delegates to ROITemplateManager."""
        return self.roi_template_manager._format_display_name(template)

    def _build_roi_template_identifier(self, template: dict[str, Any]) -> str:
        """Build ROI template identifier. Delegates to ROITemplateManager."""
        return self.roi_template_manager._build_identifier(template)

    def _get_selected_roi_template(self) -> dict[str, Any] | None:
        """Get selected template. Delegates to ROITemplateManager."""
        return self.roi_template_manager.get_selected_template()

    def _get_zone_data_for_active_context(self) -> ZoneData:
        pm = getattr(self.controller, "project_manager", None)
        if pm is None:
            return ZoneData()

        active_video = pm.get_active_zone_video()
        if not active_video:
            pending_video = getattr(self, "pending_single_video_path", None)
            active_video = pending_video

        # v2.3.1: For Live projects, always fallback to global detection_zones
        # since zones are defined once for the entire project, not per-video
        is_live_project = pm.get_project_type() == "live"

        if active_video:
            try:
                # Check for multi-aquarium data first
                if hasattr(pm, "is_multi_aquarium_video") and pm.is_multi_aquarium_video(
                    active_video
                ):
                    multi_data = pm.get_multi_aquarium_zone_data(active_video)
                    if multi_data:
                        return multi_data

                zone_data = pm.get_zone_data(
                    video_path=active_video,
                    fallback_to_global=is_live_project,  # v2.3.1: Fallback for Live projects
                )
            except (KeyError, ValueError, TypeError, FileNotFoundError):
                zone_data = ZoneData()

            if zone_data and (zone_data.polygon or zone_data.roi_polygons):
                return zone_data

        return pm.get_zone_data()

    def _select_roi_template(self, metadata: dict[str, Any]) -> None:
        """Select a template in the dropdown. Delegates to ROITemplateManager."""
        return self.roi_template_manager.select_template_by_metadata(metadata)

    def _show_template_save_dialog(
        self,
        *,
        has_arena: bool,
        has_rois: bool,
        allow_project: bool,
        initial_name: str,
    ) -> dict[str, Any] | None:
        dialog = SaveROITemplateDialog(
            self.root,
            default_name=initial_name,
            has_arena=has_arena,
            has_rois=has_rois,
            allow_project=allow_project,
        )

        if not dialog.result:
            return None

        return dialog.result

    def _on_delete_roi_template(self) -> None:
        """Delete the currently selected template. Delegates to ROITemplateManager."""
        self.roi_template_manager.delete_template()

    def _on_clear_applied_roi_template(self) -> None:
        """Clear template-applied drawings from the active video only."""
        self.roi_template_manager.clear_applied_template_drawings()

    def _on_import_roi_template(self) -> None:
        """Import a template file into the library. Delegates to ROITemplateManager."""
        self.roi_template_manager.import_template()

    def _on_import_and_apply_roi_template(self) -> None:
        """Import a template file and immediately apply it to current video.

        Delegates to DialogManager.
        """
        self.dialog_manager.import_and_apply_roi_template()

    def _update_delete_template_button_state(self) -> None:
        """Update delete button state based on selection. Delegates to ROITemplateManager."""
        return self.roi_template_manager._update_delete_button_state()

    def _on_roi_template_var_changed(self, *args) -> None:
        """Trace callback: Log whenever roi_template_var changes."""
        # We keep this trace as it might be useful for debugging, or we can delegate logging?
        # For now, just delegate update state
        self.roi_template_manager._update_delete_button_state()

    def _on_template_combobox_changed(self, event=None) -> None:
        """Log when template selection changes in combobox."""
        pass

    def _on_apply_roi_template(self) -> None:
        """Apply template. Delegates to ROITemplateManager."""
        self.roi_template_manager.apply_template()
        # Mark zones as dirty so user is warned if they switch videos without clicking "Concluir"
        self._zones_dirty = True

    def _filter_video_tree(self) -> None:
        """Filter video tree based on search text. Delegates to ProjectViewManager."""
        if not hasattr(self, "zone_controls") or not self.zone_controls:
            return
        search_text = self.zone_controls.video_search_var.get()
        self.video_selector_manager._populate_video_selector_tree(filter_text=search_text)

    def _refresh_video_selector_tree(self) -> None:
        """Refresh video selector tree. Delegates to ProjectViewManager."""
        self.video_selector_manager._populate_video_selector_tree(filter_text=None)

    def _on_apply_roi_settings(self, params: dict | None = None) -> None:
        """Apply ROI settings.

        If params are provided (via EventBus), applies them directly.
        If params are None (via legacy UI button), reads from UI variables.
        """
        try:
            # Case 1: Params provided via Event (e.g. from ConfigEditor or EventDispatcher)
            if params:
                if self.controller:
                    self.controller.hardware_vm.update_detector_parameters(params)
                return

            # Case 2: No params (Legacy UI interaction) - Read from StringVars
            self.controller.settings.roi_inclusion_rule = self.roi_inclusion_rule_var.get()
            self.controller.settings.roi_buffer_radius_value = float(
                self.roi_buffer_radius_var.get()
            )
            self.controller.settings.roi_min_bbox_overlap_ratio = float(
                self.roi_overlap_ratio_var.get()
            )

            if self.controller.project_manager.project_path:
                self.controller.project_manager._save_settings_snapshot()

            self.show_info("Sucesso", "Configurações de ROI aplicadas.")

        except ValueError:
            self.show_error("Erro", "Valores inválidos para parâmetros de ROI.")
        except (AttributeError, OSError) as e:
            log.error("gui.apply_roi_settings.error", error=str(e))
            self.show_error("Erro", f"Falha ao aplicar configurações: {e!s}")

    def _update_window_title(self, project_name: str | None = None) -> None:
        """Delegates to ProjectInitializer."""
        self.project_initializer.update_window_title(project_name)

    def _load_project_view(self):
        """Delegates to ProjectInitializer."""
        self.project_initializer.load_project_view()

    def _restore_persisted_project_settings(self, pm):
        """Delegates to ProjectInitializer."""
        self.project_initializer.restore_persisted_project_settings(pm)

    def _initialize_live_components(self, pm):
        """Delegates to ProjectInitializer."""
        self.project_initializer.initialize_live_components(pm)

    def _initialize_prerecorded_components(self, pm):
        """Delegates to ProjectInitializer."""
        self.project_initializer.initialize_prerecorded_components(pm)

    def _check_live_project_calibration(self):
        """Check if Live project needs calibration. Delegates to ValidationManager."""
        return self.validation_manager.check_live_project_calibration()

    def _manage_weights_clicked(self):
        """Delegates to WeightHardwareManager."""
        self.weight_hardware_manager.manage_weights_clicked()

    @public_api
    def setup_interactive_polygon(self, polygon):
        """Delegate interactive polygon setup to EventDispatcher (back-compat shim)."""
        polygon = polygon or []
        polygon_array = np.array(polygon, dtype=float)
        return self.canvas_manager.setup_interactive_polygon(polygon_array)

    def update_zone_listbox(self, zone_data: ZoneData | None = None):
        """Update the zone listbox via CanvasManager (legacy entry point)."""
        return self.canvas_manager.update_zone_listbox(zone_data)

    def apply_pending_readiness_snapshot(
        self,
        *,
        ready_with_trajectory: list,
        ready_with_zones: list,
        arena_only: list,
        without_arena: list,
    ) -> None:
        """Apply the readiness snapshot through ProjectViewManager."""
        return self.video_selector_manager.apply_pending_readiness_snapshot(
            ready_with_trajectory=ready_with_trajectory,
            ready_with_zones=ready_with_zones,
            arena_only=arena_only,
            without_arena=without_arena,
        )

    def _populate_video_selector_tree(self, filter_text: str | None = None) -> None:
        """Populate the video selector tree via ProjectViewManager (legacy shim)."""
        return self.video_selector_manager._populate_video_selector_tree(filter_text)

    def _request_overview_refresh(
        self,
        *,
        reason: str | None = None,
        append_summary: bool = False,
        immediate: bool = False,
    ) -> None:
        """Compat shim that delegates overview refreshes to ProjectViewManager."""
        if append_summary and reason:
            self._pending_overview_status = reason
            self._overview_status_append = True

        # Prefer new public API when available.
        if hasattr(self.video_selector_manager, "request_overview_refresh"):
            return self.video_selector_manager.request_overview_refresh(
                reason=reason,
                force=immediate,
            )

        # Fallback for older extracted method names if still present.
        legacy_handler = getattr(self.video_selector_manager, "_request_overview_refresh", None)
        if legacy_handler:
            return legacy_handler(
                reason=reason,
                append_summary=append_summary,
                immediate=immediate,
            )

        # As a last resort, trigger an immediate full refresh.
        refresh_fn = getattr(self.video_selector_manager, "refresh_project_views", None)
        if refresh_fn:
            return refresh_fn()

    @public_api
    def refresh_project_views(
        self,
        reason: str | None = None,
        *,
        append_summary: bool = False,
        immediate: bool = False,
    ) -> None:
        """Public entry point preserved for orchestrators and tests."""
        return self._request_overview_refresh(
            reason=reason,
            append_summary=append_summary,
            immediate=immediate,
        )

    def _edit_selected_zone_vertices(self) -> None:
        """Delegate zone vertex editing to CanvasManager."""
        return self.canvas_manager.edit_selected_zone_vertices()

    def _rename_selected_roi(self) -> None:
        """Delegate ROI rename workflow to DialogManager."""
        return self.dialog_manager.rename_selected_roi()

    def _remove_selected_roi_confirm(self) -> None:
        """Remove the selected ROI after user confirmation (legacy UI flow)."""
        listbox = None
        if hasattr(self, "zone_listbox") and self.zone_listbox:
            listbox = self.zone_listbox
        elif self.zone_controls and self.zone_controls.zone_listbox:
            listbox = self.zone_controls.zone_listbox

        if not listbox:
            return

        selected = listbox.selection()
        if not selected:
            return

        item = listbox.item(selected[0])
        values = item.get("values") if isinstance(item, dict) else None
        if not values:
            return

        roi_name = str(values[0]).replace("📍 ", "")
        confirm = self.dialog_manager.confirm_remove_roi(roi_name)
        if not confirm:
            return

        zone_data = self._get_zone_data_for_active_context()
        if not zone_data or not getattr(zone_data, "roi_names", None):
            return

        try:
            idx = zone_data.roi_names.index(roi_name)
        except ValueError:
            self.show_error("Erro", "ROI não encontrada")
            return

        zone_data.roi_names = list(zone_data.roi_names)
        zone_data.roi_names.pop(idx)

        if isinstance(zone_data.roi_polygons, list) and idx < len(zone_data.roi_polygons):
            zone_data.roi_polygons.pop(idx)

        roi_colors = getattr(zone_data, "roi_colors", None)
        if isinstance(roi_colors, list) and idx < len(roi_colors):
            roi_colors.pop(idx)

        self.controller.project_manager.save_zone_data(zone_data)
        self.canvas_manager.redraw_zones_from_project_data()

        status_message = f"ROI '{roi_name}' removida com sucesso."
        self.show_info("Sucesso", status_message)
        self.set_status(status_message)
        self._request_overview_refresh(reason=status_message, append_summary=True)

        # Publish dual-path event for observers still listening to Event Bus v2
        if self.event_bus_v2:
            self.event_bus_v2.publish(
                Event(
                    type=UIEvents.ZONES_UPDATED,
                    data={"zone_data": zone_data},
                    source="ApplicationGUI._remove_selected_roi_confirm",
                )
            )

    @public_api
    def update_weights_dropdown(self, weights: list[str]):
        """Delegates to WeightHardwareManager."""
        self.weight_hardware_manager.update_weights_dropdown(weights)

    def set_active_weight_in_dropdown(self, weight_name: str | None):
        """Delegates to WeightHardwareManager."""
        self.weight_hardware_manager.set_active_weight_in_dropdown(weight_name)

    def update_openvino_checkbox(self, enabled: bool):
        """Delegates to WeightHardwareManager."""
        self.weight_hardware_manager.update_openvino_checkbox(enabled)

    def update_openvino_status_display(self, status: str):
        """Delegates to WeightHardwareManager."""
        self.weight_hardware_manager.update_openvino_status_display(status)

    def _refresh_openvino_summary(self):
        """Delegates to WeightHardwareManager."""
        self.weight_hardware_manager._refresh_openvino_summary()

    def _update_active_weight_display(self, weight_name: str):
        """Delegates to WeightHardwareManager."""
        self.weight_hardware_manager._update_active_weight_display(weight_name)

    def update_gpu_hardware_display(self, hardware_summary: dict):
        """Delegates to WeightHardwareManager."""
        self.weight_hardware_manager.update_gpu_hardware_display(hardware_summary)

    def _create_project_workflow(self):
        """Delegates to ProjectInitializer."""
        self.project_initializer.create_project_workflow()

    def _open_project_workflow(self):
        """Delegates to ProjectInitializer."""
        self.project_initializer.open_project_workflow()

    # --- Single Video Workflow (Phase 4.4 → SingleVideoWorkflow) ---

    @public_api
    def _on_analyze_single_video_clicked(self):
        """Delegates to SingleVideoWorkflow."""
        self.single_video_workflow.on_analyze_single_video_clicked()

    @public_api
    def setup_zone_definition_for_single_video(self, video_path: str, config: dict):
        """Delegates to SingleVideoWorkflow."""
        self.single_video_workflow.setup_zone_definition_for_single_video(video_path, config)

    def _on_auto_detect_clicked(self, stabilization_frames: int | str | None = None):
        """Delegates to SingleVideoWorkflow."""
        self.single_video_workflow.on_auto_detect_clicked(stabilization_frames)

    def _clear_interactive_polygon(self):
        """Delegate clearing interactive polygon to CanvasManager."""
        if hasattr(self, "canvas_manager"):
            self.canvas_manager.clear_interactive_polygon()

    def _on_start_single_video_processing_clicked(self):
        """Delegates to SingleVideoWorkflow."""
        self.single_video_workflow._on_start_single_video_processing_clicked()

    def _on_close(self):
        """Delegate the close action to the controller."""
        self.controller.on_close()

    def _join_threads(self):
        """Delegate thread joining to the controller."""
        self.controller.join_threads()

    @public_api
    def set_status(self, text):
        """Update the UI status bar."""
        self.status_var.set(text)

    @public_api
    def show_progress_bar(self):
        """Show the progress bar."""
        if self.analysis_display_widget:
            self.analysis_display_widget.show_progress()

    @public_api
    def update_progress(self, value):
        """Update progress. Delegates to AnalysisDisplay."""
        if self.analysis_display_widget:
            self.analysis_display_widget.update_progress(value)

    @public_api
    def update_idletasks(self):
        """Force the GUI to update, processing pending events."""
        self.root.update_idletasks()

    @public_api
    def hide_progress_bar(self):
        """Hide the progress bar."""
        if self.analysis_display_widget:
            self.analysis_display_widget.hide_progress()

    def _toggle_canvas_view(self):
        """Delegates to AnalysisViewController."""
        self.analysis_view_controller.toggle_canvas_view()

    def _switch_to_analysis_view(self):
        """Delegates to AnalysisViewController."""
        self.analysis_view_controller.switch_to_analysis_view()

    def _switch_to_zones_view(self):
        """Delegates to AnalysisViewController."""
        self.analysis_view_controller.switch_to_zones_view()

    def start_analysis_view_mode(self):
        """Delegates to AnalysisViewController."""
        self.analysis_view_controller.start_analysis_view_mode()

    def stop_analysis_view_mode(self):
        """Delegates to AnalysisViewController."""
        self.analysis_view_controller.stop_analysis_view_mode()

    def update_detection_overlay(self, detections=None, report=None):
        """Delegates to AnalysisViewController."""
        self.analysis_view_controller.update_detection_overlay(detections, report)

    def update_processing_mode(self, report: ProcessingReport | None) -> None:
        """Delegates to AnalysisViewController."""
        self.analysis_view_controller.update_processing_mode(report)

    def update_analysis_profile(self, profile_name: str) -> None:
        """Delegates to AnalysisViewController."""
        self.analysis_view_controller.update_analysis_profile(profile_name)

    def _reset_analysis_controls(self) -> None:
        """Delegates to AnalysisViewController."""
        self.analysis_view_controller.reset_analysis_controls()

    def _build_track_options(self, detections: list[tuple]) -> list[str]:
        """Delegates to AnalysisViewController."""
        return self.analysis_view_controller.build_track_options(detections)

    def _on_track_selection_changed(self, _event=None) -> None:
        """Delegates to AnalysisViewController."""
        self.analysis_view_controller.on_track_selection_changed(_event)

    def update_analysis_progress(self, value, status_text=None):
        """Delegates to AnalysisViewController."""
        self.analysis_view_controller.update_analysis_progress(value, status_text)

    def update_analysis_metadata(self, *, metadata: dict | None) -> None:
        """Delegates to AnalysisViewController."""
        self.analysis_view_controller.update_analysis_metadata(metadata=metadata)

    def update_analysis_task_status(
        self,
        *,
        index: int,
        total: int,
        experiment_id: str | None = None,
        step: str | None = None,
    ) -> None:
        """Delegates to AnalysisViewController."""
        self.analysis_view_controller.update_analysis_task_status(
            index=index,
            total=total,
            experiment_id=experiment_id,
            step=step,
        )

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format time. Delegates to StateSynchronizer."""
        from zebtrack.ui.components.state_synchronizer import StateSynchronizer

        return StateSynchronizer._format_time(seconds)

    @public_api
    def show_error(self, title, message):
        """Show an error message box. Delegates to DialogManager."""
        return self.dialog_manager.show_error(title, message)

    @public_api
    def show_warning(self, title, message):
        """Show a warning message box. Delegates to DialogManager."""
        return self.dialog_manager.show_warning(title, message)

    @public_api
    def show_info(self, title, message):
        """Show an info message box. Delegates to DialogManager."""
        return self.dialog_manager.show_info(title, message)

    @public_api
    def show_pending_videos_dialog(
        self,
        *,
        ready_with_trajectory: list[dict],
        ready_with_zones: list[dict],
        arena_only: list[dict],
        without_arena: list[dict],
    ) -> dict | None:
        """Show pending videos dialog. Delegates to DialogManager."""
        return self.dialog_manager.show_pending_videos_dialog(
            ready_with_trajectory=ready_with_trajectory,
            ready_with_zones=ready_with_zones,
            arena_only=arena_only,
            without_arena=without_arena,
        )

    @public_api
    def ask_ok_cancel(self, title, message):
        """Show a confirmation dialog. Delegates to DialogManager."""
        return self.dialog_manager.ask_ok_cancel(title, message)

    @public_api
    def ask_string(self, title, prompt, initialvalue=None):
        """Show a dialog for string input. Delegates to DialogManager."""
        return self.dialog_manager.ask_string(title, prompt, initialvalue=initialvalue)

    @public_api
    def ask_directory(self, title):
        """Show a dialog to select a directory. Delegates to DialogManager."""
        return self.dialog_manager.ask_directory(title)

    @public_api
    def ask_open_filenames(self, title, filetypes):
        """Show a dialog to select one or more files. Delegates to DialogManager."""
        return self.dialog_manager.ask_open_filenames(title, filetypes)

    @public_api
    def ask_save_filename(self, **options):
        """Show a dialog to select a save file path. Delegates to DialogManager."""
        return self.dialog_manager.ask_save_filename(**options)

    @public_api
    def update_button_state(self, button_name, state):
        """Update the state of a button ('normal' or 'disabled')."""
        if button_name == "start_rec" and self.start_rec_btn is not None:
            self.start_rec_btn.config(state=state)
        elif button_name == "stop_rec" and self.stop_rec_btn is not None:
            self.stop_rec_btn.config(state=state)
        elif button_name == "process_video" and self.process_video_btn is not None:
            self.process_video_btn.config(state=state)
        elif button_name == "cancel_processing" and self.analysis_display_widget:
            if state == "normal":
                self.analysis_display_widget.enable_cancel_button()
            else:
                self.analysis_display_widget.disable_cancel_button()

    @public_api
    def ask_recording_details_unified(self):
        """Show a unified dialog to get day, group, and subject."""
        # Check if it's a live project with the necessary config
        pm = self.controller.project_manager
        if not pm.project_data.get("experiment_days"):
            self.show_error(
                "Error",
                "This project is not configured for live experimental tracking.",
            )
            return None

        dialog = StartRecordingDialog(self.root, pm)
        return dialog.result

    @public_api
    def ask_missing_metadata(self, experiment_id):
        """Show a dialog to get missing metadata from the user."""
        dialog = MissingMetadataDialog(self.root, experiment_id)
        return dialog.result

    # Compatibility layer removed as part of Phase 6 cleanup.
    # All legacy properties have been migrated to direct component access.

    def _load_selected_video_frame(self):
        """Load selected video frame."""
        self.canvas_manager.load_selected_video_frame()

    def _on_zone_right_click(self, event):
        """Handle right click on zone list."""
        self.menu_manager.show_roi_context_menu(event)

    def _on_zone_double_click(self, event):
        """Handle double click on zone list."""
        self.canvas_manager.edit_selected_zone_vertices()

    def _on_save_arena(self):
        """Save arena."""
        self.canvas_manager.save_arena()
        # Mark zones as dirty — saved in memory but not committed via "Concluir"
        self._zones_dirty = True

    def _on_discard_arena(self):
        """Discard arena changes."""
        self.canvas_manager.discard_arena()

    def _create_drawing_buttons(self):
        """Create drawing buttons. Delegates to WidgetFactory."""
        self.widget_factory.create_drawing_buttons()

    def _build_day_title(self, day_value, metadata: dict | None = None) -> str:
        """Shim for validation_manager._build_day_title."""
        return self.validation_manager._build_day_title(day_value, metadata)

    def _format_day_display(self, value) -> str:
        """Shim for validation_manager._format_day_display."""
        return self.validation_manager._format_day_display(value)

    def _render_progress_grid(self):
        """Render the progress grid. Delegates to WidgetFactory."""
        self.widget_factory.render_progress_grid()

    def _on_mousewheel(self, event):
        """Handle mousewheel scrolling."""
        if hasattr(self, "controls_canvas") and self.controls_canvas:
            if event.num == 5 or event.delta < 0:
                self.controls_canvas.yview_scroll(1, "units")
            elif event.num == 4 or event.delta > 0:
                self.controls_canvas.yview_scroll(-1, "units")

    def _refresh_processing_reports_tab(self) -> None:
        """Refresh the processing reports tab."""
        self.reports_tree_manager.refresh_processing_reports_tab()

    def _resolve_processing_reports_video_paths(self, selection=None) -> list[str]:
        """Resolve video paths from processing reports selection."""
        return self.video_selector_manager.resolve_processing_reports_video_paths(selection)

    def _subscribe_zone_component_events(self) -> None:
        """Delegate subscription of zone component events to EventDispatcher."""
        self.event_dispatcher.subscribe_zone_component_events()

    def _update_zone_summary_cards(self, all_videos=None) -> None:
        """Delegate zone summary card updates to ProjectViewManager."""
        self.video_selector_manager.update_zone_summary_cards()

    def _get_zone_summary_helper_text(self) -> str:
        """Delegate helper text retrieval to WidgetFactory."""
        return self.widget_factory.get_zone_summary_helper_text()

    def _handle_project_refresh_requested(self, data: dict) -> None:
        """Handle project refresh request from overview widget."""
        self.video_selector_manager.request_overview_refresh(reason="Atualização manual")

    def _handle_project_video_double_click(self, data: dict) -> None:
        """Handle video double-click from overview widget."""
        item_id = data.get("item_id")
        if item_id:
            self.video_selector_manager.handle_project_overview_double_click(item_id)

    def _handle_project_video_right_click(self, data: dict) -> None:
        """Handle video right-click from overview widget."""
        # We pass explicit coordinates if available
        x = data.get("x")
        y = data.get("y")
        item_id = data.get("item_id")
        if x is not None and y is not None and item_id:
            self.menu_manager.show_project_overview_context_menu(item_id, x, y)

    @property
    def project_overview_tree(self):
        """Access the treeview within the project overview widget."""
        if hasattr(self, "project_overview_widget") and self.project_overview_widget:
            return self.project_overview_widget.project_overview_tree
        return None

    def update_reports_tree(self):
        """Delegate to ProjectViewManager to update the reports tree."""
        if self.reports_tree_manager:
            self.reports_tree_manager.update_reports_tree()

    def get_current_detector_parameters(self) -> dict:
        """Delegate to controller to get current detector parameters."""
        if self.controller:
            return self.controller.hardware_vm.get_current_detector_parameters()
        return {}

    def publish_video_hierarchy_snapshot(self, snapshot: list):
        """Delegate event publishing to EventBusV2."""
        if self.event_bus_v2:
            self.event_bus_v2.publish(
                Event(
                    type=UIEvents.VIDEO_HIERARCHY_SNAPSHOT_UPDATED,
                    data={"snapshot": snapshot},
                    source="ApplicationGUI.publish_video_hierarchy_snapshot",
                )
            )

    @public_api
    def publish_event(self, event_name: str, data: dict | None = None) -> bool:
        """Publish an event via the event dispatcher.

        Args:
            event_name: Name of the event to publish
            data: Optional event payload

        Returns:
            True if event was published successfully
        """
        return self.event_dispatcher.publish_event(event_name, data)

    # --- Legacy Methods (Shim Layer for Components) ---
    # These methods delegate to the appropriate managers to support components
    # that still call them on the GUI object.

    def _refresh_zone_indicators(self):
        """Delegate to canvas manager to redraw zones."""
        if hasattr(self, "canvas_manager"):
            self.canvas_manager.redraw_zones_from_project_data()

    def _enable_roi_button_if_arena_exists(self):
        """Delegate to canvas manager to update ROI button state."""
        if hasattr(self, "canvas_manager"):
            self.canvas_manager.update_roi_button_state()

    def _maybe_offer_zone_reuse(self, video_path):
        """Delegate to dialog manager to offer zone reuse."""
        if hasattr(self, "dialog_manager"):
            self.dialog_manager.offer_zone_reuse(video_path)

    def _on_handle_press(self, event, handle_index):
        """Delegate to canvas event handler."""
        if hasattr(self, "canvas_manager") and self.canvas_manager.event_handler:
            self.canvas_manager.event_handler.on_handle_press(event, handle_index)

    def _on_handle_drag(self, event):
        """Delegate to canvas event handler."""
        if hasattr(self, "canvas_manager") and self.canvas_manager.event_handler:
            self.canvas_manager.event_handler.on_handle_drag(event)

    def _on_handle_release(self, event):
        """Delegate to canvas event handler."""
        if hasattr(self, "canvas_manager") and self.canvas_manager.event_handler:
            self.canvas_manager.event_handler.on_handle_release(event)


if __name__ == "__main__":
    # Using print is fine here as it's for direct execution feedback
    print("Este arquivo deve ser importado, não executado diretamente.")
    print("Execute o script principal da aplicação para iniciar o Zebtrack.")

    def _get_zone_data_for_active_context(self) -> ZoneData:
        """
        Retrieve the ZoneData for the current context (active project).

        This method is a shim to support components extracted from the God Object
        (like CanvasManager) that expect this method to exist on the GUI.
        """
        if self.project_manager:
            return self.project_manager.get_zone_data()
        return ZoneData()
