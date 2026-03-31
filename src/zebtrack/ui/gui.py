"""Main graphical user interface (GUI) module for the Zebtrack application."""

from __future__ import annotations

import tkinter as tk
from dataclasses import is_dataclass
from tkinter import (
    BooleanVar,
    Button,
    Label,
    Menu,
    StringVar,
    TclError,
    messagebox,
    ttk,
)
from tkinter import font as tkfont
from typing import TYPE_CHECKING, Any, cast

import structlog

try:
    import ttkbootstrap as ttkb
except ImportError:  # pragma: no cover - optional dependency fallback
    ttkb = cast(Any, None)

# Import custom modules
from zebtrack.core.services.zone_context_service import ZoneContextService
from zebtrack.core.video.processing_mode import ProcessingMode
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
    StartRecordingDialog,
)
from zebtrack.ui.event_bus_v2 import EventBusV2, UIEvents
from zebtrack.ui.ui_coordinator import UICoordinator

if TYPE_CHECKING:
    from zebtrack.core.project.project_manager import ProjectManager
    from zebtrack.core.state_manager import StateManager
    from zebtrack.settings import Settings

log = structlog.get_logger()


def _payload_get(payload: Any, key: str, default=None):
    if isinstance(payload, dict):
        return payload.get(key, default)
    if is_dataclass(payload) and not isinstance(payload, type):
        return getattr(payload, key, default)
    return default


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
        root: tk.Tk,
        controller: Any,
        event_bus: EventBusV2 | None = None,
        settings_obj: Settings | None = None,
        project_manager: ProjectManager | None = None,
        state_manager: StateManager | None = None,
    ):
        """Initialize the ApplicationGUI."""
        self.root = root
        self.controller = controller
        self.event_bus = event_bus
        # Backward-compat alias expected by multiple UI components
        self.event_bus_v2 = event_bus
        self.settings = settings_obj
        self._state_manager = state_manager
        # Use injected project_manager or fallback to controller (legacy)
        self.project_manager = project_manager or getattr(controller, "project_manager", None)
        self._zone_context_service = ZoneContextService(project_manager=self.project_manager)
        # Subscribe to VideoProcessingService events (v2.2 UI decoupling)
        if self.event_bus:

            def _on_error_occurred(data: Any) -> None:
                self.root.after(
                    0,
                    lambda: self.dialog_manager.show_error(
                        _payload_get(data, "title", "Erro"),
                        _payload_get(data, "message", "Ocorreu um erro desconhecido."),
                    ),
                )

            self.event_bus.subscribe(UIEvents.ERROR_OCCURRED, _on_error_occurred)

        self.root.title("DRerio LogAI")
        self.root.protocol("WM_DELETE_WINDOW", lambda: self.controller.on_close())

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
        self.canvas_manager = CanvasManager(
            self,
            event_bus_v2=self.event_bus,
            zone_context_service=self._zone_context_service,
        )
        self.state_synchronizer = StateSynchronizer(self, state_manager=self._state_manager)
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
        self.dialog_manager = DialogManager(
            self,
            event_bus_v2=self.event_bus,
            zone_context_service=self._zone_context_service,
        )
        self.widget_factory = WidgetFactory(self, settings_obj=self.settings)
        self.reports_tree_manager = ReportsTreeManager(self, event_bus_v2=self.event_bus)
        self.video_selector_manager = VideoSelectorTreeManager(self, event_bus_v2=self.event_bus)
        # Backward-compat alias used by shims and tests
        self.project_view_manager = self.video_selector_manager

        # Phase 2.5: Initialize UI Coordinator (Mediator)
        # event_bus is required for UICoordinator — narrowing for type checker
        _eb = self.event_bus
        assert _eb is not None, "UICoordinator requires an EventBusV2 instance"
        self.ui_coordinator = UICoordinator(
            event_bus=_eb,
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
        self.polygon_drawing_service = PolygonDrawingService(event_bus_v2=self.event_bus)

        # Phase 4 components
        self.roi_template_manager = ROITemplateManager(
            self.project_manager, self, event_bus_v2=self.event_bus
        )

        # Phase 5 components
        self.tab_builder = TabBuilder(self)

        # Phase 5 builders (zone control widgets, buttons, panels)
        self.zone_control_builder = ZoneControlBuilder(self, event_bus_v2=self.event_bus)
        self.button_factory = ButtonFactory()
        self.panel_builder = PanelBuilder()

        # Phase 6 components (extracted from gui.py — Phase 4.4 decomposition)
        self.analysis_view_controller = AnalysisViewController(self)
        self.project_initializer = ProjectInitializer(self)
        self.single_video_workflow = SingleVideoWorkflow(
            self, zone_context_service=self._zone_context_service
        )
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
        self._event_bus_handlers: dict[str, Any] = {}
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
            log.info("gui.init.event_bus_setup_complete")
        else:
            log.warning("gui.init.no_event_bus")

        # Subscribe to StateManager state changes for reactive UI updates
        self.state_synchronizer.subscribe_to_state_changes()

    def _post_init(self, _retries: int = 0) -> None:
        """
        Perform initialization tasks that require the controller or other dependencies
        to be fully ready. This helps decouple the GUI construction from the
        controller's state availability.
        """
        try:
            if not self.root.winfo_exists():
                log.debug("gui.post_init.root_unavailable")
                return
        except TclError:
            log.debug("gui.post_init.root_destroyed")
            return

        # If the controller is a LazyRef and not yet resolved, retry later
        if hasattr(self.controller, "is_resolved") and not self.controller.is_resolved:
            if _retries < 20:  # Retry up to 20 times (2 seconds total)
                try:
                    self.root.after(100, lambda: self._post_init(_retries + 1))
                except TclError:
                    log.debug("gui.post_init.retry_skipped_root_destroyed")
                return
            log.warning("gui.post_init.timeout", retries=_retries)
            return

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

            self.weight_hardware_manager.set_active_weight_in_dropdown(active_weight)
            self.weight_hardware_manager.update_openvino_checkbox(use_openvino)
            self.weight_hardware_manager.update_openvino_status_display(ov_status)
        except (AttributeError, RuntimeError):
            log.warning("gui.post_init.controller_sync_failed", exc_info=True)

    # --- Event bus helpers -------------------------------------------------

    @staticmethod
    def _extract_setting(root: Any, path: tuple[str, ...], default: Any) -> Any:
        current = root
        for attr in path:
            if current is None:
                return default
            current = getattr(current, attr, None)
        return current if current is not None else default

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
            self.dialog_manager.show_warning(
                "Nenhum Projeto",
                "Abra um projeto antes de ajustar a calibração específica.",
            )
            return

        with self.controller.project_calibration_session():
            CalibrationDialog(self.root, self.controller)
        self.weight_hardware_manager.update_openvino_checkbox(
            self.controller.hardware_vm.use_openvino
        )
        self.weight_hardware_manager.set_active_weight_in_dropdown(
            self.controller.hardware_vm.active_weight_name
        )
        self.weight_hardware_manager.update_openvino_status_display(
            self.controller.hardware_vm.get_openvino_status()
        )

    def _on_reset_global_config_form_widget(self) -> None:
        """Reset ConfigEditorWidget form fields to reflect current settings object."""
        self._reload_config_editor_values_widget()
        self.dialog_manager.show_info(
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

    def _on_roi_template_var_changed(self, *args) -> None:
        """Trace callback: Log whenever roi_template_var changes."""
        # We keep this trace as it might be useful for debugging, or we can delegate logging?
        # For now, just delegate update state
        self.roi_template_manager._update_delete_button_state()

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

    def _on_apply_roi_settings(self, params: dict | None = None) -> None:
        """Apply ROI settings. Delegates to EventBusV2 / hardware ViewModel.

        Kept as thin stub for backward compatibility with tests.
        """
        if params and self.controller:
            self.controller.hardware_vm.update_detector_parameters(params)

    def _remove_selected_roi_confirm(self) -> None:
        """Remove the selected ROI after user confirmation.

        Delegates to canvas_manager.remove_selected_roi() (modern path).
        Kept as thin stub for backward compatibility with tests.
        """
        if self.canvas_manager:
            self.canvas_manager.remove_selected_roi()

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

    @public_api
    def show_info(self, title: str, message: str) -> None:
        """Show an informational dialog."""
        messagebox.showinfo(title, message)

    @public_api
    def show_warning(self, title: str, message: str) -> None:
        """Show a warning dialog."""
        messagebox.showwarning(title, message)

    @public_api
    def show_error(self, title: str, message: str) -> None:
        """Show an error dialog."""
        messagebox.showerror(title, message)

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
            self.dialog_manager.show_error(
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

    def _on_save_arena(self):
        """Save arena."""
        self.canvas_manager.save_arena()
        # Mark zones as dirty — saved in memory but not committed via "Concluir"
        self._zones_dirty = True

    def _on_mousewheel(self, event):
        """Handle mousewheel scrolling."""
        if hasattr(self, "controls_canvas") and self.controls_canvas:
            if event.num == 5 or event.delta < 0:
                self.controls_canvas.yview_scroll(1, "units")
            elif event.num == 4 or event.delta > 0:
                self.controls_canvas.yview_scroll(-1, "units")

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

    def get_current_detector_parameters(self) -> dict:
        """Delegate to controller to get current detector parameters."""
        if self.controller:
            return self.controller.hardware_vm.get_current_detector_parameters()
        return {}
