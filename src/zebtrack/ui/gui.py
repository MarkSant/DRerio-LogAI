"""Este módulo define a interface gráfica principal (GUI) para a aplicação Zebtrack."""

import hashlib
import os
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path
from tkinter import (
    BooleanVar,
    Button,
    Frame,
    Label,
    Menu,
    StringVar,
    ttk,
)
from tkinter import font as tkfont
from typing import Any

import structlog

try:
    import ttkbootstrap as ttkb
except ImportError:  # pragma: no cover - optional dependency fallback
    ttkb = None

# Import custom modules
from zebtrack.core.detector import ZoneData
from zebtrack.core.processing_mode import ProcessingMode, ProcessingReport
from zebtrack.io.camera import Camera
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
    ProjectViewManager,
    ROITemplateManager,
    StateSynchronizer,
    TabBuilder,
    ValidationManager,
    WidgetFactory,
)
from zebtrack.ui.decorators import public_api
from zebtrack.ui.dialogs import (
    CalibrationDialog,
    MissingMetadataDialog,
    SaveROITemplateDialog,
    StartRecordingDialog,
)
from zebtrack.ui.event_bus import EventBus
from zebtrack.ui.event_bus_v2 import Event, EventBusV2, UIEvents
from zebtrack.ui.events import Events
from zebtrack.ui.ui_coordinator import UICoordinator
from zebtrack.ui.window_utils import (
    reset_geometry_if_not_maximized,
)

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
    """A classe principal que gerencia a interface gráfica (a "Visão")."""

    DEFAULT_CANVAS_WIDTH = 800
    DEFAULT_CANVAS_HEIGHT = 600

    def __init__(self, root, controller, event_bus: EventBus | None = None, settings_obj=None):
        """Inicializa a ApplicationGUI."""
        self.root = root
        self.controller = controller
        self.event_bus = event_bus
        self.settings = settings_obj
        self._event_bus_after_id: int | None = None
        self._event_bus_poll_interval_ms = 50
        self._event_bus_handlers: dict[str, Callable[[Any], None]] = {}

        # Initialize Event Bus V2 for Event-Driven Architecture (v4.0)
        self.event_bus_v2 = EventBusV2()

        self.root.title("DRerio LogAI")
        self.root.protocol("WM_DELETE_WINDOW", self.controller.on_close)

        self._ttkbootstrap_style = None
        self._ttkbootstrap_theme = None
        self._initialize_theme()

        # Initialize state variables before components
        self.notebook = None
        self.welcome_frame = None
        self.main_controls_frame = None
        self.zone_tab_frame = None
        self.analysis_tab_frame = None

        # Initialize component managers (extracted from God Object)
        # Phase 1 components
        self.menu_manager = MenuManager(self)
        self.canvas_manager = CanvasManager(self, event_bus_v2=self.event_bus_v2)
        self.state_synchronizer = StateSynchronizer(self)
        self.event_dispatcher = EventDispatcher(self)

        # Phase 2 components (with dependency injection)
        self.validation_manager = ValidationManager(self, settings_obj=self.settings)
        self.dialog_manager = DialogManager(self, event_bus_v2=self.event_bus_v2)
        self.widget_factory = WidgetFactory(self, settings_obj=self.settings)
        self.project_view_manager = ProjectViewManager(self, event_bus_v2=self.event_bus_v2)

        # Phase 2.5: Initialize UI Coordinator (Mediator)
        self.ui_coordinator = UICoordinator(
            event_bus=self.event_bus_v2,
            canvas_manager=self.canvas_manager,
            validation_manager=self.validation_manager,
            project_view_manager=self.project_view_manager,
            dialog_manager=self.dialog_manager,
            state_synchronizer=self.state_synchronizer,
            root=self.root,
        )

        # Phase 3 components
        self.drawing_state_manager = DrawingStateManager()
        self.polygon_drawing_service = PolygonDrawingService(event_bus_v2=self.event_bus_v2)

        # Phase 4 components
        self.roi_template_manager = ROITemplateManager(
            self.controller.project_manager, self, event_bus_v2=self.event_bus_v2
        )

        # Phase 5 components
        self.tab_builder = TabBuilder(self)

        # Phase 5 builders (zone control widgets, buttons, panels)
        self.zone_control_builder = ZoneControlBuilder(self, event_bus_v2=self.event_bus_v2)
        self.button_factory = ButtonFactory()
        self.panel_builder = PanelBuilder()

        # Create menu bar
        self.menu_manager.create_menu_bar()

        # Dynamic widgets / state variables
        self.zone_summary_frame: ttk.LabelFrame | None = None
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
        self.pending_single_video_path = None
        self.pending_single_video_config = None
        self.start_single_analysis_btn = None
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
            value=(
                self.controller.settings.roi_inclusion_rule
                if self.controller.settings
                else "bbox_intersects"
            )
        )
        self.roi_buffer_radius_var = StringVar(
            value=str(
                self.controller.settings.roi_buffer_radius_value
                if self.controller.settings
                else 0.5
            )
        )
        self.roi_overlap_ratio_var = StringVar(
            value=str(
                self.controller.settings.roi_min_bbox_overlap_ratio
                if self.controller.settings
                else 0.10
            )
        )
        self.roi_template_var = StringVar(value="")
        # Add trace to log all changes to template var
        self.roi_template_var.trace_add("write", self._on_roi_template_var_changed)
        self._roi_templates_cache: list[dict[str, Any]] = []
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
        self.analysis_video_label: Label | None = None

        # User options
        self.processing_interval_var = StringVar(
            value=str(
                self.controller.settings.video_processing.processing_interval
                if self.controller.settings
                else 10
            )
        )
        self.show_preview_var = BooleanVar(value=True)

        # New frame interval controls (defaults to 10 as per requirements)
        self.analysis_interval_var = StringVar(value="10")
        self.display_interval_var = StringVar(value="10")

        # View toggle state for analysis/zone switching
        self.canvas_view_mode = "zones"  # "zones" or "analysis"
        self.analysis_active = False
        # toggle_view_btn is now a @property that delegates to zone_controls
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
        self.save_arena_btn = None
        self.discard_arena_btn = None
        # interactive_buttons_frame is now a @property that delegates to zone_controls

        # Zone tab video selector state
        # video_selector_tree is now a @property that delegates to zone_controls
        self.video_search_var = None
        self._video_selector_filter = ""
        self._pending_readiness_snapshot = {}

        # Project overview widgets/state
        self.project_overview_frame = None
        self.project_overview_widget: ProjectOverviewWidget | None = None
        # Backward compatibility - delegate to widget
        self._project_status_containers = {}
        self._overview_refresh_job = None
        self._pending_overview_status = None
        self._overview_status_append = False
        self._last_overview_counts = {}
        self._overview_video_index: dict[str, dict] = {}
        self._overview_context_menu: Menu | None = None
        self._overview_menu_font: tkfont.Font | None = None

        # Arduino dashboard widget (live projects)
        self.arduino_dashboard_widget: ArduinoDashboardWidget | None = None
        self.external_trigger_notice_var = StringVar(value="")
        self.external_trigger_notice_label = None
        self._external_notice_default_bg = None
        self._external_notice_default_fg = None

        self.set_active_weight_in_dropdown(self.controller.active_weight_name)
        self.update_openvino_checkbox(self.controller.use_openvino)
        self.update_openvino_status_display(self.controller.get_openvino_status())

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

    def _cleanup_single_analysis_button(self):
        """Destroys the single analysis button if it exists."""
        if (
            hasattr(self, "start_single_analysis_btn")
            and self.start_single_analysis_btn is not None
        ):
            if self.start_single_analysis_btn.winfo_exists():
                self.start_single_analysis_btn.destroy()
            self.start_single_analysis_btn = None

        zone_controls = getattr(self, "zone_controls", None)
        if zone_controls:
            try:
                zone_controls.hide_single_analysis_options()
            except Exception:
                pass

    def _reset_analysis_widgets(self) -> None:
        """Encapsula a limpeza e destruição de widgets da aba de análise."""
        # Break the cleanup into smaller helpers to reduce cognitive complexity
        self.state_synchronizer._reset_analysis_media()
        self.state_synchronizer._reset_analysis_progress_and_metadata()
        self.state_synchronizer._reset_roi_and_visual_frames()
        self.state_synchronizer._destroy_notebook_and_main_controls()
        self.analysis_tab_frame = None

    def _initialize_theme(self) -> None:
        """Apply a modern ttkbootstrap theme if the library is available."""
        if ttkb is None:
            log.debug("ui.theme.bootstrap_missing")
            return

        preferred_theme = getattr(self.settings, "ui_theme_name", None) or getattr(
            self.settings, "ui_theme", None
        )
        theme_name = preferred_theme or "cosmo"

        # ttkbootstrap changed its API in some versions and may no longer accept
        # the `master` keyword in Style.__init__.
        #
        # Behaviour:
        # - Older ttkbootstrap accepted `master=self.root` in Style(...)
        # - Newer releases removed that kwarg and raise TypeError if present
        #
        # Strategy: try the call that includes `master` first (compatible with
        # older ttkbootstrap), and on TypeError retry without `master`. This
        # keeps the code compatible across multiple installed versions. If you
        # prefer to enforce a single supported ttkbootstrap version, pin an
        # appropriate range in `pyproject.toml` (e.g. "ttkbootstrap~=1.1"),
        # and remove the fallback.
        #
        # We also log the installed ttkbootstrap version when falling back so
        # maintainers can identify mismatches in CI or user environments.
        # Resolve installed ttkbootstrap version for better logging. Try
        # importlib.metadata first (Python 3.8+), fallback to pkg_resources if
        # importlib.metadata is not available or package metadata is missing.
        # Detect installed ttkbootstrap version without importing pkg_resources
        # to avoid triggering setuptools/pkg_resources deprecation warnings.
        ttk_version = getattr(ttkb, "__version__", None)
        try:
            from importlib.metadata import PackageNotFoundError
            from importlib.metadata import version as _pkg_version

            try:
                ttk_version = _pkg_version("ttkbootstrap")
            except PackageNotFoundError:
                # leave ttk_version as ttkb.__version__ if present
                pass
        except Exception:
            # importlib.metadata not available or failed; keep ttkb.__version__
            pass

        if not ttk_version:
            ttk_version = "unknown"

        try:
            self._ttkbootstrap_style = ttkb.Style(theme=theme_name, master=self.root)
        except TypeError:
            # Older/newer mismatch: try without the master kwarg
            try:
                self._ttkbootstrap_style = ttkb.Style(theme=theme_name)
                log.warning(
                    "ui.theme.bootstrap_master_removed",
                    message=(
                        "ttkbootstrap.Style no longer accepts 'master'; "
                        "initialized Style without master keyword"
                    ),
                    ttkbootstrap_version=ttk_version,
                    theme=theme_name,
                )
            except Exception:
                log.warning(
                    "ui.theme.bootstrap_failed",
                    theme=theme_name,
                    exc_info=True,
                )
                self._ttkbootstrap_style = None
                self._ttkbootstrap_theme = None
                return
        except Exception:
            log.warning(
                "ui.theme.bootstrap_failed",
                theme=theme_name,
                exc_info=True,
            )
            self._ttkbootstrap_style = None
            self._ttkbootstrap_theme = None
            return

        # If we get here, _ttkbootstrap_style is set. Configure theme usage and
        # root background if the theme provides a frame background color.
        try:
            active_theme = self._ttkbootstrap_style.theme_use()
            self._ttkbootstrap_theme = active_theme

            frame_bg = self._ttkbootstrap_style.lookup("TFrame", "background")
            if frame_bg:
                self.root.configure(background=frame_bg)

            log.debug("ui.theme.bootstrap_applied", theme=active_theme)
        except Exception:
            # If anything goes wrong after creating the Style instance, log and
            # clear the style references so callers can fall back to ttk.
            log.warning(
                "ui.theme.bootstrap_failed_post_init",
                theme=theme_name,
                exc_info=True,
            )
            self._ttkbootstrap_style = None
            self._ttkbootstrap_theme = None

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
        self.update_openvino_checkbox(self.controller.use_openvino)
        self.set_active_weight_in_dropdown(self.controller.active_weight_name)
        self.update_openvino_status_display(self.controller.get_openvino_status())

    def _on_tab_changed(self, event):
        """
        Handle tab change event to ensure analysis overlay is hidden.

        Only shows overlay when on analysis tab.
        """
        if not self.notebook:
            return

        current_tab = self.notebook.select()
        analysis_tab_id = str(self.analysis_tab_frame) if self.analysis_tab_frame else ""

        if self.analysis_active:
            self.canvas_view_mode = (
                "analysis" if analysis_tab_id and current_tab == analysis_tab_id else "zones"
            )
            if self.toggle_view_btn:
                if current_tab == analysis_tab_id:
                    self.toggle_view_btn.config(text="Ver Configuração de Zonas")
                else:
                    self.toggle_view_btn.config(text="Ver Análise em Progresso")

    def _create_main_control_frame(self):
        """Create the main UI with tabs for controlling the app."""
        if self.welcome_frame:
            self.welcome_frame.destroy()
        reset_geometry_if_not_maximized(self.root)

        self.notebook = ttk.Notebook(self.root, style="Zebtrack.TNotebook")
        self.notebook.pack(expand=True, fill="both", padx=5, pady=5)

        # Bind tab change event to hide analysis overlay when switching tabs
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # Create the tabs
        self.tab_builder.build_main_controls_tab()
        if self.controller.project_manager.get_project_type() == "live":
            self.widget_factory.create_progress_grid_tab()
        self.tab_builder.build_zone_tab()
        self.tab_builder.build_processing_reports_tab()  # New unified tab
        self.tab_builder.build_analysis_tab()
        self.tab_builder.build_configuration_tab()

        # Status frame below the notebook
        project_type_str = self.controller.project_manager.get_project_type()
        if project_type_str == "live":
            project_type_display = "Ao Vivo"
        elif project_type_str == "pre-recorded":
            project_type_display = "Pré-gravado"
        else:
            project_type_display = project_type_str

        status_text = (
            f"Projeto: {self.controller.project_manager.get_project_name()} "
            f"({project_type_display})"
        )
        self.status_var.set(status_text)
        status_frame = Frame(self.root)
        status_frame.pack(pady=5, fill="x", padx=10, side="bottom")
        Label(status_frame, textvariable=self.status_var).pack()

        # Ensure analysis UI starts hidden
        self.hide_progress_bar()

    def _on_reset_global_config_form_widget(self) -> None:
        """Reset ConfigEditorWidget form fields to reflect current settings object."""
        self._reload_config_editor_values_widget()
        self.show_info(
            "Formulário recarregado",
            "Valores restaurados para refletir as configurações atuais.",
        )

    def _on_roi_rule_change_widget(self, rule: str) -> None:
        """Handle ROI rule change from ConfigEditorWidget."""
        # This widget doesn't need conditional UI updates (unlike the zones tab)
        # But we keep this handler for future extensions
        pass

    def _navigate_to_processing_reports_tab(self) -> None:
        """Navigate to the Processing and Reports tab."""
        if not self.notebook:
            return

        # Find the index of the Processing and Reports tab
        tab_count = self.notebook.index("end")
        for i in range(tab_count):
            tab_text = self.notebook.tab(i, "text")
            if "Processamento e Relatórios" in tab_text:
                self.notebook.select(i)
                return

        log.warning("gui.navigate.processing_reports_tab_not_found")

    def _create_project_overview_panel(self, parent: ttk.Frame | None) -> None:
        """Legacy helper preserved for TabBuilder/tests – delegates to WidgetFactory."""
        if parent is None:
            return
        if not self.widget_factory:
            log.warning("gui.project_overview.missing_widget_factory")
            return
        return self.widget_factory.create_project_overview_panel(parent)

    def _on_project_overview_tree_double_click(self, event) -> None:
        """Handle double-click events on the overview tree (legacy handler)."""
        del event

        if not self.project_overview_tree:
            return

        item_id = self.project_overview_tree.focus()
        if item_id:
            self._on_project_overview_tree_double_click_impl(item_id)

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

            self.controls_canvas.configure(scrollregion=self.controls_canvas.bbox("all"))

    

        def _on_canvas_configure_scroll(self, event=None):

            """Update frame width when canvas size changes."""

            canvas_width = event.width if event else self.controls_canvas.winfo_width()

            self.controls_canvas.itemconfig(self.controls_canvas_window, width=canvas_width)

    

        def _bind_mousewheel(self):

            """Bind mouse wheel scrolling to the canvas."""

    

            def _on_mousewheel(event):

                self.controls_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    

            self.controls_canvas.bind("<MouseWheel>", _on_mousewheel)

            # For Linux

            self.controls_canvas.bind(

                "<Button-4>", lambda e: self.controls_canvas.yview_scroll(-1, "units")

            )

            self.controls_canvas.bind(

                "<Button-5>", lambda e: self.controls_canvas.yview_scroll(1, "units")

            )

    

            def _recenter_canvas_image(self, canvas_width, canvas_height):

    

                """Recenter the canvas background image."""

    

                if not hasattr(self, "_canvas_bg_position"):

    

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
        del event  # Evento não é utilizado diretamente
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

        if active_video:
            try:
                zone_data = pm.get_zone_data(
                    video_path=active_video,
                    fallback_to_global=False,
                )
            except Exception:
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
        return self.roi_template_manager.delete_template()

    def _on_import_roi_template(self) -> None:
        """Import a template file into the library. Delegates to ROITemplateManager."""
        return self.roi_template_manager.import_template()

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
        return self.roi_template_manager.apply_template()




    def _update_window_title(self, project_name: str | None = None) -> None:
        """Update the window title with the project name."""
        base_title = "DRerio LogAI"
        if project_name:
            self.root.title(f"{base_title} - {project_name}")
        else:
            self.root.title(base_title)

    def _load_project_view(self):
        """
        Transitions from the welcome screen to the main control view.

        Initializes the detector with the appropriate plugin.
        """
        # Reset analysis display state from single video workflow
        self.hide_progress_bar()
        self.analysis_status_var.set("Nenhuma análise em andamento.")
        if self.analysis_display_widget and self.analysis_display_widget.video_label:
            try:
                self.analysis_display_widget.video_label.configure(image="")
                self._analysis_overlay_image = None
            except Exception:
                pass

        pm = self.controller.project_manager

        # Update window title with project name
        try:
            project_name = pm.get_project_name() if hasattr(pm, "get_project_name") else None
            self._update_window_title(project_name)
        except Exception:
            pass  # Keep default title if name unavailable

        # Load persisted user preferences if present
        if pm.get_project_type() == "pre-recorded":
            if pm.project_data.get("last_processing_interval") is not None:
                try:
                    self.processing_interval_var.set(
                        str(int(pm.project_data["last_processing_interval"]))
                    )
                except (ValueError, TypeError):
                    pass
            if pm.project_data.get("last_show_preview") is not None:
                try:
                    self.show_preview_var.set(
                        bool(pm.project_data["last_show_preview"])  # type: ignore[arg-type]
                    )
                except Exception:
                    pass

            # Restore analysis and display intervals
            if pm.project_data.get("analysis_interval_frames") is not None:
                try:
                    self.analysis_interval_var.set(
                        str(int(pm.project_data["analysis_interval_frames"]))
                    )
                except (ValueError, TypeError):
                    pass
            if pm.project_data.get("display_interval_frames") is not None:
                try:
                    self.display_interval_var.set(
                        str(int(pm.project_data["display_interval_frames"]))
                    )
                except (ValueError, TypeError):
                    pass

        self._create_main_control_frame()

        project_type = pm.get_project_type()
        if project_type == "live":
            # Initial rendering of the progress grid
            self.root.after(100, self._render_progress_grid)

            # Only attempt to connect if a port is configured from the dialog
            if self.controller.settings and self.controller.settings.arduino.port:
                if not self.controller.arduino.connect():
                    self.show_warning(
                        "Aviso do Arduino",
                        f"Não foi possível conectar ao Arduino na porta "
                        f"{self.controller.settings.arduino.port}. Executando em modo offline.",
                    )
            try:
                # ✅ Use camera_index from project_data (saved by wizard)
                pm = self.controller.project_manager
                camera_index = pm.project_data.get("camera_index", 0)

                log.info(
                    "gui.project_loading.live_camera_setup",
                    camera_index=camera_index,
                    project_name=pm.get_project_name(),
                )

                # Create temporary settings with correct camera index
                temp_settings = self.controller.settings.model_copy(deep=True)
                temp_settings.camera.index = camera_index

                # Initialize camera with modified settings
                self.controller.camera = Camera(settings_obj=temp_settings)

                self.controller.active_frame_source = self.controller.camera
                self.controller.detector.update_scaling(
                    self.controller.camera.actual_width,
                    self.controller.camera.actual_height,
                )
            except OSError as e:
                self.show_error("Erro na Câmera", str(e))
                self.widget_factory.create_welcome_frame()
                return
        elif project_type == "pre-recorded":
            self.update_reports_tree()

            if self.event_bus_v2:
                self.event_bus_v2.publish(Event(
                    type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
                    data={'filter_text': None},
                    source='GUI._load_project_view'
                ))

            ready_message = f"Projeto: {pm.get_project_name()} - Pronto."
            self.set_status(ready_message)
            self._request_overview_refresh(reason=ready_message, append_summary=True)

        if project_type == "live":
            # Auto-calibration for Live projects when no zones are defined
            self.root.after(1000, self._check_live_project_calibration)

    def _check_live_project_calibration(self):
        """Check if Live project needs calibration. Delegates to ValidationManager."""
        return self.validation_manager.check_live_project_calibration()

    def _manage_weights_clicked(self):
        """Open the weight management dialog."""
        self.event_dispatcher.publish_event(Events.MODEL_MANAGE_WEIGHTS)

    @public_api
    def update_weights_dropdown(self, weights: list[str]):
        """Cache available weights so summaries stay consistent."""
        self._available_weight_names = list(weights or [])
        if (
            self.controller.active_weight_name
            and self.controller.active_weight_name in self._available_weight_names
        ):
            self._update_active_weight_display(self.controller.active_weight_name)
        elif not self._available_weight_names:
            self._update_active_weight_display("")

    def set_active_weight_in_dropdown(self, weight_name: str | None):
        """Update the active weight summary."""
        self._update_active_weight_display(weight_name or "")

    def update_openvino_checkbox(self, enabled: bool):
        """Synchronize OpenVINO toggle state with the summary label."""
        self._openvino_enabled = bool(enabled)
        self._refresh_openvino_summary()

    def update_openvino_status_display(self, status: str):
        """Update the detailed OpenVINO status shown in the UI."""
        self._openvino_status_message = status or ""
        self._refresh_openvino_summary()

    def _refresh_openvino_summary(self):
        state_text = "Ativado" if self._openvino_enabled else "Desativado"
        status_text = self._openvino_status_message.strip()
        if status_text:
            self._openvino_display_var.set(f"OpenVINO: {state_text} — {status_text}")
        else:
            self._openvino_display_var.set(f"OpenVINO: {state_text}")

    def _update_active_weight_display(self, weight_name: str):
        if weight_name:
            self._active_weight_display_var.set(f"Peso ativo: {weight_name}")
        else:
            self._active_weight_display_var.set("Peso ativo: Nenhum peso selecionado.")

    def update_gpu_hardware_display(self, hardware_summary: dict):
        """Update the GPU hardware information shown in the UI."""
        gpu_name = "CPU apenas"
        recommended_backend = hardware_summary.get("recommended_backend", "pytorch")

        # Try to get NVIDIA GPU name first
        if hardware_summary.get("cuda_available", False):
            try:
                import torch

                if torch.cuda.is_available():
                    gpu_name = torch.cuda.get_device_name(0)
            except Exception:
                gpu_name = "NVIDIA GPU"
        # Then check for Intel/OpenVINO GPU
        elif hardware_summary.get("has_intel_gpu", False):
            openvino_devices = hardware_summary.get("openvino_devices", [])
            gpu_devices = [d for d in openvino_devices if "GPU" in d]
            if gpu_devices:
                gpu_name = "Intel GPU"

        # Format display string
        backend_display = "PyTorch" if recommended_backend == "pytorch" else "OpenVINO"
        if "CPU" in gpu_name:
            display_text = f"Hardware: {gpu_name}"
        else:
            display_text = f"Hardware: {gpu_name} (recomendado: {backend_display})"

        self._gpu_hardware_display_var.set(display_text)

    def _create_project_workflow(self):
        """
        Handle the UI part of creating a new project by opening a comprehensive dialog.

        Then calls the controller with the collected data.
        Phase 7: Direct wizard data delegation to ProjectWorkflowService.
        No adapter layer needed - service processes wizard output directly.
        """
        from zebtrack.ui.wizard.wizard_dialog import WizardDialog

        wizard = WizardDialog(self.root, settings_obj=self.controller.settings)
        if not wizard.result:
            return  # User cancelled

        # Validate required fields
        required_fields = ["project_path", "project_name", "project_type"]
        missing = [f for f in required_fields if f not in wizard.result]
        if missing:
            self.show_error("Erro no Wizard", f"Campos obrigatórios ausentes: {', '.join(missing)}")
            return

        # Pass wizard data directly to controller (via ProjectWorkflowService)
        # The service now handles data enrichment and processing internally
        self.event_dispatcher.publish_event(Events.WIZARD_CREATE_PROJECT, wizard.result)

    def _open_project_workflow(self):
        """Handle the UI part of opening a project, then call the controller."""
        project_path = self.ask_directory(title="Selecione uma Pasta de Projeto Existente")
        if not project_path:
            return

        self.event_dispatcher.publish_event(Events.PROJECT_OPEN, {"project_path": project_path})

    @public_api
    def _on_analyze_single_video_clicked(self):
        """Handle single video analysis. Delegates to EventDispatcher."""
        return self.event_dispatcher.handle_analyze_single_video_clicked()

    @public_api
    def setup_zone_definition_for_single_video(self, video_path: str, config: dict):
        """Prepare and display the zone configuration tab for a single video."""
        # Reset analysis UI elements for a clean setup
        self.hide_progress_bar()
        self.analysis_status_var.set("Nenhuma análise em andamento.")
        if self.analysis_display_widget and self.analysis_display_widget.video_label:
            try:
                self.analysis_display_widget.video_label.configure(image="")
                self._analysis_overlay_image = None
            except Exception:
                pass

        self.pending_single_video_path = video_path
        self.pending_single_video_config = config

        # Ensure zone edits persist under the selected video
        self.controller.project_manager.set_active_zone_video(video_path)

        # Open the main project view if it is not already open
        if not self.notebook:
            self._create_main_control_frame()

        self.canvas_manager.display_roi_video_frame(video_path)
        self.notebook.select(self.zone_tab_frame)

        # Clear template selection for single video workflow - user should
        # explicitly choose if they want to apply a template
        self._refresh_roi_templates(clear_selection=True)

        # Add a "Start Analysis" button specific to this flow
        if not self.start_single_analysis_btn:
            self.start_single_analysis_btn = ttk.Button(
                self.fixed_button_frame,  # Add to the fixed button frame at bottom
                text="Iniciar Análise de Vídeo Único",
                command=self._on_start_single_video_processing_clicked,
            )
            self.start_single_analysis_btn.pack(side="bottom", fill="x", pady=5)
        self.start_single_analysis_btn.config(state="normal")

        self.show_info(
            "Configuração Necessária",
            "Defina a arena do aquário usando a detecção automática ou o "
            "desenho manual.\n\n"
            "Após definir a arena principal, clique em 'Iniciar Análise de "
            "Vídeo Único'.",
        )

        self.state_synchronizer.prepare_single_video_ui_state(config)

    def _on_auto_detect_clicked(self, stabilization_frames: int | str | None = None):
        """Handle the auto-detect button."""
        # Prevent editing during analysis
        if self.analysis_active:
            self.show_warning(
                "Análise em Progresso",
                "Não é possível detectar zonas durante a análise de vídeo.",
            )
            return

        raw_value = (
            stabilization_frames
            if stabilization_frames is not None
            else self.stabilization_frames_var.get()
        )

        try:
            stabilization_frames_int = int(raw_value)
            if stabilization_frames_int <= 0:
                raise ValueError
        except (ValueError, TypeError):
            self.show_warning(
                "Entrada Inválida",
                "O número de frames para análise deve ser um número inteiro positivo.",
            )
            return

        # Keep UI entry in sync with validated value
        self.stabilization_frames_var.set(str(stabilization_frames_int))

        # Clear any old interactive polygon before starting a new detection
        self._clear_interactive_polygon()

        video_path = self.pending_single_video_path or None

        self.event_dispatcher.publish_event(
            Events.ZONE_AUTO_DETECT,
            {
                "video_path": video_path,
                "stabilization_frames": stabilization_frames_int,
            },
        )

    def _on_start_single_video_processing_clicked(self):
        """Handle the 'Start Analysis' button in the single video flow."""
        # If the user was editing a polygon, prompt for confirmation before saving.
        if self.edited_polygon_points:
            response = self.dialog_manager.confirm_save_polygon_before_analysis()
            if response is None:
                # Cancel pressed, abort analysis
                return
            elif response:
                # Yes pressed, save polygon
                self.controller.save_manual_arena(self.edited_polygon_points)
                self._clear_interactive_polygon()
            else:
                # No pressed, discard changes
                self._clear_interactive_polygon()

        # 1. Get the zone data that the user drew
        zone_data = self._get_zone_data_for_active_context()
        if not zone_data.polygon:
            self.show_error("Erro", "A área principal do aquário (polígono) não foi definida.")
            return

        updated_config = self.validation_manager.compose_single_video_runtime_config()
        if updated_config is None:
            return
        self.pending_single_video_config = updated_config

        # 2. Disable the button and publish the event
        self.start_single_analysis_btn.config(state="disabled")
        self.event_dispatcher.publish_event(
            Events.VIDEO_START_SINGLE_PROCESSING,
            {
                "video_path": self.pending_single_video_path,
                "config": self.pending_single_video_config,
                "zone_data": zone_data,
            },
        )

        # 3. Clear the pending state
        self.pending_single_video_path = None
        self.pending_single_video_config = None

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
        """Toggle between zone drawing view and analysis progress view."""
        if not self.notebook or not self.analysis_tab_frame or not self.zone_tab_frame:
            return

        current_tab = self.notebook.select()
        analysis_tab_id = str(self.analysis_tab_frame)

        if current_tab != analysis_tab_id:
            self._switch_to_analysis_view()
        else:
            self._switch_to_zones_view()

    def _switch_to_analysis_view(self):
        """Switch to analysis progress view."""
        if not self.notebook or not self.analysis_tab_frame:
            return

        self.canvas_view_mode = "analysis"
        self.notebook.select(self.analysis_tab_frame)

        if self.zone_controls and self.zone_controls.toggle_view_btn:
            self.zone_controls.toggle_view_btn.config(text="Ver Configuração de Zonas")

    def _switch_to_zones_view(self):
        """Switch to zone drawing view."""
        if not self.notebook or not self.zone_tab_frame:
            return

        self.canvas_view_mode = "zones"
        self.notebook.select(self.zone_tab_frame)

        if self.zone_controls and self.zone_controls.toggle_view_btn:
            self.zone_controls.toggle_view_btn.config(text="Ver Análise em Progresso")

    def start_analysis_view_mode(self):
        """Start analysis - immediately switch to analysis view and enable toggle."""
        self.analysis_active = True
        self.analysis_status_var.set("Preparando análise...")
        if self.analysis_task_var is not None:
            self.analysis_task_var.set("Preparando fila de análise...")
        self.state_synchronizer._set_analysis_metadata_defaults()
        self._reset_analysis_controls()
        self.show_progress_bar()
        if self.zone_controls and self.zone_controls.toggle_view_btn:
            self.zone_controls.toggle_view_btn.config(state="normal")
        if self.analysis_display_widget:
            self.analysis_display_widget.enable_cancel_button()
        self._switch_to_analysis_view()

    def stop_analysis_view_mode(self):
        """Stop analysis - disable toggle and return to zones view."""
        self.analysis_active = False
        if self.zone_controls and self.zone_controls.toggle_view_btn:
            self.zone_controls.toggle_view_btn.config(state="disabled")
        if self.analysis_display_widget:
            self.analysis_display_widget.disable_cancel_button()
        self.hide_progress_bar()
        self.analysis_status_var.set("Nenhuma análise em andamento.")
        if self.analysis_task_var is not None:
            self.analysis_task_var.set("Nenhuma tarefa em andamento.")
        self.state_synchronizer._set_analysis_metadata_defaults()
        self._reset_analysis_controls()
        self._switch_to_zones_view()

    def update_detection_overlay(
        self,
        detections: list[tuple],
        report: ProcessingReport | None = None,
    ) -> None:
        """Receive the latest detection batch for track selection overlays."""
        if detections is None:
            detections = []

        mode = report.mode if report else self._active_processing_mode
        self._current_detections = list(detections)

        if self.track_selector_widget:
            state = "disabled" if mode is ProcessingMode.SINGLE_SUBJECT else "readonly"
            self.track_selector_widget.configure(state=state)

        if mode is ProcessingMode.SINGLE_SUBJECT:
            self.track_selector_var.set("Todos")
            self.state_synchronizer._update_track_options(["Todos"])
        else:
            options = self._build_track_options(self._current_detections)
            self.state_synchronizer._update_track_options(options)

        if self._last_analysis_frame is not None:
            self.canvas_manager._render_last_analysis_frame()

    def update_processing_mode(self, report: ProcessingReport | None) -> None:
        """Update the UI to reflect the active tracking pipeline."""
        if report is None:
            return

        previous_mode = self._active_processing_mode
        mode = report.mode
        self._active_processing_mode = mode

        if self.analysis_display_widget:
            self.analysis_display_widget.set_tracking_mode(mode.display_name)

        if self.analysis_display_widget and self.analysis_display_widget.track_selector_widget:
            state = "disabled" if mode is ProcessingMode.SINGLE_SUBJECT else "readonly"
            self.analysis_display_widget.track_selector_widget.configure(state=state)

        if mode is ProcessingMode.SINGLE_SUBJECT:
            if self.analysis_display_widget:
                self.analysis_display_widget.track_selector_var.set("Todos")
            self.state_synchronizer._update_track_options(["Todos"])
        elif previous_mode is ProcessingMode.SINGLE_SUBJECT:
            # Re-populate track selector
            options = self.widget_factory.build_track_options(self._current_detections)
            self.state_synchronizer._update_track_options(options)

    def update_analysis_profile(self, profile_name: str) -> None:
        """Update the label describing the active analysis profile."""
        text = (profile_name or "default").strip() or "default"
        self.analysis_profile_var.set(f"Perfil de análise: {text}")
        self._reset_analysis_controls()

    def _reset_analysis_controls(self) -> None:
        """Reset track selector state and cached frames."""
        self._current_detections = []
        self._last_analysis_frame = None
        self._analysis_overlay_image = None

        if self.analysis_display_widget:
            self.analysis_display_widget.track_selector_var.set("Todos")
            self.state_synchronizer._update_track_options(["Todos"])

            if self.analysis_display_widget.track_selector_widget:
                state = (
                    "disabled"
                    if self._active_processing_mode is ProcessingMode.SINGLE_SUBJECT
                    else "readonly"
                )
                self.analysis_display_widget.track_selector_widget.configure(state=state)

    def _build_track_options(self, detections: list[tuple]) -> list[str]:
        observed: set[str] = set()
        for det in detections:
            if len(det) < 6:
                continue
            track_id = det[5]
            if track_id is None:
                continue
            text = str(track_id).strip()
            if text:
                observed.add(text)

        ordered = sorted(observed, key=str)
        return ["Todos", *ordered]

    def _on_track_selection_changed(self, _event=None) -> None:
        self.canvas_manager._render_last_analysis_frame()

    def update_analysis_progress(self, value, status_text=None):
        """Update progress bar and status in the analysis overlay."""
        if self.progress_bar:
            self.progress_bar["value"] = value * 100
        if status_text:
            self.analysis_status_var.set(status_text)
        self.update_idletasks()

    def update_analysis_metadata(self, *, metadata: dict | None) -> None:
        """Update the metadata display for the currently processed video."""
        metadata = metadata or {}
        group_display = self.validation_manager.resolve_group_display(metadata)
        day_display = self.validation_manager.resolve_day_display(metadata)
        subject_display = self.validation_manager.resolve_subject_display(metadata)

        self.state_synchronizer._apply_analysis_metadata_strings(
            group_display,
            day_display,
            subject_display,
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


if __name__ == "__main__":
    # Using print is fine here as it's for direct execution feedback
    print("Este arquivo deve ser importado, não executado diretamente.")
    print("Execute o script principal da aplicação para iniciar o Zebtrack.")
