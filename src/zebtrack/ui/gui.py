"""
Este módulo define a interface gráfica principal (GUI) para a aplicação Zebtrack.
"""

import hashlib
import os
import queue
import re
import subprocess
import sys
import threading
import time
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
    filedialog,
    messagebox,
    ttk,
)
from tkinter import font as tkfont
from typing import Any

import cv2
import numpy as np
import structlog
from PIL import Image, ImageTk

try:
    import ttkbootstrap as ttkb
except ImportError:  # pragma: no cover - optional dependency fallback
    ttkb = None

# Import custom modules
from zebtrack.core.detector import ZoneData
from zebtrack.core.processing_mode import ProcessingMode, ProcessingReport
from zebtrack.io.camera import Camera
from zebtrack.ui.components import (
    AnalysisDisplayWidget,
    ArduinoDashboardWidget,
    CanvasManager,
    ConfigEditorWidget,
    DialogManager,
    EventDispatcher,
    MenuManager,
    ProjectOverviewWidget,
    ProjectViewManager,
    StateSynchronizer,
    ValidationManager,
    VideoDisplayWidget,
    WidgetFactory,
    ZoneControlsWidget,
)
from zebtrack.ui.dialogs import (
    CalibrationDialog,
    CenterPeripheryDialog,
    ColorSelectionDialog,
    MissingMetadataDialog,
    PendingVideosDialog,
    SaveROITemplateDialog,
    SingleVideoConfigDialog,
    StartRecordingDialog,
    SubjectSelectionDialog,
)
from zebtrack.ui.event_bus import EventBus, EventType
from zebtrack.ui.events import Events
from zebtrack.ui.window_utils import (
    reset_geometry_if_not_maximized,
)
from zebtrack.utils import polygon_centroid, snap_point_to_axes

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


class _VideoPathResolverContext:
    """Helper class to reduce complexity of _resolve_processing_reports_video_paths."""

    def __init__(self, tree, metadata_store):
        self.tree = tree
        self.metadata_store = metadata_store
        self.final_paths: list[str] = []
        self.seen_paths: set[str] = set()
        self.resolved_video_nodes: list[str] = []
        self.had_hierarchy_nodes = False

    def add_video_path(self, video_path: str | None, node_id: str | None = None) -> None:
        """Add a video path if not already seen."""
        if not video_path or video_path in self.seen_paths:
            return
        self.seen_paths.add(video_path)
        self.final_paths.append(video_path)
        if node_id and node_id not in self.resolved_video_nodes and self.tree.exists(node_id):
            self.resolved_video_nodes.append(node_id)

    def add_video_node(self, item_id: str) -> None:
        """Process a single video or file node."""
        metadata = self.metadata_store.get(item_id)
        if not metadata:
            return
        node_type = metadata.get("type")
        if node_type == "video":
            self.add_video_path(metadata.get("video_path"), item_id)
        elif node_type == "file":
            parent_video = metadata.get("parent_video")
            if parent_video:
                self.add_video_path(parent_video, f"video_{parent_video}")

    def collect_descendants(self, item_id: str) -> None:
        """Recursively collect all video descendants."""
        if not self.tree.exists(item_id):
            return
        try:
            self.tree.item(item_id, open=True)
        except Exception:
            pass
        for child in self.tree.get_children(item_id):
            child_type = self.metadata_store.get(child, {}).get("type")
            if child_type in ("video", "file"):
                self.add_video_node(child)
            else:
                self.collect_descendants(child)

    def process_item(self, item_id: str) -> None:
        """Process a single item from the selection."""
        metadata = self.metadata_store.get(item_id)
        if metadata and metadata.get("type") in ("video", "file"):
            self.add_video_node(item_id)
        else:
            self.had_hierarchy_nodes = True
            self.collect_descendants(item_id)

    def update_tree_selection(self) -> None:
        """Update tree selection to show resolved video nodes."""
        if self.had_hierarchy_nodes and self.resolved_video_nodes:
            try:
                self.tree.selection_set(tuple(self.resolved_video_nodes))
            except Exception:
                pass


class ApplicationGUI:
    """
    A classe principal que gerencia a interface gráfica (a "Visão").
    """

    DEFAULT_CANVAS_WIDTH = 800
    DEFAULT_CANVAS_HEIGHT = 600

    def __init__(self, root, controller, event_bus: EventBus | None = None, settings_obj=None):
        """
        Inicializa a ApplicationGUI.
        """
        self.root = root
        self.controller = controller
        self.event_bus = event_bus
        self.settings = settings_obj
        self._event_bus_after_id: int | None = None
        self._event_bus_poll_interval_ms = 50
        self._event_bus_handlers: dict[EventType, Callable[[Any], None]] = {}
        self.root.title("DRerio LogAI")
        self.root.protocol("WM_DELETE_WINDOW", self.controller.on_close)

        self._ttkbootstrap_style = None
        self._ttkbootstrap_theme = None
        self._initialize_theme()

        # Initialize component managers (extracted from God Object)
        # Phase 1 components
        self.menu_manager = MenuManager(self)
        self.canvas_manager = CanvasManager(self)
        self.state_synchronizer = StateSynchronizer(self)
        self.event_dispatcher = EventDispatcher(self)

        # Phase 2 components
        self.validation_manager = ValidationManager(self)
        self.dialog_manager = DialogManager(self)
        self.widget_factory = WidgetFactory(self)
        self.project_view_manager = ProjectViewManager(self)

        # Create menu bar
        self.menu_manager.create_menu_bar()

        # Dynamic widgets / state variables
        self.welcome_frame = None
        self.notebook = None
        self.main_controls_frame = None
        self.zone_tab_frame = None
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

        # Maintain backward compatibility aliases (will be removed later)
        self.video_label: Label | None = None
        self.progress_frame: ttk.Frame | None = None
        self.progress_bar = None
        self.progress_labels: dict[str, StringVar] = {}
        self.cancel_proc_btn: ttk.Button | None = None
        self.tracking_mode_var = StringVar(value="Modo de rastreamento: Multi-Track")
        self.track_selector_var = StringVar(value="Todos")
        self.track_selector_widget: ttk.Combobox | None = None
        self.social_summary_var = StringVar(value="Interações sociais: aguardando dados.")
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

        self._configure_styles()
        self._create_welcome_frame()

        log.info("gui.init.event_bus_setup", has_event_bus=self.event_bus is not None)
        if self.event_bus is not None:
            log.info("gui.init.registering_handlers")
            self._register_event_bus_handlers()
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






































    def _build_status_icon_legend(self, *, include_summary: bool = False) -> str:
        """Build status icon legend. Delegates to WidgetFactory."""
        return self.widget_factory.build_status_icon_legend_simple(include_summary=include_summary)

    # --- Event bus helpers -------------------------------------------------

    def _register_event_bus_handlers(self) -> None:
        self._event_bus_handlers = {
            EventType.CALLABLE: self._handle_callable_event,
            EventType.NAMED: self._handle_named_event,
        }





    def _poll_event_bus(self) -> None:
        """Poll the event bus for pending events and dispatch them."""
        self._event_bus_after_id = None
        if self.event_bus is None:
            log.warning("gui.event_bus.poll_no_bus")
            return

        queue_size = self.event_bus.size()
        if queue_size > 0:
            log.debug("gui.event_bus.poll_queue_size", size=queue_size)

        events = self.event_bus.drain(max_items=50)
        if events:
            log.debug("gui.event_bus.polling", event_count=len(events))

        processed = 0
        for event in events:
            # Use the EventType handlers to dispatch CALLABLE and NAMED events
            handler = self._event_bus_handlers.get(event.type)
            if handler is None:
                log.warning(
                    "gui.event_bus.unhandled_event_type",
                    event_type=event.type.name,
                )
                continue
            try:
                handler(event.payload)
                processed += 1
            except Exception:
                log.warning(
                    "gui.event_bus.handler_error",
                    event_type=event.type.name,
                    exc_info=True,
                )

        if processed:
            log.debug("gui.event_bus.processed", count=processed)

        log.info("gui.event_bus.poll_complete", will_reschedule=True)
        self.event_dispatcher.schedule_event_bus_poll()

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


    def _get_zone_summary_helper_text(self) -> str:
        """Get zone summary helper text. Delegates to WidgetFactory."""
        return self.widget_factory.get_zone_summary_helper_text()

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

    def _update_window_title(self, project_name: str | None = None):
        """
        Updates the window title with optional project name.
        Delegates to ProjectViewManager.

        Args:
            project_name: Name of the current project, or None for default title
        """
        return self.project_view_manager.update_window_title(project_name)



    def _display_welcome_logo(self):
        """Displays the DRerio LogAI logo in the welcome frame."""
        try:
            from pathlib import Path

            # Try to load logo from assets
            logo_path = Path(__file__).parent / "assets" / "logo_welcome.png"

            if not logo_path.exists():
                # Fallback for development environment
                logo_path = Path("src/zebtrack/ui/assets/logo_welcome.png")

            if logo_path.exists():
                # Load and display logo
                logo_pil = Image.open(logo_path)
                self._welcome_logo_image = ImageTk.PhotoImage(logo_pil)

                logo_label = ttk.Label(self.welcome_frame, image=self._welcome_logo_image)
                logo_label.pack(pady=(10, 20))

                log.debug("welcome.logo.displayed", path=str(logo_path))
            else:
                # Fallback to text if logo not found
                ttk.Label(
                    self.welcome_frame,
                    text="Bem-vindo ao DRerio LogAI",
                    font=("Helvetica", 16),
                ).pack(pady=(0, 15))
                log.warning("welcome.logo.not_found", attempted_path=str(logo_path))

        except Exception as e:
            # Fallback to text on any error
            ttk.Label(
                self.welcome_frame,
                text="Bem-vindo ao DRerio LogAI",
                font=("Helvetica", 16),
            ).pack(pady=(0, 15))
            log.warning("welcome.logo.load_error", error=str(e))

    def _create_welcome_frame(self):
        """Creates the initial UI for project selection and model configuration."""
        # Reset title to default (no project)
        self._update_window_title()

        self._cleanup_single_analysis_button()
        # CRITICAL: Force process all pending GUI events before cleanup
        # This ensures all scheduled callbacks are executed
        self.root.update_idletasks()

        # Reset + destroy analysis-related widgets
        self._reset_analysis_widgets()

        # Force final GUI update before creating welcome frame
        self.root.update_idletasks()

        reset_geometry_if_not_maximized(self.root)
        self.welcome_frame = ttk.Frame(self.root, padding="10")
        self.welcome_frame.pack(expand=True, fill="both")

        # --- Logo Image ---
        self._display_welcome_logo()

        # Project actions and model status widgets
        self._build_project_actions(self.welcome_frame)
        self._build_model_status(self.welcome_frame)

    def _reset_analysis_widgets(self) -> None:
        """Encapsula a limpeza e destruição de widgets da aba de análise."""
        # Break the cleanup into smaller helpers to reduce cognitive complexity
        self.state_synchronizer._reset_analysis_media()
        self.state_synchronizer._reset_analysis_progress_and_metadata()
        self.state_synchronizer._reset_roi_and_visual_frames()
        self.state_synchronizer._destroy_notebook_and_main_controls()
        self.analysis_tab_frame = None





    def _build_project_actions(self, parent) -> None:
        """Create the project actions controls. Delegates to WidgetFactory."""
        return self.widget_factory.build_project_actions(parent)

    def _build_model_status(self, parent) -> None:
        """Create the model status display. Delegates to WidgetFactory."""
        return self.widget_factory.build_model_status(parent)

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

    def _configure_styles(self) -> None:
        """Configure custom styles. Delegates to WidgetFactory."""
        return self.widget_factory.configure_styles()

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
        Handle tab change event to ensure analysis overlay is hidden when not on
        analysis tab.
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
        """Creates the main UI with tabs for controlling the app."""
        if self.welcome_frame:
            self.welcome_frame.destroy()
        reset_geometry_if_not_maximized(self.root)

        self.notebook = ttk.Notebook(self.root, style="Zebtrack.TNotebook")
        self.notebook.pack(expand=True, fill="both", padx=5, pady=5)

        # Bind tab change event to hide analysis overlay when switching tabs
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # Create the tabs
        self._create_main_controls_tab()
        if self.controller.project_manager.get_project_type() == "live":
            self._create_progress_grid_tab()
        self._create_roi_analysis_tab()
        self._create_processing_reports_tab()  # New unified tab
        self._create_analysis_tab_widget()
        self._create_configuration_tab_widget()

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

    def _create_configuration_tab_widget(self) -> None:
        """Creates the configuration tab. Delegates to WidgetFactory."""
        return self.widget_factory.create_configuration_tab_widget()

    def _reload_config_editor_values_widget(self) -> None:
        """Load current settings into ConfigEditorWidget. Delegates to WidgetFactory."""
        return self.widget_factory.reload_config_editor_values()

    def _on_reset_global_config_form_widget(self) -> None:
        """Reset ConfigEditorWidget form fields to reflect current settings object."""
        self._reload_config_editor_values_widget()
        self.show_info(
            "Formulário recarregado",
            "Valores restaurados para refletir as configurações atuais.",
        )

    def _on_save_global_config_from_widget(self, values: dict) -> None:
        """Validate and save config from ConfigEditorWidget. Delegates to ValidationManager."""
        return self.validation_manager.save_global_config_from_widget(values)

    def _on_roi_rule_change_widget(self, rule: str) -> None:
        """Handle ROI rule change from ConfigEditorWidget."""
        # This widget doesn't need conditional UI updates (unlike the zones tab)
        # But we keep this handler for future extensions
        pass

    def _create_main_controls_tab(self):
        """Creates the tab with the main project controls."""
        self.main_controls_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.main_controls_frame, text="Controle Principal")

        project_type = self.controller.project_manager.get_project_type()
        self.process_video_btn = None

        controls_container = ttk.Frame(self.main_controls_frame)
        controls_container.pack(fill="x", pady=(0, 10))

        if project_type == "live":
            self.start_rec_btn = Button(
                controls_container,
                text="Iniciar Gravação",
                command=lambda: self.event_dispatcher.publish_event(Events.RECORDING_START, {}),
            )
            self.start_rec_btn.pack(side="left", padx=5)
            self.stop_rec_btn = Button(
                controls_container,
                text="Parar Gravação",
                command=lambda: self.event_dispatcher.publish_event(Events.RECORDING_STOP, {}),
                state="disabled",
            )
            self.stop_rec_btn.pack(side="left", padx=5)
        elif project_type == "pre-recorded":
            # Primary action: add/process new videos (legacy location)
            ttk.Button(
                controls_container,
                text="Adicionar e Processar Novos Vídeos/Pastas...",
                command=lambda: self.event_dispatcher.publish_event(
                    Events.PROJECT_PROCESS_VIDEOS, {}
                ),
            ).pack(side="left", padx=5)

            # Project-wide interval settings
            intervals_frame = ttk.LabelFrame(
                self.main_controls_frame, text="Intervalos de Processamento", padding=10
            )
            intervals_frame.pack(fill="x", pady=10, padx=10)

            # Analysis interval
            analysis_label_frame = ttk.Frame(intervals_frame)
            analysis_label_frame.pack(fill="x", pady=2)
            ttk.Label(analysis_label_frame, text="Intervalo de Análise (frames):").pack(side="left")
            ttk.Entry(analysis_label_frame, textvariable=self.analysis_interval_var, width=10).pack(
                side="right"
            )

            # Display interval
            display_label_frame = ttk.Frame(intervals_frame)
            display_label_frame.pack(fill="x", pady=2)
            ttk.Label(display_label_frame, text="Intervalo de Exibição (frames):").pack(side="left")
            ttk.Entry(display_label_frame, textvariable=self.display_interval_var, width=10).pack(
                side="right"
            )

        Button(
            controls_container,
            text="Fechar Projeto",
            command=lambda: self.event_dispatcher.publish_event(Events.PROJECT_CLOSE, {}),
        ).pack(side="right", padx=5)

        self._create_project_overview_panel(self.main_controls_frame)

        model_status_frame = ttk.LabelFrame(
            self.main_controls_frame,
            text="Estado do Modelo de Detecção",
            padding=10,
        )
        model_status_frame.pack(fill="x", pady=(10, 10))
        ttk.Label(
            model_status_frame,
            textvariable=self._active_weight_display_var,
        ).pack(anchor="w")
        ttk.Label(
            model_status_frame,
            textvariable=self._openvino_display_var,
        ).pack(anchor="w", pady=(4, 0))
        button_row = ttk.Frame(model_status_frame)
        button_row.pack(anchor="w", pady=(6, 0))
        ttk.Button(
            button_row,
            text="Calibração Global...",
            command=self._open_global_calibration_window,
        ).pack(side="left", padx=(0, 6))
        if getattr(self.controller.project_manager, "project_path", None):
            ttk.Button(
                button_row,
                text="Calibração e Preferências do Projeto...",
                command=self._open_project_calibration_window,
            ).pack(side="left")

        if project_type == "live":
            self.external_trigger_notice_label = Label(
                self.main_controls_frame,
                textvariable=self.external_trigger_notice_var,
                anchor="w",
                justify="left",
                wraplength=600,
                padx=10,
                pady=6,
            )
            self.external_trigger_notice_label.pack(fill="x", pady=(0, 8))
            self._external_notice_default_bg = self.external_trigger_notice_label.cget("background")
            self._external_notice_default_fg = self.external_trigger_notice_label.cget("foreground")

            # Create Arduino dashboard widget
            self.arduino_dashboard_widget = ArduinoDashboardWidget(
                self.main_controls_frame,
                event_bus=self.event_bus,
                project_manager=self.controller.project_manager,
            )
            self.arduino_dashboard_widget.pack(fill="both", expand=False, pady=(0, 10))
            self.clear_external_trigger_notice()

        self._request_overview_refresh()

    def _create_project_overview_panel(self, parent: ttk.Frame) -> None:
        """Create the project overview panel. Delegates to WidgetFactory."""
        return self.widget_factory.create_project_overview_panel(parent)

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

    def _get_status_meta(self, status_key: str) -> tuple[str, str]:
        """Get status metadata. Delegates to ProjectViewManager."""
        return self.project_view_manager._get_status_meta(status_key)

    def _request_overview_refresh(
        self,
        reason: str | None = None,
        *,
        append_summary: bool = False,
        immediate: bool = False,
    ) -> None:
        """Request overview refresh. Delegates to ProjectViewManager."""
        return self.project_view_manager._request_overview_refresh(
            reason=reason,
            append_summary=append_summary,
            immediate=immediate,
        )

    def refresh_project_views(
        self,
        reason: str | None = None,
        *,
        append_summary: bool = False,
        immediate: bool = False,
    ) -> None:
        """Refresh overview, pipeline, and reports panels. Delegates to ProjectViewManager."""
        return self.project_view_manager.refresh_project_views(
            reason=reason,
            append_summary=append_summary,
            immediate=immediate,
        )

    def _refresh_project_overview(self) -> None:
        """Refresh the project overview display. Delegates to ProjectViewManager."""
        return self.project_view_manager._refresh_project_overview()

    def _compose_overview_status_line(self, total: int, counts: Counter) -> str:
        """Compose status line for overview. Delegates to ProjectViewManager."""
        return self.project_view_manager._compose_overview_status_line(total, counts)

    def _update_project_overview_summary(
        self,
        counts: Counter,
        total: int,
        videos: list[dict] | None,
    ) -> None:
        """Update project overview summary. Delegates to ProjectViewManager."""
        return self.project_view_manager._update_project_overview_summary(counts, total, videos)

    def _update_project_overview_tree(self, project_manager, all_videos: list[dict]) -> None:
        """Update the project overview tree. Delegates to ProjectViewManager."""
        return self.project_view_manager._update_project_overview_tree(project_manager, all_videos)

    def _prepare_overview_hierarchy_for_widget(self, all_videos: list[dict]) -> dict:
        """Prepare hierarchy data for ProjectOverviewWidget. Delegates to ProjectViewManager."""
        return self.project_view_manager._prepare_overview_hierarchy_for_widget(all_videos)

    def _format_status_label(self, status_key: str) -> str:
        """Format status label. Delegates to ProjectViewManager."""
        return self.project_view_manager._format_status_label(status_key)

    def _format_status_summary(self, counts: Counter) -> str:
        """Format status summary. Delegates to ProjectViewManager."""
        return self.project_view_manager._format_status_summary(counts)

    def _format_status_ratio(self, symbol_key: str, completed: int, total: int) -> str:
        """Format status ratio. Delegates to ProjectViewManager."""
        return self.project_view_manager._format_status_ratio(symbol_key, completed, total)

    def _summarize_batch_data(self, videos: list[dict]) -> str:
        """Summarize batch data. Delegates to ProjectViewManager."""
        return self.project_view_manager._summarize_batch_data(videos)

    def _format_data_badges(self, video: dict) -> str:
        """Format data badges. Delegates to ProjectViewManager."""
        return self.project_view_manager._format_data_badges(video)

    def _format_video_metadata(self, metadata: dict) -> str:
        """Format video metadata. Delegates to ProjectViewManager."""
        return self.project_view_manager._format_video_metadata(metadata)

    def _on_project_overview_tree_double_click(self, event) -> None:
        """Handle double-click events on the overview tree (legacy handler)."""
        del event

        if not self.project_overview_tree:
            return

        item_id = self.project_overview_tree.focus()
        if item_id:
            self._on_project_overview_tree_double_click_impl(item_id)

    def _on_project_overview_tree_double_click_impl(self, item_id: str) -> None:
        """Implementation of double-click logic (reusable)."""
        if not self.project_overview_tree:
            return

        tags = self.project_overview_tree.item(item_id, "tags") or ()
        if not tags:
            return

        video_path = tags[0]
        if not video_path or video_path.startswith("status_"):
            return

        if not os.path.exists(video_path):
            self.show_warning(
                "Arquivo não encontrado",
                f"O vídeo selecionado não foi localizado:\n{video_path}",
            )
            return

        success = self.canvas_manager.load_video_frame_to_canvas(video_path, frame_number=0)
        if success:
            self._maybe_offer_zone_reuse(video_path)
            self.canvas_manager.redraw_zones_from_project_data()
            message = f"Frame carregado: {os.path.basename(video_path)}"
            self.set_status(message)
            self._request_overview_refresh(reason=message, append_summary=True)
        else:
            self.show_error(
                "Erro ao Carregar",
                f"Não foi possível carregar o vídeo selecionado.\n{video_path}",
            )

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






    def show_external_trigger_notice(self, session_label: str, **details):
        if not self.external_trigger_notice_label:
            return

        day = details.get("day")
        group = details.get("group")
        cobaia = details.get("cobaia")
        port = details.get("port")

        descriptors = []
        if day is not None and group is not None and cobaia is not None:
            day_display = self._format_day_display(day) or day
            descriptors.append(f"Dia {day_display}, Grupo {group}, Sujeito {cobaia}")
        if port:
            descriptors.append(f"Porta {port}")

        message = f"Aguardando sinal externo para iniciar {session_label}."
        if descriptors:
            message += f" ({' • '.join(descriptors)})"

        self.external_trigger_notice_var.set(message)

        highlight_bg = "#FFF7ED"
        highlight_fg = "#92400e"
        try:
            self.external_trigger_notice_label.config(
                background=highlight_bg,
                foreground=highlight_fg,
            )
        except Exception:
            pass

    def clear_external_trigger_notice(self):
        if not self.external_trigger_notice_label:
            return

        self.external_trigger_notice_var.set("")

        try:
            bg = (
                self._external_notice_default_bg
                if self._external_notice_default_bg is not None
                else self.external_trigger_notice_label.cget("background")
            )
            fg = (
                self._external_notice_default_fg
                if self._external_notice_default_fg is not None
                else self.external_trigger_notice_label.cget("foreground")
            )
            self.external_trigger_notice_label.config(background=bg, foreground=fg)
        except Exception:
            pass

    def _create_roi_analysis_tab(self):
        """Creates the tab for ROI and detection zone configuration."""
        # This tab is now for defining detection zones (main polygon, ROI polygons)
        # and will replace the old ROI analysis functionality.
        self.roi_data = {}  # This will be repurposed for the new zone data
        self.drawing_mode = None
        self.current_polygon_points = []

        # Coordinate system for polygon alignment
        self._poly_pts_canvas = []  # Canvas coordinates for UI display
        self._poly_pts_video = []  # Video coordinates for saving
        self._bg_scale = 1.0  # Scaling factor from video to canvas
        self._bg_offset = (0, 0)  # Offset of image in canvas
        self._bg_img_size = (0, 0)  # Original image dimensions

        # Undo/Redo system for drawing
        self._drawing_history = []  # Stack of (canvas_pts, video_pts) states
        self._drawing_redo_stack = []  # Stack for redo operations

        # Interactive vertex editing during drawing
        self._dragging_vertex_index = None  # Index of vertex being dragged
        self._vertex_hover_index = None  # Index of vertex being hovered
        self._vertex_hover_tolerance = 10  # Pixels tolerance for vertex hover detection

        self.current_circle_center = None
        self._canvas_bg_image = None  # Keep a reference to the image
        self._drawing_buttons_frame = None  # Frame for undo/redo buttons

        # 1. Create the main frame for the tab and rename it
        self.zone_tab_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.zone_tab_frame, text="Configuração de Zonas")

        # 2. Create the PanedWindow for side-by-side panels
        main_pane = ttk.PanedWindow(self.zone_tab_frame, orient="horizontal")
        main_pane.pack(expand=True, fill="both")

        # 3. Create the control panel on the left with scrollable frame
        left_panel_frame = ttk.Frame(main_pane, padding=5, relief="groove", borderwidth=2)
        # Add left panel without invalid minsize parameter
        main_pane.add(left_panel_frame, weight=1)

        # ✨ NEW: Create ZoneControlsWidget instead of inline controls
        self.zone_controls = ZoneControlsWidget(left_panel_frame, event_bus=self.event_bus)
        self.zone_controls.pack(fill="both", expand=True)

        # Keep legacy attributes in sync with the new component state
        self.stabilization_frames_var = self.zone_controls.stabilization_frames_var

        # Keep reference to internal widgets for backward compatibility
        # TODO: Migrate code to use ZoneControlsWidget API instead
        self.zone_controls_frame = self.zone_controls.zone_controls_frame
        self.fixed_button_frame = self.zone_controls.fixed_button_frame

        # 4. Create the visualization panel on the right
        self.viz_frame = ttk.Frame(main_pane, padding=5, relief="sunken", borderwidth=2)
        main_pane.add(self.viz_frame, weight=4)

        # Bind pane configure event to maintain minimum left panel width
        def _on_pane_configure(event=None):
            try:
                # Clamp left panel to minimum 600px width to keep all controls visible
                current_pos = main_pane.sashpos(0)
                if current_pos < 600:
                    main_pane.sashpos(0, 600)
            except Exception:
                pass  # Ignore errors during resize

        main_pane.bind("<Configure>", _on_pane_configure)

        # 5. ✨ NEW: Create VideoDisplayWidget instead of manual Canvas
        self.video_display = VideoDisplayWidget(
            self.viz_frame, event_bus=self.event_bus, width=800, height=600, bg="gray"
        )
        self.video_display.pack(expand=True, fill="both")

        # Keep reference to canvas for backward compatibility with drawing code
        # TODO: Migrate drawing logic to use VideoDisplayWidget API
        self._roi_canvas_widget = self.video_display.canvas

        # Bind canvas resize event for proper image scaling (keep existing behavior)
        self._roi_canvas_widget.bind("<Configure>", self._on_canvas_configure)

        # 6. ✨ REMOVED: _create_zone_control_widgets() is no longer needed
        # ZoneControlsWidget already creates all the necessary control widgets
        # The old method is kept below for reference but is no longer called

        # 7. ✨ NEW: Create context menu before subscribing to events
        self.roi_context_menu = None
        self.menu_manager.create_roi_context_menu()

        # 8. ✨ NEW: Subscribe to events emitted by the components
        self._subscribe_zone_component_events()

        # 9. Set initial sash position AFTER all widgets are created
        # This ensures the geometry is properly calculated
        def _set_initial_sash():
            try:
                # Use update_idletasks to ensure geometry is calculated
                main_pane.update_idletasks()
                # Set to 640px so the "Aplicar" button stays fully visible
                main_pane.sashpos(0, 640)
            except Exception:
                pass  # Sash position might fail if pane isn't fully realized yet

        # Try multiple times with increasing delays to ensure it sticks
        main_pane.after(10, _set_initial_sash)
        main_pane.after(50, _set_initial_sash)
        main_pane.after(100, _set_initial_sash)
        main_pane.after(200, _set_initial_sash)

    def _subscribe_zone_component_events(self):
        """Subscribe to events emitted by ZoneControlsWidget. Delegates to EventDispatcher."""
        return self.event_dispatcher.subscribe_zone_component_events()



    def _on_canvas_configure(self, event=None):
        """Handle canvas resize events to properly scale and center the image."""
        # Skip if this is not the main roi_canvas being resized
        if event and event.widget != self.roi_canvas:
            return

        if not hasattr(self, "_raw_bg_image") or not self._raw_bg_image:
            if hasattr(self, "_original_image") and self._original_image:
                self._raw_bg_image = self._original_image
            else:
                return

        # Get the current canvas dimensions
        canvas_width = self.roi_canvas.winfo_width()
        canvas_height = self.roi_canvas.winfo_height()

        if canvas_width <= 1 or canvas_height <= 1:
            return

        # Re-scale and center the background image using the new method
        try:
            self.canvas_manager._draw_bg_image_to_canvas()
            # After updating the background, redraw any zones that exist
            if hasattr(self, "controller") and self.controller:
                self.canvas_manager.redraw_zones_from_project_data()
        except Exception as e:
            log.warning("gui.canvas.configure_error", error=str(e))

    def _create_zone_control_widgets(self):
        """Create all zone control widgets. Delegates to WidgetFactory."""
        return self.widget_factory.create_zone_control_widgets()

    def _create_zone_summary_cards_section(self) -> None:
        """Create zone summary cards. Delegates to WidgetFactory."""
        return self.widget_factory.create_zone_summary_cards_section()


    def _update_zone_summary_cards(self, all_videos=None) -> None:
        """Update zone summary cards. Delegates to ProjectViewManager."""
        return self.project_view_manager._update_zone_summary_cards(all_videos)

    def _refresh_pipeline_video_table(self, all_videos=None) -> None:
        """Refresh pipeline video table. Delegates to ProjectViewManager."""
        return self.project_view_manager._refresh_pipeline_video_table(all_videos)

    def _pipeline_summary_exists(self, video_info: dict) -> bool:
        controller = getattr(self, "controller", None)
        pm = getattr(controller, "project_manager", None)
        path = video_info.get("path")
        if not pm or not path:
            return False

        experiment_id = Path(path).stem
        entry = pm.find_video_entry(path=path)
        metadata_hint = dict(entry.get("metadata") or {}) if entry else {}
        results_path = pm.resolve_results_directory(
            experiment_id,
            video_path=path,
            metadata=metadata_hint,
        )
        summary_path = Path(results_path) / f"{experiment_id}_summary.parquet"
        return summary_path.exists()

    def _get_selected_pipeline_video_paths(self) -> list[str]:
        if not self.pipeline_video_tree:
            return []
        selected_items = list(self.pipeline_video_tree.selection() or [])
        if not selected_items:
            return []

        final_selection: list[str] = []
        seen_subjects: set[str] = set()
        had_hierarchy_nodes = False

        def add_subject(item_id: str) -> None:
            if item_id in self.pipeline_video_vars and item_id not in seen_subjects:
                seen_subjects.add(item_id)
                final_selection.append(item_id)

        def collect_descendants(item_id: str) -> None:
            # Ensure parent nodes are expanded so children become visible.
            try:
                self.pipeline_video_tree.item(item_id, open=True)
            except Exception:
                pass

            for child in self.pipeline_video_tree.get_children(item_id):
                if child in self.pipeline_video_vars:
                    add_subject(child)
                else:
                    collect_descendants(child)

        for item in selected_items:
            if item in self.pipeline_video_vars:
                add_subject(item)
            else:
                had_hierarchy_nodes = True
                collect_descendants(item)

        if had_hierarchy_nodes or len(final_selection) != len(selected_items):
            # Replace Treeview selection with the resolved subject entries only.
            try:
                self.pipeline_video_tree.selection_set(tuple(final_selection))
            except Exception:
                pass

        return final_selection

    def _resolve_processing_reports_video_paths(self, selection: Iterable[str] | None) -> list[str]:
        """Translate unified tab selections into concrete video paths."""
        if not selection:
            return []

        widget = getattr(self, "processing_reports_widget", None)
        tree = getattr(widget, "tree", None)
        if not tree:
            return []

        metadata_store = getattr(self, "_processing_reports_tree_metadata", {})
        context = _VideoPathResolverContext(tree, metadata_store)

        for item_id in selection:
            if not item_id or not tree.exists(item_id):
                continue
            context.process_item(item_id)

        context.update_tree_selection()
        return context.final_paths

    def _on_pipeline_selection_changed(self, event=None) -> None:
        del event
        selections = self._get_selected_pipeline_video_paths()
        listed = len(self.pipeline_video_vars)

        if self.pipeline_selection_label:
            if not selections:
                if listed == 0:
                    text = "Nenhum vídeo elegível listado."
                else:
                    text = f"{listed} vídeo(s) elegível(is). Selecione itens para ações."
            else:
                text = f"{listed} vídeo(s) elegível(is) • {len(selections)} selecionado(s)."
            self.pipeline_selection_label.config(text=text)

        self._update_pipeline_buttons_state(selections)

    def _update_pipeline_buttons_state(self, selections=None) -> None:
        if not self.pipeline_action_buttons:
            return
        if selections is None:
            selections = self._get_selected_pipeline_video_paths()

        has_selection = bool(selections)
        for button in self.pipeline_action_buttons.values():
            button.config(state="normal" if has_selection else "disabled")

        if has_selection:
            all_have_trajectory = all(
                bool(self.pipeline_video_vars.get(path, {}).get("info", {}).get("has_trajectory"))
                for path in selections
            )
            self.pipeline_action_buttons["summaries"].config(
                state="normal" if all_have_trajectory else "disabled"
            )

    def _trigger_batch_trajectory_processing(self, selection: Iterable[str] | None = None) -> None:
        if selection is None:
            selections = self._get_selected_pipeline_video_paths()
            if not selections:
                pipeline_vars = getattr(self, "pipeline_video_vars", {}) or {}
                if not pipeline_vars:
                    self.show_info(
                        "Processamento",
                        "Nenhum vídeo elegível foi encontrado com arena válida.",
                    )
                    return
                selections = list(pipeline_vars.keys())
        else:
            selections = self._resolve_processing_reports_video_paths(selection)
            if not selections:
                self.show_info(
                    "Processamento",
                    "Selecione vídeos com arena e ROIs definidas para gerar trajetórias.",
                )
                return

        unique_paths = list(dict.fromkeys(selections))
        if not unique_paths:
            return

        self.event_dispatcher.publish_event(
            Events.PROJECT_PROCESS_VIDEOS, {"video_paths": unique_paths}
        )
        self._request_overview_refresh()
        # Switch to analysis tab to show progress of the newly requested batch.
        self._switch_to_analysis_view()

    def _trigger_parquet_summaries(self) -> None:
        selections = self._get_selected_pipeline_video_paths()
        if not selections:
            self.show_info(
                "Sumários",
                "Selecione ao menos um vídeo com trajetória para exportar o sumário.",
            )
            return

        self.event_dispatcher.publish_event(
            Events.PROJECT_GENERATE_SUMMARIES, {"video_paths": selections}
        )
        self._refresh_pipeline_video_table()

    def _refresh_zone_indicators(self, videos=None) -> None:
        """Refresh zone indicators. Delegates to ProjectViewManager."""
        return self.project_view_manager._refresh_zone_indicators(videos)

    def _create_analysis_tab_widget(self):
        """Creates the analysis tab. Delegates to WidgetFactory."""
        return self.widget_factory.create_analysis_tab_widget()

    def _create_scrollable_controls_frame(self, parent):
        """Create a scrollable frame. Delegates to WidgetFactory."""
        return self.widget_factory.create_scrollable_controls_frame(parent)

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
        self.roi_canvas.delete("background_image")

        # Center the image in the new canvas size
        center_x = canvas_width // 2
        center_y = canvas_height // 2

        # Update stored position
        self._canvas_bg_position = (center_x, center_y, "center")

        # Create the centered image
        self.roi_canvas.create_image(
            center_x,
            center_y,
            anchor="center",
            image=self._canvas_bg_image,
            tags="background_image",
        )

    def _on_roi_rule_change(self, event=None):
        """Handle ROI inclusion rule change and update UI. Delegates to WidgetFactory."""
        rule = self.roi_inclusion_rule_var.get()
        return self.widget_factory.update_roi_rule_ui(rule)

    def _on_apply_roi_settings(self):
        """Apply ROI inclusion rule settings to the global settings."""
        try:
            # Validate and convert parameters
            buffer_radius = float(self.roi_buffer_radius_var.get())
            overlap_ratio = float(self.roi_overlap_ratio_var.get())

            # Validate ranges
            if buffer_radius < 0:
                raise ValueError("Raio de buffer deve ser >= 0")
            if not (0 <= overlap_ratio <= 1):
                raise ValueError("Fração de sobreposição deve estar entre 0 e 1")

            # Update settings if available
            if self.controller.settings:
                self.controller.settings.roi_inclusion_rule = self.roi_inclusion_rule_var.get()
                self.controller.settings.roi_buffer_radius_value = buffer_radius
                self.controller.settings.roi_min_bbox_overlap_ratio = overlap_ratio

                # Save to project if available
                if self.controller.project_manager.project_path:
                    self.controller.project_manager._save_settings_snapshot()

                self.show_info(
                    "Sucesso",
                    f"Configurações de ROI aplicadas:\n"
                    f"Regra: {self.controller.settings.roi_inclusion_rule}\n"
                    f"Raio buffer: {self.controller.settings.roi_buffer_radius_value}\n"
                    f"Sobreposição mínima: {self.controller.settings.roi_min_bbox_overlap_ratio}",
                )
            else:
                self.show_warning(
                    "Aviso", "Settings não disponível. Configurações não foram salvas."
                )

        except ValueError as e:
            self.show_error("Erro de Validação", str(e))
        except Exception as e:
            self.show_error("Erro", f"Erro ao aplicar configurações: {e!s}")

    def setup_interactive_polygon(self, polygon: np.ndarray):
        """Draws a suggested polygon that the user can interactively edit."""
        # Garante que há frame no canvas antes de desenhar
        if self._canvas_bg_image is None:
            if not self.canvas_manager.load_video_frame_to_canvas():
                self.show_error(
                    "Erro",
                    "Não foi possível carregar um frame para mostrar o polígono detectado.",
                )
                return

        self._clear_interactive_polygon()  # Clear any previous one
        self.edited_polygon_points = [list(p) for p in polygon]

        self.canvas_manager._draw_interactive_polygon()

        # Show the save/discard buttons using component method
        if hasattr(self, "zone_controls") and self.zone_controls:
            self.zone_controls.show_interactive_buttons()
        elif self.interactive_buttons_frame:
            # Fallback for legacy code
            self.interactive_buttons_frame.pack(
                fill="x", padx=5, pady=5, before=self.roi_inclusion_frame
            )

        self.set_status("Ajuste o polígono arrastando os vértices. Salve ou descarte.")


    def _on_handle_press(self, event, handle_index):
        """Records which handle is being dragged and initial offset."""
        self._dragged_handle_index = handle_index

        # Store the initial mouse position and handle position
        self._drag_start_mouse = (float(event.x), float(event.y))

        # Get current handle position in video coordinates
        video_point = self.edited_polygon_points[handle_index]
        # Convert to canvas coordinates
        canvas_point = self.canvas_manager._video_to_canvas(video_point[0], video_point[1])
        self._drag_start_handle = canvas_point

        # Calculate offset between mouse and handle center
        self._drag_offset = (canvas_point[0] - event.x, canvas_point[1] - event.y)

        # Bind motion and release to the entire canvas so events continue even
        # when mouse leaves the handle
        self.roi_canvas.bind("<B1-Motion>", self._on_handle_drag_global)
        self.roi_canvas.bind("<ButtonRelease-1>", self._on_handle_release_global)

    def _on_handle_drag(self, event):
        """Updates polygon point and redraws. Delegates to CanvasManager."""
        return self.canvas_manager.handle_vertex_drag(event)

    def _on_handle_drag_global(self, event):
        """Global drag handler for canvas-wide dragging."""
        self._on_handle_drag(event)

    def _on_handle_release(self, event):
        """Finalizes the drag operation (called from tag binding)."""
        self._handle_release_common()

    def _on_handle_release_global(self, event):
        """Global release handler (called from canvas binding)."""
        # Unbind global handlers
        self.roi_canvas.unbind("<B1-Motion>")
        self.roi_canvas.unbind("<ButtonRelease-1>")
        self._handle_release_common()

    def _handle_release_common(self):
        """Common release logic."""
        self._dragged_handle_index = None
        self._drag_offset = (0, 0)

    def _on_save_arena(self):
        """Saves the edited polygon and makes it static."""
        if self.current_editing_zone == "arena":
            # Save main arena
            self.event_dispatcher.publish_event(
                Events.ZONE_SAVE_MANUAL_ARENA,
                {"polygon_points": self.edited_polygon_points},
            )
            status_message = "Arena principal salva com sucesso."
            self.set_status(status_message)
            # Enable ROI button after main arena is saved
            self._enable_roi_button_if_arena_exists()
            self._request_overview_refresh(reason=status_message, append_summary=True)
        elif isinstance(self.current_editing_zone, tuple) and self.current_editing_zone[0] == "roi":
            # Save ROI
            _, roi_index, roi_name = self.current_editing_zone
            zone_data = self._get_zone_data_for_active_context()

            # Update the ROI polygon
            zone_data.roi_polygons[roi_index] = self.edited_polygon_points

            # Save to project using new zone persistence helper
            self.controller.project_manager.save_zone_data(zone_data)

            status_message = f"ROI '{roi_name}' salva com sucesso."
            self.set_status(status_message)
            self._request_overview_refresh(reason=status_message, append_summary=True)
        else:
            # Fallback - assume arena (legacy behavior)
            self.controller.save_manual_arena(self.edited_polygon_points)
            status_message = "Zona salva com sucesso."
            self.set_status(status_message)
            # Enable ROI button after main arena is saved
            self._enable_roi_button_if_arena_exists()
            self._request_overview_refresh(reason=status_message, append_summary=True)

        # Clear interactive elements and redraw zones
        self._clear_interactive_polygon()
        self.canvas_manager.redraw_zones_from_project_data()
        self.update_zone_listbox()
        self._refresh_zone_indicators()

    def _on_discard_arena(self):
        """Discards the interactive polygon."""
        self._clear_interactive_polygon()
        if self.current_editing_zone == "arena":
            self.set_status("Edição da arena descartada.")
        elif isinstance(self.current_editing_zone, tuple) and self.current_editing_zone[0] == "roi":
            _, _, roi_name = self.current_editing_zone
            self.set_status(f"Edição da ROI '{roi_name}' descartada.")
        else:
            self.set_status("Edição descartada.")

        # Redraw zones to restore original state
        self.canvas_manager.redraw_zones_from_project_data()

    def _clear_interactive_polygon(self):
        """Clears all interactive elements from the canvas and hides buttons."""
        self.roi_canvas.delete("interactive_polygon", "handle", "suggested_polygon")
        try:
            if self.interactive_buttons_frame and self.interactive_buttons_frame.winfo_exists():
                self.interactive_buttons_frame.pack_forget()
        except Exception:
            # This can fail if the root window is already being destroyed.
            # It's safe to ignore in that case.
            pass

        self.interactive_polygon_item = None
        self.polygon_handles = []
        self.edited_polygon_points = []
        self._dragged_handle_index = None
        self._drag_offset = (0, 0)
        self.current_editing_zone = None



    def _video_sort_key(self, value):
        """Get video sort key. Delegates to ProjectViewManager."""
        return self.project_view_manager._video_sort_key(value)

    def _format_subject_label(self, value):
        """Format subject label. Delegates to ProjectViewManager."""
        return self.project_view_manager._format_subject_label(value)

    @staticmethod
    def _format_day_display(value):
        if value in (None, ""):
            return ""
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            try:
                return f"{int(value):02d}"
            except (TypeError, ValueError):
                return str(value)
        value_str = str(value).strip()
        if not value_str:
            return ""
        lower_value = value_str.lower()
        if lower_value == "sem dia":
            return "Sem Dia"
        match = re.search(r"(\d+)", value_str)
        if match:
            try:
                return f"{int(match.group(1)):02d}"
            except ValueError:
                return value_str
        return value_str

    def _build_day_title(self, day_value, metadata: dict | None = None) -> str:
        """Build day title. Delegates to ProjectViewManager."""
        return self.project_view_manager._build_day_title(day_value, metadata)

    def _build_video_hierarchy_data(
        self,
        all_videos: list[dict],
        search_text: str,
    ) -> dict[str, dict]:
        """Build video hierarchy data. Delegates to ProjectViewManager."""
        return self.project_view_manager._build_video_hierarchy_data(all_videos, search_text)

    def _build_video_hierarchy_snapshot(self) -> list[dict]:
        """Build video hierarchy snapshot. Delegates to ValidationManager."""
        return self.validation_manager.build_video_hierarchy_snapshot()

    def _format_status_token(self, has_parquet: bool, symbol_key: str) -> str:
        """Format status token. Delegates to ValidationManager."""
        return self.validation_manager.format_status_token(has_parquet, symbol_key)

    def _populate_video_selector_tree(self, filter_text: str | None = None):
        """Populate video selector tree. Delegates to ProjectViewManager."""
        return self.project_view_manager._populate_video_selector_tree(filter_text)

    def _refresh_video_selector_tree(self) -> None:
        """Repopula a árvore mantendo seleção e filtros atuais sempre que possível."""

        if not self.video_selector_tree:
            return

        selected_tag = None
        selection = self.video_selector_tree.selection()
        if selection:
            try:
                tags = self.video_selector_tree.item(selection[0], "tags")
                if tags:
                    selected_tag = tags[0]
            except Exception:
                selected_tag = None

        current_filter = getattr(self, "_video_selector_filter", "")
        self._populate_video_selector_tree(current_filter)

        if selected_tag:
            self._reselect_video_tree_item(selected_tag)

    def _reselect_video_tree_item(self, target_tag: str) -> None:
        if not target_tag or not self.video_selector_tree:
            return

        def _walk(node: str) -> bool:
            for child in self.video_selector_tree.get_children(node):
                tags = self.video_selector_tree.item(child, "tags")
                if tags and tags[0] == target_tag:
                    # Ensure branch is visible before selecting
                    parent = self.video_selector_tree.parent(child)
                    while parent:
                        self.video_selector_tree.item(parent, open=True)
                        parent = self.video_selector_tree.parent(parent)

                    self.video_selector_tree.selection_set(child)
                    self.video_selector_tree.see(child)
                    return True

                if _walk(child):
                    return True
            return False

        _walk("")

    def _filter_video_tree(self):
        """Filtra a árvore com base no texto de busca."""
        if self.video_search_var is None:
            return
        self._populate_video_selector_tree(self.video_search_var.get())

    def apply_pending_readiness_snapshot(
        self,
        *,
        ready_with_trajectory: list[dict],
        ready_with_zones: list[dict],
        arena_only: list[dict],
        without_arena: list[dict],
    ) -> None:
        mapping: dict[str, tuple[str, ...]] = {}

        def _assign(entries: list[dict], *tags: str) -> None:
            for info in entries or []:
                path = info.get("path")
                if path:
                    mapping[path] = tuple(tags)

        _assign(ready_with_trajectory, "ready_full")
        _assign(ready_with_zones, "ready_partial")
        _assign(arena_only, "ready_optional", "ready_partial")
        _assign(without_arena, "ready_missing")

        self._pending_readiness_snapshot = mapping

        if self.video_selector_tree:
            self._populate_video_selector_tree(self._video_selector_filter)

    def _load_selected_video_frame(self, event=None):
        """Carrega o frame do vídeo selecionado no canvas principal."""

        if not self.video_selector_tree:
            return

        selection = self.video_selector_tree.selection()
        if not selection:
            self.show_warning(
                "Nenhum Vídeo Selecionado",
                "Por favor, selecione um vídeo da lista para carregar.",
            )
            return

        item_id = selection[0]
        tags = self.video_selector_tree.item(item_id, "tags")

        if not tags or not tags[0]:
            self.show_info(
                "Selecione um Vídeo",
                ("Por favor, escolha um item com ícone de peixe (🐟) para carregar o frame."),
            )
            return

        video_path = tags[0]
        success = self.canvas_manager.load_video_frame_to_canvas(video_path, frame_number=0)

        if success:
            self._maybe_offer_zone_reuse(video_path)
            self.canvas_manager.redraw_zones_from_project_data()
            filename = os.path.basename(video_path)
            self.set_status(f"✓ Frame carregado: {filename}")
            log.info("gui.video_selector.frame_loaded", path=video_path)
        else:
            self.show_error(
                "Erro ao Carregar",
                f"Não foi possível carregar o vídeo selecionado.\n{video_path}",
            )

    def _maybe_offer_zone_reuse(self, video_path: str) -> None:
        """Prompt user to reuse zones when current video has none. Delegates to DialogManager."""
        return self.dialog_manager.offer_zone_reuse(video_path)

    def _on_video_tree_double_click(self, event):
        """Callback para duplo clique no seletor de vídeos."""
        del event  # Evento não é utilizado diretamente
        self._load_selected_video_frame()


    def _create_processing_reports_tab(self) -> None:
        """Creates the processing reports tab. Delegates to WidgetFactory."""
        return self.widget_factory.create_processing_reports_tab()

    def _on_processing_reports_item_double_click(self, event=None) -> None:
        """Handle double-click on items in the Processing Reports tree."""
        if not self.processing_reports_widget or not self.processing_reports_widget.tree:
            return

        tree = self.processing_reports_widget.tree

        # Get item at click position
        item_id = None
        if event is not None:
            item_id = tree.identify_row(event.y)
        if not item_id:
            selection = tree.selection()
            if selection:
                item_id = selection[0]
        if not item_id:
            return

        metadata = self._processing_reports_tree_metadata.get(item_id)
        if not metadata:
            return

        node_type = metadata.get("type")

        # Handle file nodes (docx/xlsx) - open them
        if node_type == "file":
            self._handle_report_file_node(metadata)
            return

        # Handle video nodes - open results folder
        if node_type == "video":
            results_dir = metadata.get("results_dir")
            if results_dir and os.path.exists(results_dir):
                log.info("gui.open_results_folder", path=results_dir)
                try:
                    if os.name == "nt":  # Windows
                        os.startfile(results_dir)
                    elif os.name == "posix":  # macOS, Linux
                        import subprocess

                        subprocess.Popen(["xdg-open", results_dir])
                except Exception as e:
                    log.error("gui.open_results_folder.failed", error=str(e))
                    self.show_error("Erro", f"Não foi possível abrir a pasta: {e}")

    def _on_processing_reports_generate_partial(self) -> None:
        """Handle partial report generation from the unified tab."""
        if not self.processing_reports_widget:
            return

        selection = self.processing_reports_widget.get_selection()
        if not selection:
            return

        selected_videos = []
        all_videos = self.controller.project_manager.get_all_videos()
        metadata_store = getattr(self, "_processing_reports_tree_metadata", {})

        for item_id in selection:
            metadata = metadata_store.get(item_id)
            if not metadata or metadata.get("type") != "video":
                continue
            video_path = metadata.get("video_path")
            if not video_path:
                continue
            for video_data in all_videos:
                if video_data["path"] == video_path:
                    selected_videos.append(video_data)
                    break

        if selected_videos:
            self.event_dispatcher.publish_event(
                Events.REPORT_GENERATE,
                {"videos": selected_videos, "report_type": "partial"},
            )

    def _refresh_processing_reports_tab(self) -> None:
        """Refresh the processing reports tab. Delegates to ProjectViewManager."""
        return self.project_view_manager._refresh_processing_reports_tab()

    def _determine_status_tag(self, complete_count: int, total_count: int) -> str:
        """Determine status tag. Delegates to ProjectViewManager."""
        return self.project_view_manager._determine_status_tag(complete_count, total_count)

    def _build_processing_report_artifact_id(self, parent_id: str, artifact_path: str) -> str:
        """Create a stable item id for report artifacts while avoiding duplicates."""
        digest_source = f"{parent_id}|{artifact_path}".encode("utf-8", "ignore")
        digest = hashlib.sha1(digest_source).hexdigest()[:16]
        return f"file_{digest}"

    def _sort_key_for_reports(self, value):
        """Sort key for reports. Delegates to ProjectViewManager."""
        return self.project_view_manager._sort_key_for_reports(value)

    def _format_subject_for_reports(self, value):
        """Format subject for reports. Delegates to ValidationManager."""
        return self.validation_manager.format_subject_for_reports(value)

    def _build_report_hierarchy(self, all_videos: list[dict], pm) -> dict:
        """Build report hierarchy. Delegates to ProjectViewManager."""
        return self.project_view_manager._build_report_hierarchy(all_videos, pm)

    def _populate_reports_tree_from_hierarchy(self, hierarchy: dict, pm) -> None:
        """Populate reports tree. Delegates to ProjectViewManager."""
        return self.project_view_manager._populate_reports_tree_from_hierarchy(hierarchy, pm)

    def _append_report_artifacts(self, parent_id: str, entry: dict) -> None:
        """Append report artifacts to tree. Delegates to ProjectViewManager."""
        return self.project_view_manager.append_report_artifacts_from_entry(parent_id, entry)

    def _on_report_item_select(self, event=None):
        """Enables or disables the partial report button based on selection."""
        selection = self.reports_tree.selection()
        has_video = False
        metadata_store = getattr(self, "_report_tree_metadata", {})
        for item_id in selection:
            metadata = metadata_store.get(item_id)
            if metadata and metadata.get("type") == "video":
                has_video = True
                break

        if has_video:
            self.generate_partial_report_btn.config(state="normal")
        else:
            self.generate_partial_report_btn.config(state="disabled")

    def _on_report_item_double_click(self, event=None):
        """Open the results folder for the selected video when reports exist."""
        tree = getattr(self, "reports_tree", None)
        if not tree:
            return

        item_id = None
        if event is not None:
            item_id = tree.identify_row(event.y)
        if not item_id:
            selection = tree.selection()
            if selection:
                item_id = selection[0]
        if not item_id:
            return

        metadata_store = getattr(self, "_report_tree_metadata", {})
        metadata = metadata_store.get(item_id)
        if not metadata:
            return

        node_type = metadata.get("type")

        if node_type == "file":
            self._handle_report_file_node(metadata)
            return

        if node_type != "video":
            return

        self._handle_report_video_node(metadata)

    def _handle_report_file_node(self, metadata: dict) -> None:
        artifact_path = metadata.get("path")
        if artifact_path and os.path.exists(artifact_path):
            self._open_path_in_explorer(artifact_path)
        else:
            self.show_warning(
                "Arquivo não encontrado",
                (
                    "O relatório selecionado não foi localizado no disco. Gere "
                    "novamente o relatório para restaurar o arquivo."
                ),
            )

    def _handle_report_video_node(self, metadata: dict) -> None:
        """Handle report video node. Delegates to ProjectViewManager."""
        return self.project_view_manager.handle_report_video_node(metadata)

    def _open_path_in_explorer(self, target_path: str) -> None:
        """Open the given directory in the user's file explorer."""
        try:
            if sys.platform.startswith("win"):
                os.startfile(target_path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", target_path])
            else:
                subprocess.Popen(["xdg-open", target_path])
        except Exception as exc:  # pragma: no cover - GUI feedback
            self.show_error(
                "Erro ao abrir pasta",
                (
                    "Não foi possível abrir o diretório de resultados.\n"
                    f"Caminho: {target_path}\n\nDetalhes: {exc}"
                ),
            )

    def _generate_partial_report(self):
        """
        Gathers selected videos and tells the controller to generate a partial report.
        """
        selected_items = self.reports_tree.selection()
        if not selected_items:
            return

        selected_videos = []
        all_videos = self.controller.project_manager.get_all_videos()
        metadata_store = getattr(self, "_report_tree_metadata", {})

        for item_id in selected_items:
            if not self.reports_tree.exists(item_id):
                continue
            metadata = metadata_store.get(item_id)
            if not metadata or metadata.get("type") != "video":
                continue
            video_path = metadata.get("video_path")
            if not video_path:
                continue
            for video_data in all_videos:
                if video_data["path"] == video_path:
                    selected_videos.append(video_data)
                    break

        if selected_videos:
            self.event_dispatcher.publish_event(
                Events.REPORT_GENERATE,
                {"videos": selected_videos, "report_type": "partial"},
            )

    def _generate_unified_report(self):
        """Tells the controller to generate a unified report of all project videos."""
        all_videos = self.controller.project_manager.get_all_videos()
        if not all_videos:
            self.show_warning(
                "Sem Dados",
                "Não há vídeos processados neste projeto para gerar um relatório.",
            )
            return
        self.event_dispatcher.publish_event(
            Events.REPORT_GENERATE,
            {"videos": all_videos, "report_type": "unified"},
        )

    def _start_main_arena_drawing(self):
        """Starts drawing the main arena polygon."""
        # Prevent editing during analysis
        if self.analysis_active:
            self.show_warning(
                "Análise em Progresso",
                "Não é possível editar zonas durante a análise de vídeo.",
            )
            return

        self.current_drawing_type = "arena"

        self._start_polygon_drawing()

    def _start_roi_drawing(self):
        """Starts drawing an ROI polygon, checking if an arena exists first."""
        # Prevent editing during analysis
        if self.analysis_active:
            self.show_warning(
                "Análise em Progresso",
                "Não é possível editar zonas durante a análise de vídeo.",
            )
            return

        main_arena = self._get_zone_data_for_active_context().polygon
        if not main_arena:
            self.show_error(
                "Erro",
                "Por favor, defina o 'Polígono Principal' primeiro antes de "
                "adicionar Áreas de Interesse.",
            )
            return
        self.current_drawing_type = "roi"
        self._start_polygon_drawing()

    def _start_polygon_drawing(self):
        """Activates polygon drawing mode. Delegates to CanvasManager."""
        return self.canvas_manager.start_polygon_drawing()

    def _stop_drawing(self):
        """Deactivates any drawing mode and unbinds all associated events."""
        # Destroy the instruction label if it exists
        if self.drawing_instruction_label:
            self.drawing_instruction_label.destroy()
            self.drawing_instruction_label = None

        # Destroy floating drawing buttons if they exist
        if self._drawing_buttons_frame:
            self._drawing_buttons_frame.destroy()
            self._drawing_buttons_frame = None

        self.drawing_mode = None
        self.current_drawing_type = None
        self.roi_canvas.config(cursor="")
        # Unbind all possible drawing events
        self.roi_canvas.unbind("<Button-1>")
        self.roi_canvas.unbind("<Double-Button-1>")
        self.roi_canvas.unbind("<Motion>")
        self.roi_canvas.unbind("<ButtonPress-1>")
        self.roi_canvas.unbind("<B1-Motion>")
        self.roi_canvas.unbind("<ButtonRelease-1>")
        # Unbind keyboard shortcuts
        self.roi_canvas.unbind("<Control-z>")
        self.roi_canvas.unbind("<Control-y>")
        self.roi_canvas.unbind("<Control-Shift-Z>")

        self.roi_canvas.delete("elastic_line")
        self.roi_canvas.delete("drawing_aid")  # Deletes both vertices and fixed lines
        self.roi_canvas.delete("snap_indicator")  # Clear snap indicators

        # Clear coordinate lists
        self.current_polygon_points = []
        self._poly_pts_canvas = []
        self._poly_pts_video = []

        self.set_status("Pronto.")

    def _create_drawing_buttons(self):
        """Creates floating undo/redo buttons over the canvas."""
        if self._drawing_buttons_frame:
            self._drawing_buttons_frame.destroy()

        # Create a frame that floats over the canvas (top-right corner)
        self._drawing_buttons_frame = ttk.Frame(self.viz_frame, relief="raised", borderwidth=2)

        # Undo button
        undo_btn = ttk.Button(
            self._drawing_buttons_frame,
            text="↶ Desfazer (Ctrl+Z)",
            command=lambda: self._on_drawing_undo(None),
            width=20,
        )
        undo_btn.pack(side="left", padx=2)

        # Redo button
        redo_btn = ttk.Button(
            self._drawing_buttons_frame,
            text="↷ Refazer (Ctrl+Y)",
            command=lambda: self._on_drawing_redo(None),
            width=20,
        )
        redo_btn.pack(side="left", padx=2)

        # Position the frame in top-right corner of canvas
        self._drawing_buttons_frame.place(relx=1.0, rely=0.0, anchor="ne", x=-10, y=10)

    def _on_drawing_undo(self, event):
        """Undo last point added to polygon."""
        if self.drawing_mode != "polygon" or not self._poly_pts_canvas:
            return "break"  # Prevent event propagation

        # Save current state to redo stack before undoing
        self._drawing_redo_stack.append(
            (
                self._poly_pts_canvas[-1],
                self._poly_pts_video[-1],
                self.current_polygon_points[-1],
            )
        )

        # Remove last point
        self._poly_pts_canvas.pop()
        self._poly_pts_video.pop()
        self.current_polygon_points.pop()

        # Redraw the polygon
        self.canvas_manager._redraw_polygon_in_progress()

        self.set_status(f"Último ponto desfeito. Pontos atuais: {len(self.current_polygon_points)}")
        return "break"

    def _on_drawing_redo(self, event):
        """Redo last undone point."""
        if self.drawing_mode != "polygon" or not self._drawing_redo_stack:
            return "break"

        # Restore point from redo stack
        canvas_pt, video_pt, current_pt = self._drawing_redo_stack.pop()
        self._poly_pts_canvas.append(canvas_pt)
        self._poly_pts_video.append(video_pt)
        self.current_polygon_points.append(current_pt)

        # Redraw the polygon
        self.canvas_manager._redraw_polygon_in_progress()

        self.set_status(f"Ponto restaurado. Pontos atuais: {len(self.current_polygon_points)}")
        return "break"


    def _on_vertex_drag_motion(self, event):
        """Handle mouse motion while dragging a vertex."""
        if self._dragging_vertex_index is None:
            return

        canvas_x = float(event.x)
        canvas_y = float(event.y)

        # If drawing ROI, clamp position to arena
        if self.current_drawing_type == "roi":
            main_arena_poly = self._get_zone_data_for_active_context().polygon
            if main_arena_poly:
                canvas_arena_poly = []
                for point in main_arena_poly:
                    canvas_pt = self.canvas_manager._video_to_canvas(point[0], point[1])
                    canvas_arena_poly.append([canvas_pt[0], canvas_pt[1]])

                arena_array = np.array(canvas_arena_poly, dtype=np.float32)
                result = cv2.pointPolygonTest(arena_array, (canvas_x, canvas_y), True)

                if result < 0:
                    # Clamp to nearest arena boundary
                    min_dist = float("inf")
                    closest_point = (canvas_x, canvas_y)

                    for i in range(len(canvas_arena_poly)):
                        p1 = canvas_arena_poly[i]
                        p2 = canvas_arena_poly[(i + 1) % len(canvas_arena_poly)]

                        edge_snap = self.canvas_manager._point_to_segment_distance(
                            canvas_x, canvas_y, p1[0], p1[1], p2[0], p2[1]
                        )

                        if edge_snap and edge_snap["distance"] < min_dist:
                            min_dist = edge_snap["distance"]
                            closest_point = (edge_snap["x"], edge_snap["y"])

                    canvas_x, canvas_y = closest_point

        # Update vertex position
        self.current_polygon_points[self._dragging_vertex_index] = (canvas_x, canvas_y)
        self._poly_pts_canvas[self._dragging_vertex_index] = (canvas_x, canvas_y)
        video_pt = self.canvas_manager._canvas_to_video(canvas_x, canvas_y)
        self._poly_pts_video[self._dragging_vertex_index] = video_pt

        # Redraw polygon
        self.canvas_manager._redraw_polygon_in_progress()

    def _on_vertex_drag_end(self, event):
        """Handle mouse release after dragging a vertex."""
        if self._dragging_vertex_index is not None:
            self._dragging_vertex_index = None
            self.roi_canvas.config(cursor="crosshair")

    def _apply_snapping(self, canvas_x, canvas_y, exclude_current_polygon=False, snap_threshold=10):
        """
        Applies snapping to nearby vertices or edges of existing polygons.

        Args:
            canvas_x (float): X coordinate in canvas space
            canvas_y (float): Y coordinate in canvas space
            exclude_current_polygon (bool): If True, excludes the polygon
                currently being edited.
            snap_threshold (int): Maximum distance in pixels for snapping to occur

        Returns:
            tuple or None: (snapped_x, snapped_y) if snapping occurred, None otherwise
        """
        zone_data = self._get_zone_data_for_active_context()
        all_polygons = []

        # Add main arena polygon if it exists
        if zone_data.polygon:
            # Convert to canvas coordinates
            canvas_polygon = []
            for point in zone_data.polygon:
                canvas_pt = self.canvas_manager._video_to_canvas(point[0], point[1])
                canvas_polygon.append(canvas_pt)

            # Only add if not editing this polygon
            if not (exclude_current_polygon and self.current_editing_zone == "arena"):
                all_polygons.append(canvas_polygon)

        # Add all ROI polygons
        for idx, roi_polygon in enumerate(zone_data.roi_polygons):
            canvas_polygon = []
            for point in roi_polygon:
                canvas_pt = self.canvas_manager._video_to_canvas(point[0], point[1])
                canvas_polygon.append(canvas_pt)

            # Only add if not editing this specific ROI
            skip_this_roi = (
                exclude_current_polygon
                and isinstance(self.current_editing_zone, tuple)
                and self.current_editing_zone[0] == "roi"
                and self.current_editing_zone[1] == idx
            )
            if not skip_this_roi:
                all_polygons.append(canvas_polygon)

        # Find closest point
        closest_point = None
        min_distance = snap_threshold

        for polygon in all_polygons:
            # Check snapping to vertices
            for vertex in polygon:
                dist = np.sqrt((canvas_x - vertex[0]) ** 2 + (canvas_y - vertex[1]) ** 2)
                if dist < min_distance:
                    min_distance = dist
                    closest_point = vertex

            # Check snapping to edges
            for i in range(len(polygon)):
                p1 = polygon[i]
                p2 = polygon[(i + 1) % len(polygon)]

                # Calculate distance from point to line segment
                edge_snap = self.canvas_manager._point_to_segment_distance(
                    canvas_x, canvas_y, p1[0], p1[1], p2[0], p2[1]
                )

                if edge_snap and edge_snap["distance"] < min_distance:
                    min_distance = edge_snap["distance"]
                    closest_point = (edge_snap["x"], edge_snap["y"])

        anchors: list[tuple[float, float]] = [
            tuple(vertex) for polygon in all_polygons for vertex in polygon
        ]
        axis_centers: list[tuple[float, float]] = []

        if zone_data.polygon:
            centroid = polygon_centroid(zone_data.polygon)
            if centroid:
                axis_centers.append(self.canvas_manager._video_to_canvas(*centroid))

        for roi_polygon in zone_data.roi_polygons or []:
            centroid = polygon_centroid(roi_polygon)
            if centroid:
                axis_centers.append(self.canvas_manager._video_to_canvas(*centroid))

        axis_snap = snap_point_to_axes(
            (canvas_x, canvas_y),
            anchors=anchors,
            centers=axis_centers,
            threshold=float(snap_threshold),
        )

        if axis_snap is not None:
            axis_dist = np.sqrt((canvas_x - axis_snap[0]) ** 2 + (canvas_y - axis_snap[1]) ** 2)
            if axis_dist < min_distance:
                closest_point = axis_snap
                min_distance = axis_dist

        return closest_point

    def _refresh_roi_templates(self, clear_selection: bool = False) -> None:  # noqa: C901
        """Refresh template list. If clear_selection=True, always reset to blank."""
        pm = getattr(self.controller, "project_manager", None)
        if pm is None:
            return

        # Check if delete button exists, if not, create it dynamically
        if (
            not self.delete_template_btn
            and hasattr(self, "roi_template_combobox")
            and self.roi_template_combobox
        ):
            log.warning("gui.roi_templates.delete_button_missing_creating_now", has_combobox=True)
            # Find the template actions frame and create the button
            try:
                # Get the parent of the combobox
                template_selector = self.roi_template_combobox.master
                template_frame = template_selector.master

                # Look for or create template_actions frame
                template_actions = None
                for child in template_frame.winfo_children():
                    if isinstance(child, ttk.Frame) and child != template_selector:
                        # Check if this frame has buttons
                        for grandchild in child.winfo_children():
                            if isinstance(grandchild, ttk.Button):
                                template_actions = child
                                break
                        if template_actions:
                            break

                if template_actions:
                    # Create delete button
                    self.delete_template_btn = ttk.Button(
                        template_actions,
                        text="🗑️ Deletar Template",
                        command=self._on_delete_roi_template,
                        state="disabled",
                    )
                    self.delete_template_btn.pack(side="left", padx=(4, 0))
                    log.info("gui.roi_templates.delete_button_created_dynamically")
                else:
                    log.error("gui.roi_templates.could_not_find_template_actions_frame")
            except Exception as e:
                log.error("gui.roi_templates.failed_to_create_delete_button", error=str(e))

        try:
            templates = pm.list_roi_templates()
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("gui.roi_templates.refresh_failed", error=str(exc))
            templates = []

        enriched: list[dict[str, Any]] = []
        for template in templates:
            if not isinstance(template, dict):
                log.debug("gui.roi_templates.skipping_non_dict", template_type=type(template))
                continue

            # Validate template has a name
            template_name = template.get("name", "").strip()
            if not template_name:
                log.warning("gui.roi_templates.skipping_empty_name", template_data=template)
                continue

            # Validate file existence for file-based templates
            template_file = template.get("file")
            if template_file:
                from pathlib import Path

                # Try to fix common path issues
                original_file = str(template_file)
                fixed_file = original_file

                # Fix comma instead of dot in .zebtrack
                if "\\,zebtrack\\" in fixed_file or "/,zebtrack/" in fixed_file:
                    fixed_file = fixed_file.replace("\\,zebtrack\\", "\\.zebtrack\\")
                    fixed_file = fixed_file.replace("/,zebtrack/", "/.zebtrack/")
                    log.warning(
                        "gui.roi_templates.fixing_path_comma",
                        original=original_file,
                        fixed=fixed_file,
                    )
                    template["file"] = fixed_file
                    template_file = fixed_file

                # Check if file exists
                file_path = Path(template_file)
                if not file_path.exists():
                    log.warning(
                        "gui.roi_templates.skipping_missing_file",
                        name=template_name,
                        file=template_file,
                        file_exists=False,
                    )
                    continue

                # Verify it's actually readable
                try:
                    if not file_path.is_file():
                        log.warning(
                            "gui.roi_templates.skipping_not_a_file",
                            name=template_name,
                            file=template_file,
                        )
                        continue
                except Exception as e:
                    log.warning(
                        "gui.roi_templates.skipping_unreadable_file",
                        name=template_name,
                        file=template_file,
                        error=str(e),
                    )
                    continue

            entry = dict(template)
            entry["display_name"] = self._format_roi_template_display(entry)
            entry["identifier"] = self._build_roi_template_identifier(entry)

            # Validate display_name is not empty
            if not entry.get("display_name", "").strip():
                log.warning(
                    "gui.roi_templates.skipping_empty_display_name", name=template_name, entry=entry
                )
                continue

            enriched.append(entry)

        self._roi_templates_cache = enriched
        # Filter out any empty display names (extra safety)
        names = [
            entry["display_name"] for entry in enriched if entry.get("display_name", "").strip()
        ]

        log.info(
            "gui.roi_templates.refreshed",
            total_templates=len(templates),
            valid_templates=len(enriched),
            display_names=names,
        )

        if self.roi_template_combobox:
            self.roi_template_combobox.configure(values=names)

        # If clear_selection is requested
        if clear_selection:
            # If there are no templates, disable the combobox
            if not names and hasattr(self, "roi_template_combobox"):
                self.roi_template_var.set("")
                self.roi_template_combobox.configure(state="disabled")
                log.info("gui.roi_templates.combobox_disabled_no_templates")
            # If there's exactly one template, auto-select it
            elif len(names) == 1 and hasattr(self, "roi_template_combobox"):
                self.roi_template_combobox.configure(state="readonly")
                # Set directly to the template, don't clear first
                self.roi_template_var.set(names[0])
                log.info("gui.roi_templates.auto_selected_single_template", template_name=names[0])
            # If there are multiple templates, clear selection
            else:
                self.roi_template_var.set("")
                if hasattr(self, "roi_template_combobox"):
                    self.roi_template_combobox.configure(state="readonly")
                log.info(
                    "gui.roi_templates.combobox_enabled_multiple_templates",
                    template_count=len(names),
                    templates=names,
                )

            # Update button state after selection change
            self._update_delete_template_button_state()
            return

        # Enable combobox if there are templates
        if names and hasattr(self, "roi_template_combobox"):
            self.roi_template_combobox.configure(state="readonly")
        elif not names and hasattr(self, "roi_template_combobox"):
            self.roi_template_combobox.configure(state="disabled")

        # Auto-select if there's exactly one template available
        if len(names) == 1 and not self.roi_template_var.get():
            self.roi_template_var.set(names[0])
            log.info("gui.roi_templates.auto_selected_on_refresh", template_name=names[0])
            return

        # If current selection is no longer valid, clear it
        current_selection = self.roi_template_var.get()
        if current_selection and current_selection not in names:
            self.roi_template_var.set("")
            log.info(
                "gui.roi_templates.cleared_invalid_selection",
                old_selection=current_selection,
                valid_names=names,
            )

        # Update delete button state
        self._update_delete_template_button_state()

    def _on_save_roi_template(self) -> None:
        """Save ROI template. Delegates to WidgetFactory."""
        return self.widget_factory.save_roi_template()

    def _format_roi_template_display(self, template: dict[str, Any]) -> str:
        """Format ROI template display. Delegates to WidgetFactory."""
        return self.widget_factory.format_roi_template_display(template)

    def _build_roi_template_identifier(self, template: dict[str, Any]) -> str:
        """Build ROI template identifier. Delegates to WidgetFactory."""
        return self.widget_factory.build_roi_template_identifier(template)

    def _get_selected_roi_template(self) -> dict[str, Any] | None:
        """Get selected template. Delegates to WidgetFactory."""
        return self.widget_factory.get_selected_roi_template()

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
        """Select a template in the dropdown. Delegates to WidgetFactory."""
        return self.widget_factory.select_roi_template(metadata)

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
        """Delete the currently selected template. Delegates to WidgetFactory."""
        return self.widget_factory.delete_roi_template()

    def _on_import_roi_template(self) -> None:
        """Import a template file into the library (does not apply it)."""
        pm = getattr(self.controller, "project_manager", None)
        if pm is None:
            return

        file_path = filedialog.askopenfilename(
            title="Importar Template de ROI para Biblioteca",
            filetypes=[("Templates de ROI", "*.json"), ("Todos os arquivos", "*.*")],
        )
        if not file_path:
            return

        try:
            metadata = pm.import_roi_template(file_path)
        except Exception as exc:  # pragma: no cover - defensive
            log.error("gui.roi_templates.import_failed", error=str(exc), file=file_path)
            self.show_error("Erro ao importar", str(exc))
            return

        self._refresh_roi_templates()
        self._select_roi_template(metadata)
        template_name = metadata.get("name", Path(file_path).stem)
        message = (
            f"Template '{template_name}' adicionado à biblioteca.\n\n"
            "Use o botão 'Aplicar' para usar este template."
        )
        self.show_info("Template importado", message)

    def _on_import_and_apply_roi_template(self) -> None:
        """Import a template file and immediately apply it to current video."""
        pm = getattr(self.controller, "project_manager", None)
        if pm is None:
            return

        file_path = filedialog.askopenfilename(
            title="Importar e Aplicar Template de ROI",
            filetypes=[("Templates de ROI", "*.json"), ("Todos os arquivos", "*.*")],
        )
        if not file_path:
            return

        # Get active video context
        active_video = pm.get_active_zone_video()
        if not active_video:
            pending_video = getattr(self, "pending_single_video_path", None)
            if pending_video:
                try:
                    pm.set_active_zone_video(pending_video)
                except Exception as exc:  # pragma: no cover - defensive
                    log.warning(
                        "gui.roi_templates.activate_pending_failed",
                        error=str(exc),
                        video=pending_video,
                    )
                active_video = pm.get_active_zone_video() or pending_video

        if not active_video:
            self.show_warning(
                "Vídeo não selecionado",
                "Selecione um vídeo antes de aplicar o template.",
            )
            return

        try:
            # Load template directly from file
            import json

            with open(file_path, encoding="utf-8") as f:
                template_data = json.load(f)

            # Convert to ZoneData
            from zebtrack.core.detector import ZoneData

            template_zone = ZoneData(
                polygon=template_data.get("polygon"),
                roi_polygons=template_data.get("roi_polygons", []),
                roi_names=template_data.get("roi_names", []),
                roi_colors=template_data.get("roi_colors", []),
            )

            # Save to project
            pm.save_zone_data(
                template_zone,
                video_path=active_video,
                persist=bool(pm.project_path),
            )

            if active_video:
                pm.set_active_zone_video(active_video)

            self.controller.setup_detector_zones()

            log.info(
                "gui.roi_templates.imported_and_applied",
                video=active_video,
                file=file_path,
                polygon_points=len(template_zone.polygon or []),
                roi_count=len(template_zone.roi_polygons or []),
            )

        except Exception as exc:  # pragma: no cover - defensive
            log.error(
                "gui.roi_templates.import_and_apply_failed",
                error=str(exc),
                file=file_path,
            )
            self.show_error("Erro ao importar e aplicar", str(exc))
            return

        # Refresh UI
        self.canvas_manager.redraw_zones_from_project_data()
        self.update_zone_listbox()
        self._refresh_zone_indicators()
        self._enable_roi_button_if_arena_exists()

        # Import to library and update dropdown
        template_name = Path(file_path).stem
        try:
            metadata = pm.import_roi_template(file_path)
            self._refresh_roi_templates()
            self._select_roi_template(metadata)
            template_name = metadata.get("name", template_name)
            log.info(
                "gui.roi_templates.import_and_apply.library_updated", template_name=template_name
            )
        except Exception as exc:  # pragma: no cover - if import fails, we still applied
            log.warning(
                "gui.roi_templates.import_and_apply.library_import_failed",
                error=str(exc),
                template_name=template_name,
            )
            # Still refresh templates to update display
            self._refresh_roi_templates()

        self.show_info(
            "Template aplicado",
            f"As zonas foram atualizadas com o template '{template_name}'.",
        )

    def _update_delete_template_button_state(self) -> None:
        """Update the delete template button state based on selection."""
        if not self.delete_template_btn:
            return

        current_value = self.roi_template_var.get().strip()
        if current_value and self._get_selected_roi_template():
            self.delete_template_btn.config(state="normal")
        else:
            self.delete_template_btn.config(state="disabled")

    def _on_roi_template_var_changed(self, *args) -> None:
        """Trace callback: Log whenever roi_template_var changes."""
        current_value = self.roi_template_var.get()
        import traceback

        stack = "".join(traceback.format_stack()[-4:-1])  # Get calling context

        log.info(
            "gui.roi_template.var_changed",
            new_value=repr(current_value),
            new_value_length=len(current_value) if current_value else 0,
            call_stack=stack,
        )

        # Update delete button state when selection changes
        self._update_delete_template_button_state()

    def _on_template_combobox_changed(self, event=None) -> None:
        """Log when template selection changes in combobox."""
        current_value = self.roi_template_var.get()
        cache_entries = self._roi_templates_cache if hasattr(self, "_roi_templates_cache") else []

        log.info(
            "gui.roi_template.combobox_selection_changed",
            new_value=repr(current_value),
            new_value_stripped=repr(current_value.strip()) if current_value else None,
            new_value_length=len(current_value) if current_value else 0,
            cache_size=len(cache_entries),
            cache_display_names=[e.get("display_name") for e in cache_entries],
        )

    def _on_apply_roi_template(self) -> None:
        pm = getattr(self.controller, "project_manager", None)
        if pm is None:
            return

        # Detailed logging of current state
        current_var_value = self.roi_template_var.get()
        cache_entries = self._roi_templates_cache if hasattr(self, "_roi_templates_cache") else []

        log.info(
            "gui.roi_template.apply_attempt.initial_state",
            selected_value_raw=repr(current_var_value),
            selected_value_stripped=repr(current_var_value.strip()) if current_var_value else None,
            selected_value_length=len(current_var_value) if current_var_value else 0,
            cache_size=len(cache_entries),
            cache_display_names=[e.get("display_name") for e in cache_entries],
            cache_names=[e.get("name") for e in cache_entries],
        )

        selected_template = self._get_selected_roi_template()

        log.info(
            "gui.roi_template.apply_attempt.after_get",
            template_found=selected_template is not None,
            template_data=selected_template if selected_template else "NOT_FOUND",
        )

        if not selected_template:
            # More detailed error message
            if not current_var_value.strip() and cache_entries:
                # There are templates available but none selected
                error_msg = (
                    "Por favor, CLIQUE no template no menu dropdown para selecioná-lo.\n\n"
                    "Não basta apenas abrir o menu - você precisa clicar no nome do template.\n\n"
                    f"Templates disponíveis: {len(cache_entries)}\n"
                    f"  • {cache_entries[0].get('display_name') if cache_entries else 'N/A'}"
                )
                if len(cache_entries) == 1:
                    # Auto-select the only available template
                    self.roi_template_var.set(cache_entries[0].get("display_name", ""))
                    log.info(
                        "gui.roi_template.auto_selecting_on_apply",
                        template=cache_entries[0].get("display_name"),
                    )
                    # Try again now that we've selected it
                    self.root.after(100, self._on_apply_roi_template)
                    return
            else:
                cache_info = (
                    "\n".join(
                        [
                            (
                                f"  - '{e.get('display_name')}' "
                                f"(name: '{e.get('name')}', file: '{e.get('file')}')"
                            )
                            for e in cache_entries
                        ]
                    )
                    if cache_entries
                    else "  (vazio)"
                )

                error_msg = (
                    f"Template não encontrado ou inválido.\n\n"
                    f"Valor selecionado: '{current_var_value}'\n"
                    f"Templates disponíveis:\n{cache_info}"
                )

            log.error(
                "gui.roi_template.apply_failed_no_match",
                selected_value=current_var_value,
                available_display_names=[e.get("display_name") for e in cache_entries],
            )

            self.show_warning(
                "Nenhum template selecionado",
                error_msg,
            )
            return

        active_video = pm.get_active_zone_video()
        if not active_video:
            pending_video = getattr(self, "pending_single_video_path", None)
            if pending_video:
                try:
                    pm.set_active_zone_video(pending_video)
                except Exception as exc:  # pragma: no cover - defensive
                    log.warning(
                        "gui.roi_templates.activate_pending_failed",
                        error=str(exc),
                        video=pending_video,
                    )
                active_video = pm.get_active_zone_video() or pending_video

        if not active_video:
            self.show_warning(
                "Vídeo não selecionado",
                "Selecione um vídeo na lista antes de aplicar o template.",
            )
            return

        template_name = (
            selected_template.get("name") or selected_template.get("display_name") or "Template"
        )
        template_location = selected_template.get("location")
        template_file = selected_template.get("file")

        try:
            template_zone = pm.load_roi_template(
                selected_template.get("name", ""),
                location=template_location,
                file_path=template_file,
            )
            pm.save_zone_data(
                template_zone,
                video_path=active_video,
                persist=bool(pm.project_path),
            )

            if active_video:
                pm.set_active_zone_video(active_video)

            self.controller.setup_detector_zones()
            log.info(
                "gui.roi_templates.zone_applied",
                video=active_video,
                polygon_points=len(template_zone.polygon or []),
                roi_count=len(template_zone.roi_polygons or []),
            )
        except FileNotFoundError as exc:
            log.error(
                "gui.roi_templates.file_missing",
                template=template_name,
                error=str(exc),
            )
            self.show_error(
                "Arquivo não encontrado",
                (
                    "O arquivo associado ao template não foi encontrado. "
                    "Remova ou importe novamente o template."
                ),
            )
            self._refresh_roi_templates()
            return
        except Exception as exc:  # pragma: no cover - defensive
            log.error(
                "gui.roi_templates.apply_failed",
                error=str(exc),
                template=template_name,
            )
            self.show_error("Erro ao aplicar template", str(exc))
            return

        self.canvas_manager.redraw_zones_from_project_data()
        self.update_zone_listbox()
        self._refresh_zone_indicators()
        self._enable_roi_button_if_arena_exists()
        applied_zone = self._get_zone_data_for_active_context()
        log.info(
            "gui.roi_templates.post_refresh_state",
            polygon_points=len(applied_zone.polygon or []),
            roi_count=len(applied_zone.roi_polygons or []),
        )
        self.show_info(
            "Template aplicado",
            f"As zonas foram atualizadas com o template '{template_name}'.",
        )
        self.set_status(f"Template '{template_name}' aplicado ao vídeo em edição.")


    def _on_canvas_click(self, event):
        """Handles canvas clicks during polygon drawing. Delegates to CanvasManager."""
        return self.canvas_manager.handle_canvas_click(event)

    def _on_canvas_motion(self, event):
        """Handles mouse movement for drawing elastic lines."""
        if self.drawing_mode != "polygon":
            return

        self.roi_canvas.delete("elastic_line")
        self.roi_canvas.delete("snap_indicator")  # Clear previous snap indicator

        # Check for snapping
        canvas_x = float(event.x)
        canvas_y = float(event.y)
        snapped_point = self._apply_snapping(canvas_x, canvas_y)

        # Check if mouse is hovering over an existing vertex (from current polygon being drawn)
        self._vertex_hover_index = None
        hover_color = "cyan"  # Default color

        if self.current_polygon_points:
            for i, (vx, vy) in enumerate(self.current_polygon_points):
                dist = ((canvas_x - vx) ** 2 + (canvas_y - vy) ** 2) ** 0.5
                if dist <= self._vertex_hover_tolerance:
                    self._vertex_hover_index = i
                    hover_color = "orange"  # Change color when over vertex
                    # Use vertex position for display
                    display_x, display_y = vx, vy
                    break

        # Use snapped point if available and not hovering over vertex
        if self._vertex_hover_index is None:
            display_x = snapped_point[0] if snapped_point else canvas_x
            display_y = snapped_point[1] if snapped_point else canvas_y
        else:
            display_x, display_y = self.current_polygon_points[self._vertex_hover_index]

        # When drawing ROI, clamp the display indicator within the arena
        if self.current_drawing_type == "roi":
            main_arena_poly = self._get_zone_data_for_active_context().polygon
            if main_arena_poly:
                # Convert arena to canvas coordinates
                canvas_arena_poly = []
                for point in main_arena_poly:
                    canvas_pt = self.canvas_manager._video_to_canvas(point[0], point[1])
                    canvas_arena_poly.append([canvas_pt[0], canvas_pt[1]])

                arena_array = np.array(canvas_arena_poly, dtype=np.float32)

                # Test if display point is inside arena
                result = cv2.pointPolygonTest(arena_array, (display_x, display_y), True)

                # If outside arena (result < 0), clamp to nearest arena boundary
                if result < 0:
                    # Find the closest point on the arena boundary
                    min_dist = float("inf")
                    closest_point = (display_x, display_y)

                    # Check distance to each edge of the arena
                    for i in range(len(canvas_arena_poly)):
                        p1 = canvas_arena_poly[i]
                        p2 = canvas_arena_poly[(i + 1) % len(canvas_arena_poly)]

                        edge_snap = self.canvas_manager._point_to_segment_distance(
                            display_x, display_y, p1[0], p1[1], p2[0], p2[1]
                        )

                        if edge_snap and edge_snap["distance"] < min_dist:
                            min_dist = edge_snap["distance"]
                            closest_point = (edge_snap["x"], edge_snap["y"])

                    # Update display position to clamped point
                    display_x, display_y = closest_point

        # Draw snap indicator if snapping is active, hovering over vertex, or if we're drawing ROI
        # (to show the clamped position within arena)
        should_show_indicator = (
            snapped_point is not None
            or self._vertex_hover_index is not None
            or (
                self.current_drawing_type == "roi"
                and self._get_zone_data_for_active_context().polygon
            )
        )

        if should_show_indicator:
            # Draw a small circle to indicate snap point (color changes when over vertex)
            self.roi_canvas.create_oval(
                display_x - 5,
                display_y - 5,
                display_x + 5,
                display_y + 5,
                outline=hover_color,
                width=2,
                tags="snap_indicator",
            )

        # If no points yet, only show snap indicator
        if not self.current_polygon_points:
            return

        last_point = self.current_polygon_points[-1]
        first_point = self.current_polygon_points[0]

        # Line from last vertex to cursor (or snap point)
        self.roi_canvas.create_line(
            last_point[0],
            last_point[1],
            display_x,
            display_y,
            fill="yellow",
            dash=(4, 4),
            tags="elastic_line",
        )
        # Line from cursor (or snap point) to first vertex (if more than one
        # point exists)
        if len(self.current_polygon_points) > 1:
            self.roi_canvas.create_line(
                display_x,
                display_y,
                first_point[0],
                first_point[1],
                fill="yellow",
                dash=(4, 4),
                tags="elastic_line",
            )

    def _on_canvas_double_click(self, event):
        """Finaliza o desenho do polígono e o envia para o controlador."""
        # Fix: Auto-detect drawing type if not set (for single video workflow)
        if self.current_drawing_type is None and self.drawing_mode == "polygon":
            # If no main arena exists, assume we're drawing it
            zone_data = self._get_zone_data_for_active_context()
            if not zone_data.polygon:
                self.current_drawing_type = "arena"
            else:
                self.current_drawing_type = "roi"

        if self.drawing_mode != "polygon" or len(self.current_polygon_points) < 3:
            if self.current_polygon_points:
                self.show_warning(
                    "Polígono Incompleto",
                    "Um polígono precisa de pelo menos 3 pontos. Você tem "
                    f"{len(self.current_polygon_points)} pontos.",
                )
            self._stop_drawing()
            return

        try:
            # Limpa elementos temporários de desenho ANTES de salvar
            self.roi_canvas.delete("elastic_line")
            self.roi_canvas.delete("drawing_aid")

            if self.current_drawing_type == "arena":
                # Salva o polígono no projeto
                success = self.controller.set_main_arena_polygon(
                    self._poly_pts_video  # Use video coordinates instead
                )

                if success:
                    # Agora redesenha tudo do zero com os dados salvos
                    # Não chame _stop_drawing() ainda, pois ele limpa o canvas
                    self.drawing_mode = None
                    self.current_drawing_type = None
                    self.roi_canvas.config(cursor="")

                    # Unbind eventos
                    self.roi_canvas.unbind("<Button-1>")
                    self.roi_canvas.unbind("<Double-Button-1>")
                    self.roi_canvas.unbind("<Motion>")

                    # Limpa label de instrução
                    if self.drawing_instruction_label:
                        self.drawing_instruction_label.destroy()
                        self.drawing_instruction_label = None

                    # Força redesenho com dados salvos
                    self.canvas_manager.redraw_zones_from_project_data()
                    self.update_zone_listbox()

                    status_message = "✓ Arena principal definida com sucesso!"
                    self.set_status(status_message)
                    self.show_info(
                        "Sucesso",
                        f"Arena principal criada com {len(self.current_polygon_points)} pontos.",
                    )
                    self._request_overview_refresh(reason=status_message, append_summary=True)
                else:
                    self.set_status("❌ Erro ao salvar arena principal.")
                    self.show_error("Erro", "Não foi possível salvar a arena principal.")
                    self._stop_drawing()

            elif self.current_drawing_type == "roi":
                roi_name = self.ask_string(
                    "Nome da ROI", "Digite um nome para esta nova Área de Interesse:"
                )
                if not roi_name:
                    self._stop_drawing()  # This now handles all cleanup
                    return

                # Selecionar cor da área
                color_dialog = ColorSelectionDialog(self.root)
                if not color_dialog.result:
                    self._stop_drawing()  # This now handles all cleanup
                    return

                selected_color = color_dialog.result
                roi_color = selected_color["rgb"]
                color_name = selected_color["name"]

                self.set_status(f"Salvando área de interesse '{roi_name}' ({color_name})...")
                success = self.controller.add_roi_polygon(
                    self._poly_pts_video,
                    roi_name,
                    roi_color,  # Use video coordinates
                )

                if success:
                    # Limpa o estado de desenho manualmente para ROI também
                    self.drawing_mode = None
                    self.current_drawing_type = None
                    self.roi_canvas.config(cursor="")

                    # Unbind eventos
                    self.roi_canvas.unbind("<Button-1>")
                    self.roi_canvas.unbind("<Double-Button-1>")
                    self.roi_canvas.unbind("<Motion>")

                    # Limpa label de instrução
                    if self.drawing_instruction_label:
                        self.drawing_instruction_label.destroy()
                        self.drawing_instruction_label = None

                    # Força redesenho com dados salvos
                    self.canvas_manager.redraw_zones_from_project_data()
                    self.update_zone_listbox()

                    status_message = (
                        f"✓ Área de Interesse '{roi_name}' ({color_name}) adicionada com sucesso!"
                    )
                    self.set_status(status_message)
                    self.show_info(
                        "Sucesso",
                        f"Área de interesse '{roi_name}' ({color_name}) criada com "
                        f"{len(self.current_polygon_points)} pontos.",
                    )
                    self._request_overview_refresh(reason=status_message, append_summary=True)
                else:
                    self.set_status(f"❌ Erro ao salvar área de interesse '{roi_name}'.")
                    self.show_error(
                        "Erro",
                        f"Não foi possível salvar a área de interesse '{roi_name}'.",
                    )
                    self._stop_drawing()

        except Exception as e:
            self.set_status("❌ Erro durante salvamento.")
            self.show_error("Erro", str(e))
            self._stop_drawing()

        finally:
            # Limpa pontos temporários
            self.current_polygon_points = []

    def update_zone_listbox(self, zone_data: ZoneData | None = None):
        """Update zone listbox. Delegates to CanvasManager."""
        return self.canvas_manager.update_zone_listbox(zone_data)

    def _enable_roi_button_if_arena_exists(self, zone_data: ZoneData | None = None):
        """Habilita o botão de desenhar ROI se a arena principal existir."""
        if zone_data is None:
            zone_data = self._get_zone_data_for_active_context()

        widget = getattr(self, "zone_controls", None)
        if widget:
            widget.set_draw_roi_enabled(bool(zone_data and zone_data.polygon))
            return

        if hasattr(self, "draw_roi_button") and self.draw_roi_button is not None:
            if zone_data and zone_data.polygon:
                self.draw_roi_button.config(state="normal")
            else:
                self.draw_roi_button.config(state="disabled")


    def _remove_selected_roi(self):
        """Removes the ROI selected in the listbox."""
        selected_items = self.roi_listbox.selection()
        if not selected_items:
            self.show_warning(
                "Nenhuma Seleção", "Por favor, selecione uma ROI da lista para remover."
            )
            return

        selected_arena_id = self.arena_selector_var.get()
        if not selected_arena_id or selected_arena_id not in self.roi_data:
            return  # Should not happen if an item is selected

        # Find the index and name of the item to remove
        selected_item = selected_items[0]
        item_index = self.roi_listbox.index(selected_item)

        # Remove from data source
        del self.roi_data[selected_arena_id][item_index]

        # Refresh the view
        self._on_arena_select()

    def _run_center_periphery_analysis(self):
        """Runs the center-periphery analysis."""
        current_arena_id = self.arena_selector_var.get()
        if not current_arena_id:
            self.show_error("Erro", "Selecione um aquário ativo e carregue os dados primeiro.")
            return

        dialog = CenterPeripheryDialog(self.root)
        if not dialog.result:
            return

        self.controller.run_center_periphery_analysis(
            arena_id=current_arena_id,
            method=dialog.result["method"],
            value=dialog.result["value"],
        )

    def _create_template_rois(self):
        """Opens a dialog to create ROIs from a template. Delegates to WidgetFactory."""
        return self.widget_factory.create_template_rois()

    def _start_circle_drawing(self):
        """Activates circle drawing mode."""
        self._stop_drawing()  # Ensure clean state
        self.drawing_mode = "circle"
        self.current_circle_center = None
        self.roi_canvas.config(cursor="crosshair")
        self.roi_canvas.bind("<ButtonPress-1>", self._on_canvas_press_circle)
        self.roi_canvas.bind("<B1-Motion>", self._on_canvas_drag_circle)
        self.roi_canvas.bind("<ButtonRelease-1>", self._on_canvas_release_circle)
        self.set_status("Modo de Desenho (Círculo): Clique e arraste para definir o raio.")

    def _on_canvas_press_circle(self, event):
        if self.drawing_mode != "circle":
            return
        self.current_circle_center = (event.x, event.y)

    def _on_canvas_drag_circle(self, event):
        if self.drawing_mode != "circle" or not self.current_circle_center:
            return

        self.roi_canvas.delete("elastic_line")
        cx, cy = self.current_circle_center
        radius = ((event.x - cx) ** 2 + (event.y - cy) ** 2) ** 0.5
        self.roi_canvas.create_oval(
            cx - radius,
            cy - radius,
            cx + radius,
            cy + radius,
            outline="yellow",
            dash=(4, 4),
            tags="elastic_line",
        )

    def _on_canvas_release_circle(self, event):
        if self.drawing_mode != "circle" or not self.current_circle_center:
            return

        cx, cy = self.current_circle_center
        radius = ((event.x - cx) ** 2 + (event.y - cy) ** 2) ** 0.5

        if radius < 2:  # Ignore tiny circles
            self._stop_drawing()
            return

        roi_name = self.ask_string(
            "Nome da ROI",
            "Digite um nome para esta nova Região de Interesse (Círculo):",
        )
        if not roi_name:
            self._stop_drawing()
            return

        current_arena_id = self.arena_selector_var.get()
        if not current_arena_id:
            self.show_error("Erro", "Nenhum aquário ativo selecionado.")
            self._stop_drawing()
            return

        new_roi = {"name": roi_name, "type": "circle", "coords": (cx, cy, radius)}
        self.roi_data.setdefault(current_arena_id, []).append(new_roi)

        self.roi_canvas.create_oval(
            cx - radius,
            cy - radius,
            cx + radius,
            cy + radius,
            outline="blue",
            fill="cyan",
            stipple="gray25",
            width=2,
        )
        self.roi_listbox.insert("", "end", values=(roi_name,))

        self._stop_drawing()

    def _load_project_view(self):
        """
        Transitions from the welcome screen to the main control view and
        initializes the detector with the appropriate plugin.
        """
        # Reset analysis display state from single video workflow
        self.hide_progress_bar()
        self.analysis_status_var.set("Nenhuma análise em andamento.")
        if self.analysis_video_label:
            try:
                self.analysis_video_label.configure(image="")
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
                self.controller.camera = Camera()
                self.controller.active_frame_source = self.controller.camera
                self.controller.detector.update_scaling(
                    self.controller.camera.actual_width,
                    self.controller.camera.actual_height,
                )
            except OSError as e:
                self.show_error("Erro na Câmera", str(e))
                self._create_welcome_frame()
                return
        elif project_type == "pre-recorded":
            self.update_reports_tree()
            self._populate_video_selector_tree()
            ready_message = f"Projeto: {pm.get_project_name()} - Pronto."
            self.set_status(ready_message)
            self._request_overview_refresh(reason=ready_message, append_summary=True)

        if project_type == "live":
            self.controller.capture_thread = threading.Thread(
                target=self._live_frame_capture_loop, name="CaptureThread", daemon=False
            )
            self.controller.processing_thread = threading.Thread(
                target=self._live_processing_loop, name="ProcessingThread", daemon=False
            )
            self.controller.capture_thread.start()
            self.controller.processing_thread.start()

            # Auto-calibration for Live projects when no zones are defined
            self.root.after(1000, self._check_live_project_calibration)

    def _create_progress_grid_tab(self):
        """Creates the progress grid tab. Delegates to WidgetFactory."""
        return self.widget_factory.create_progress_grid_tab()

    def _check_live_project_calibration(self):
        """Checks if Live project needs calibration and prompts user automatically."""
        if self.controller.project_manager.get_project_type() != "live":
            return

        zone_data = self._get_zone_data_for_active_context()
        if not zone_data or not zone_data.polygon:
            log.info("ui.live_calibration.auto_prompt")

            response = self.ask_ok_cancel(
                "Calibração Automática",
                "Nenhuma arena principal foi definida para este projeto ao vivo.\n\n"
                "Deseja configurar a calibração automaticamente agora?\n\n"
                "• Será aberta a aba de Configuração de Zonas\n"
                "• Você pode usar 'Detectar Aquário (Auto)' ou desenhar manualmente\n"
                "• A configuração será salva automaticamente",
            )

            if response:
                log.info("ui.live_calibration.auto_accepted")
                # Switch to zone configuration tab
                if hasattr(self, "notebook") and hasattr(self, "zone_tab_frame"):
                    self.notebook.select(self.zone_tab_frame)

                # Show guidance message
                self.show_info(
                    "Configuração de Arena Principal",
                    "Configure a arena principal usando:\n\n"
                    "1. 'Detectar Aquário (Auto)' - Para detecção automática\n"
                    "2. 'Desenhar Polígono Principal' - Para desenho manual\n\n"
                    "A configuração será salva automaticamente.",
                )
            else:
                log.info("ui.live_calibration.auto_declined")

    def _render_progress_grid(self):
        """Clears and redraws progress grid. Delegates to WidgetFactory."""
        return self.widget_factory.render_progress_grid()

    def _on_grid_cell_clicked(self, day, group_name):
        pm = self.controller.project_manager
        subjects_per_group = pm.project_data.get("subjects_per_group", 0)
        completed_sessions = pm.get_completed_sessions()

        completed_subjects = {s for (d, g, s) in completed_sessions if d == day and g == group_name}

        dialog = SubjectSelectionDialog(
            self.root, day, group_name, subjects_per_group, completed_subjects
        )

        if dialog.result:
            subject_id = dialog.result
            self.controller.start_recording(day=day, group=group_name, cobaia=str(subject_id))
            self._render_progress_grid()  # Refresh grid after starting a recording

    def _live_frame_capture_loop(self):
        """
        Loop to capture frames from a LIVE source (camera).
        """
        live_frame_count = 0
        while not self.controller.program_exit_event.is_set():
            if not self.controller.active_frame_source:
                time.sleep(0.1)
                continue

            ret, frame = self.controller.active_frame_source.get_frame()
            if not ret:
                log.error("gui.capture_thread.get_frame_failed")
                time.sleep(0.5)
                continue

            live_frame_count += 1

            if not self.controller.frame_queue.full():
                self.controller.frame_queue.put((live_frame_count, frame.copy()))
            if self.controller.is_capturing_for_video and not self.controller.video_queue.full():
                self.controller.video_queue.put(frame.copy())

            fps = (
                self.controller.settings.video_processing.fps if self.controller.settings else 30.0
            )
            time.sleep(1 / (fps * 1.5))

    def _live_processing_loop(self):
        """
        Loop to process frames from a LIVE source.
        """
        while not self.controller.program_exit_event.is_set():
            try:
                frame_number, frame = self.controller.frame_queue.get(timeout=1)
            except queue.Empty:
                continue

            # Determine if we should process/display this frame based on intervals
            should_analyze = (frame_number % self.controller.analysis_interval_frames) == 0
            should_display = (frame_number % self.controller.display_interval_frames) == 0

            detections = []  # Initialize empty for frames that aren't analyzed

            if self.controller.is_processing and should_analyze:
                # Apply perspective warp if calibration data is available
                calib_data = self.controller.project_manager.project_data.get("calibration", {})
                h_matrix = calib_data.get("homography_matrix")
                target_dims = calib_data.get("target_dims_px")

                if h_matrix and target_dims:
                    import numpy as np

                    h_matrix = np.array(h_matrix)
                    frame = cv2.warpPerspective(frame, h_matrix, tuple(target_dims))

                detections, command = self.controller.detector.detect(frame, "live")
                if command is not None:
                    self.controller.arduino.send_command(command)
                if self.controller.is_recording and detections:
                    timestamp = time.time() - self.controller.recorder.start_time
                    self.controller.recorder.write_detection_data(
                        timestamp, frame_number, detections
                    )
                self.controller.detector.draw_overlay(frame, detections)

            # Update live preview window if it exists (respect display interval)
            if self.controller.live_preview_window and should_display:
                try:
                    self.controller.live_preview_window.update_frame(frame, detections)
                except Exception as e:
                    log.error("gui.live_preview.update_error", error=str(e))

            # Only show cv2 window if no preview window is active (respect display interval)
            if not self.controller.live_preview_window and should_display:
                cv2.imshow("Live View", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                self.controller.on_close()
                break
        cv2.destroyAllWindows()
        log.info("gui.live_processing_loop.finished")

    def _prompt_for_weight_type(self):
        """Prompts user to select weight type. Delegates to WidgetFactory."""
        return self.widget_factory.prompt_for_weight_type()

    def _manage_weights_clicked(self):
        """Opens the weight management dialog."""
        self.event_dispatcher.publish_event(Events.MODEL_MANAGE_WEIGHTS)

    def update_weights_dropdown(self, weights: list[str]):
        """Caches available weights so summaries stay consistent."""
        self._available_weight_names = list(weights or [])
        if (
            self.controller.active_weight_name
            and self.controller.active_weight_name in self._available_weight_names
        ):
            self._update_active_weight_display(self.controller.active_weight_name)
        elif not self._available_weight_names:
            self._update_active_weight_display("")

    def set_active_weight_in_dropdown(self, weight_name: str | None):
        """Updates the active weight summary."""
        self._update_active_weight_display(weight_name or "")

    def update_openvino_checkbox(self, enabled: bool):
        """Synchronizes OpenVINO toggle state with the summary label."""
        self._openvino_enabled = bool(enabled)
        self._refresh_openvino_summary()

    def update_openvino_status_display(self, status: str):
        """Updates the detailed OpenVINO status shown in the UI."""
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
        """Updates the GPU hardware information shown in the UI."""
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
        Handles the UI part of creating a new project by opening a comprehensive dialog,
        then calls the controller with the collected data.

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
        """Handles the UI part of opening a project, then calls the controller."""
        project_path = self.ask_directory(title="Selecione uma Pasta de Projeto Existente")
        if not project_path:
            return

        self.event_dispatcher.publish_event(Events.PROJECT_OPEN, {"project_path": project_path})

    def _on_analyze_single_video_clicked(self):
        """Handles the UI part of the single video workflow."""
        dialog = SingleVideoConfigDialog(self.root, settings_obj=self.controller.settings)
        if not dialog.result:
            return  # User cancelled

        source_type = dialog.result.get("source_type", "video")

        if source_type == "camera":
            # Camera analysis: use camera_index
            camera_index = dialog.result.get("camera_index", 0)
            self.show_info(
                "Análise de Câmera",
                f"Iniciando análise da câmera {camera_index}..."
            )
            # Trigger camera analysis via controller
            self.controller.start_live_camera_analysis(camera_index=camera_index)
            return

        # Video file analysis: require video_path
        video_path = dialog.result.get("video_path")
        if not video_path:
            return

        # Pass both config and video path to the controller via event
        self.event_dispatcher.publish_event(
            Events.VIDEO_ANALYZE_SINGLE,
            {
                "video_path": video_path,
                "config": dialog.result,
            },
        )

    def setup_zone_definition_for_single_video(self, video_path: str, config: dict):
        """Prepares and displays the zone configuration tab for a single video."""
        # Reset analysis UI elements for a clean setup
        self.hide_progress_bar()
        self.analysis_status_var.set("Nenhuma análise em andamento.")
        if self.analysis_video_label:
            try:
                self.analysis_video_label.configure(image="")
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

        self._prepare_single_video_ui_state(config)

    def _prepare_single_video_ui_state(self, config: dict | None) -> None:
        """Ensure zone controls reflect the incoming single-video configuration."""
        zone_controls = getattr(self, "zone_controls", None)
        if not zone_controls:
            return

        try:
            zone_controls.show_single_analysis_options()
        except Exception:
            pass

        analysis_interval = None
        display_interval = None
        roi_choice = None
        stabilization_frames = None

        if config:
            analysis_interval = config.get("analysis_interval_frames")
            display_interval = config.get("display_interval_frames")
            roi_choice = config.get("roi_choice")
            stabilization_frames = config.get("stabilization_frames")

        if analysis_interval is None:
            analysis_interval = self.analysis_interval_var.get()
        if display_interval is None:
            display_interval = self.display_interval_var.get()
        if stabilization_frames is None:
            stabilization_frames = self.stabilization_frames_var.get()

        # Share the same StringVar instances so edits from either side stay in sync
        self.analysis_interval_var = zone_controls.analysis_interval_var
        self.display_interval_var = zone_controls.display_interval_var
        self.roi_choice_var = zone_controls.roi_choice_var
        self.stabilization_frames_var = zone_controls.stabilization_frames_var

        self.analysis_interval_var.set(str(analysis_interval or "10"))
        self.display_interval_var.set(str(display_interval or "10"))
        self.roi_choice_var.set(roi_choice or "none")
        self.stabilization_frames_var.set(str(stabilization_frames or "10"))

    def _compose_single_video_runtime_config(self) -> dict | None:
        """Collect the latest single-video settings before starting processing."""
        if not self.pending_single_video_config:
            return None

        config = dict(self.pending_single_video_config)

        # Prefer values from the new zone controls component when available
        zone_controls = getattr(self, "zone_controls", None)
        if zone_controls:
            analysis_var = zone_controls.analysis_interval_var.get()
            display_var = zone_controls.display_interval_var.get()
            roi_choice = zone_controls.roi_choice_var.get()
            stabilization_var = zone_controls.stabilization_frames_var.get()
        else:
            analysis_var = self.analysis_interval_var.get()
            display_var = self.display_interval_var.get()
            roi_choice = config.get("roi_choice", "none")
            stabilization_var = self.stabilization_frames_var.get()

        try:
            analysis_interval = int(analysis_var)
            display_interval = int(display_var)
            if analysis_interval <= 0 or display_interval <= 0:
                raise ValueError
            stabilization_frames = int(stabilization_var)
            if stabilization_frames <= 0:
                raise ValueError
        except (TypeError, ValueError):
            self.show_error(
                "Erro",
                (
                    "Os intervalos devem ser números inteiros positivos "
                    "(análise, exibição e estabilização)."
                ),
            )
            return None

        config["analysis_interval_frames"] = analysis_interval
        config["display_interval_frames"] = display_interval
        config["roi_choice"] = roi_choice
        config["stabilization_frames"] = stabilization_frames

        return config

    def _on_auto_detect_clicked(self, stabilization_frames: int | str | None = None):
        """Handler for the auto-detect button."""
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
        """Handler for the 'Start Analysis' button in the single video flow."""
        # If the user was editing a polygon, prompt for confirmation before saving.
        if self.edited_polygon_points:
            response = messagebox.askyesnocancel(
                "Salvar Polígono?",
                "Você deseja salvar as alterações no polígono antes de iniciar a "
                "análise?\n\n"
                "Sim: Salvar e iniciar análise\n"
                "Não: Descartar alterações e iniciar análise\n"
                "Cancelar: Voltar para edição",
            )
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

        updated_config = self._compose_single_video_runtime_config()
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
        """Delegates the close action to the controller."""
        self.controller.on_close()

    def _join_threads(self):
        """Delegates thread joining to the controller."""
        self.controller.join_threads()

    def set_status(self, text):
        """Updates the UI status bar."""
        self.status_var.set(text)

    def show_progress_bar(self):
        """Shows the progress bar frame and cancel button."""
        if self.progress_frame and not self.progress_frame.winfo_viewable():
            # Pack progress_frame BEFORE video_container to ensure it stays visible
            if hasattr(self, "video_container") and self.video_container:
                self.progress_frame.pack(before=self.video_container, pady=5, fill="x", padx=10)
                # Force layout recalculation after showing progress bar
                self.root.update_idletasks()
            else:
                self.progress_frame.pack(pady=5, fill="x", padx=10)
            self.progress_bar["value"] = 0
        if self.cancel_proc_btn:
            self.cancel_proc_btn.config(state="normal")

    def update_progress(self, value):
        """Updates the progress bar."""
        if self.progress_bar:
            self.progress_bar["value"] = value * 100  # Convert fraction to percentage
            self.update_idletasks()

    def update_idletasks(self):
        """Force the GUI to update, processing pending events."""
        self.root.update_idletasks()

    def update_progress_stats(
        self,
        *,
        total=None,
        processed=None,
        detected=None,
        percent=None,
        elapsed=None,
        eta=None,
    ):
        """Update textual statistics for file processing."""
        if not self.progress_labels:
            return
        if total is not None:
            self.progress_labels["total"].set(str(total))
        if processed is not None:
            self.progress_labels["processed"].set(str(processed))
        if detected is not None:
            self.progress_labels["detected"].set(str(detected))
        if percent is not None:
            self.progress_labels["percent"].set(f"{percent:.1f}%")
        if elapsed is not None:
            self.progress_labels["elapsed"].set(self._format_time(elapsed))
        if eta is not None:
            self.progress_labels["eta"].set(self._format_time(eta) if eta >= 0 else "-")

    def hide_progress_bar(self):
        """Hides the progress bar and cancel button, and resets its value."""
        if (
            self.progress_frame
            and self.progress_frame.winfo_exists()
            and self.progress_frame.winfo_viewable()
        ):
            self.progress_frame.pack_forget()
            self.progress_bar["value"] = 0
        if self.cancel_proc_btn and self.cancel_proc_btn.winfo_exists():
            self.cancel_proc_btn.config(state="disabled")



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

        if self.toggle_view_btn:
            self.toggle_view_btn.config(text="Ver Configuração de Zonas")

    def _switch_to_zones_view(self):
        """Switch to zone drawing view."""
        if not self.notebook or not self.zone_tab_frame:
            return

        self.canvas_view_mode = "zones"
        self.notebook.select(self.zone_tab_frame)

        if self.toggle_view_btn:
            self.toggle_view_btn.config(text="Ver Análise em Progresso")

    def start_analysis_view_mode(self):
        """Called when analysis starts - immediately switch to analysis view and
        enable toggle."""
        self.analysis_active = True
        self.analysis_status_var.set("Preparando análise...")
        if self.analysis_task_var is not None:
            self.analysis_task_var.set("Preparando fila de análise...")
        self.state_synchronizer._set_analysis_metadata_defaults()
        self._reset_analysis_controls()
        self.show_progress_bar()
        if self.toggle_view_btn:
            self.toggle_view_btn.config(state="normal")
        if self.cancel_proc_btn:
            self.cancel_proc_btn.config(state="normal")
        self._switch_to_analysis_view()

    def stop_analysis_view_mode(self):
        """Called when analysis stops - disable toggle and return to zones view."""
        self.analysis_active = False
        if self.toggle_view_btn:
            self.toggle_view_btn.config(state="disabled")
        if self.cancel_proc_btn:
            self.cancel_proc_btn.config(state="disabled")
        self.hide_progress_bar()
        self.analysis_status_var.set("Nenhuma análise em andamento.")
        if self.analysis_task_var is not None:
            self.analysis_task_var.set(self._default_analysis_task_text())
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

        self.tracking_mode_var.set(f"Modo de rastreamento: {mode.display_name}")

        if not self.track_selector_widget:
            return

        state = "disabled" if mode is ProcessingMode.SINGLE_SUBJECT else "readonly"
        self.track_selector_widget.configure(state=state)

        if mode is ProcessingMode.SINGLE_SUBJECT:
            self.track_selector_var.set("Todos")
            self.state_synchronizer._update_track_options(["Todos"])
        elif previous_mode is ProcessingMode.SINGLE_SUBJECT:
            options = self._build_track_options(self._current_detections)
            self.state_synchronizer._update_track_options(options)

    def update_analysis_profile(self, profile_name: str) -> None:
        """Update the label describing the active analysis profile."""
        text = (profile_name or "default").strip() or "default"
        self.analysis_profile_var.set(f"Perfil de análise: {text}")
        self._reset_analysis_controls()

    def update_social_summary(
        self,
        *,
        profile: str,
        stats: dict | None,
        tracks: list[str] | None,
    ) -> None:
        """Display aggregated social proximity statistics for the active video."""
        if stats and isinstance(stats, dict):
            percentages = stats.get("social_time_percentage") or {}
            if isinstance(percentages, dict) and percentages:
                formatted = []
                for key, value in sorted(
                    percentages.items(),
                    key=lambda item: str(item[0]),
                ):
                    if isinstance(value, (int, float)):
                        formatted.append(f"ID {key}: {value:.1f}%")
                if formatted:
                    self.social_summary_var.set("Interações sociais: " + ", ".join(formatted))
                else:
                    self.social_summary_var.set(
                        "Interações sociais: nenhum agrupamento registrado."
                    )
            else:
                self.social_summary_var.set("Interações sociais: nenhum agrupamento registrado.")
        else:
            self.social_summary_var.set("Interações sociais: aguardando dados.")

        if tracks and self._active_processing_mode is not ProcessingMode.SINGLE_SUBJECT:
            normalized_tracks = [str(track).strip() for track in tracks if str(track).strip()]
            if normalized_tracks:
                self.state_synchronizer._update_track_options(["Todos", *normalized_tracks])

    def _reset_analysis_controls(self) -> None:
        """Reset track selector state and cached frames."""
        self._current_detections = []
        self._last_analysis_frame = None
        self._analysis_overlay_image = None
        self.track_selector_var.set("Todos")
        self.state_synchronizer._update_track_options(["Todos"])
        if self.track_selector_widget:
            state = (
                "disabled"
                if self._active_processing_mode is ProcessingMode.SINGLE_SUBJECT
                else "readonly"
            )
            self.track_selector_widget.configure(state=state)

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

    def update_processing_stats(
        self,
        total_frames=None,
        processed_frames=None,
        detected_frames=None,
        start_time=None,
        current_frame=None,
    ):
        """Update processing statistics in real-time during video analysis."""
        if not self.progress_labels:
            return

        # Update frame counters in all label sets
        labels = self.progress_labels
        if total_frames is not None:
            labels["total"].set(str(total_frames))
        if processed_frames is not None:
            labels["processed"].set(str(processed_frames))
        if detected_frames is not None:
            labels["detected"].set(str(detected_frames))

        # Calculate and update percentage based on actual frame position
        if total_frames:
            frame_for_percent = current_frame if current_frame is not None else processed_frames
            if frame_for_percent is not None:
                percent = (frame_for_percent / total_frames) * 100
                labels["percent"].set(f"{percent:.1f}%")

        # Calculate elapsed time and ETA
        if start_time:
            import time

            elapsed = time.time() - start_time
            labels["elapsed"].set(self._format_time(elapsed))

            frame_for_eta = current_frame if current_frame is not None else processed_frames
            if frame_for_eta and total_frames and frame_for_eta > 0:
                rate = frame_for_eta / elapsed
                remaining_frames = total_frames - frame_for_eta
                if rate > 0:
                    eta = remaining_frames / rate
                    labels["eta"].set(self._format_time(eta))
                else:
                    labels["eta"].set("-")

    def update_analysis_metadata(self, *, metadata: dict | None) -> None:
        """Update the metadata display for the currently processed video."""
        metadata = metadata or {}
        group_display = self._resolve_group_display(metadata)
        day_display = self._resolve_day_display(metadata)
        subject_display = self._resolve_subject_display(metadata)

        self.state_synchronizer._apply_analysis_metadata_strings(
            group_display,
            day_display,
            subject_display,
        )

    def update_analysis_task_status(
        self,
        *,
        index: int,
        total: int,
        experiment_id: str | None = None,
        step: str | None = None,
    ) -> None:
        """Update the task summary indicating which video is being processed."""
        if not hasattr(self, "analysis_task_var") or self.analysis_task_var is None:
            return

        total_videos = max(int(total) if total is not None else 0, 1)
        current_index = max(int(index) if index is not None else 0, 0) + 1

        parts: list[str] = [f"Vídeo {current_index} de {total_videos}"]

        if experiment_id:
            exp_text = str(experiment_id).strip()
            if exp_text:
                parts.append(f"— {exp_text}")

        if step:
            step_text = str(step).strip()
            if step_text:
                if step_text.lower().startswith("etapa:"):
                    step_text = step_text[6:].strip()
                if step_text:
                    parts.append(f"• {step_text}")

        self.analysis_task_var.set(" ".join(parts))

    @staticmethod

    @classmethod



    @staticmethod

    def _resolve_group_display(self, metadata: dict) -> str:
        for key in (
            "group_display_name",
            "group_label",
            "group_name",
            "group_id",
            "group",
        ):
            value = metadata.get(key)
            if value not in (None, "", "None"):
                text = str(value).strip()
                if text:
                    return text
        return "Sem Grupo"

    def _resolve_day_display(self, metadata: dict) -> str:
        for key in ("day_label", "day_display_name"):
            value = metadata.get(key)
            if value not in (None, "", "None"):
                text = str(value).strip()
                if text:
                    return text if text.lower().startswith("dia") else f"Dia {text}"

        for key in ("day", "day_id", "dia"):
            value = metadata.get(key)
            if value not in (None, "", "None"):
                formatted = self._format_day_display(value)
                if formatted.lower() == "sem dia":
                    return "Sem Dia"
                return f"Dia {formatted}"

        return "Sem Dia"

    def _resolve_subject_display(self, metadata: dict) -> str:
        for key in (
            "subject_label",
            "subject_display_name",
            "subject",
            "subject_id",
            "animal",
            "animal_id",
            "individual",
            "individuo",
            "cobaia",
        ):
            value = metadata.get(key)
            if value in (None, "", "None"):
                continue

            if isinstance(value, bool):
                text = str(value).strip()
                if text:
                    return text

            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if float(value).is_integer():
                    return f"{int(value):02d}"
                return str(value)

            text = str(value).strip()
            if not text:
                continue
            if text.isdigit():
                return f"{int(text):02d}"
            return text

        return "Não informado"

    @staticmethod
    def _format_time(seconds: float) -> str:
        if seconds is None or seconds < 0:
            return "-"
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h:d}h {m:02d}m {s:02d}s"
        if m:
            return f"{m:d}m {s:02d}s"
        return f"{s:d}s"

    def show_error(self, title, message):
        """Shows an error message box. Delegates to DialogManager."""
        return self.dialog_manager.show_error(title, message)

    def show_warning(self, title, message):
        """Shows a warning message box. Delegates to DialogManager."""
        return self.dialog_manager.show_warning(title, message)

    def show_info(self, title, message):
        """Shows an info message box. Delegates to DialogManager."""
        return self.dialog_manager.show_info(title, message)

    def show_pending_videos_dialog(
        self,
        *,
        ready_with_trajectory: list[dict],
        ready_with_zones: list[dict],
        arena_only: list[dict],
        without_arena: list[dict],
    ) -> dict | None:
        """Exibe o diálogo hierárquico de vídeos pendentes."""

        self.apply_pending_readiness_snapshot(
            ready_with_trajectory=ready_with_trajectory,
            ready_with_zones=ready_with_zones,
            arena_only=arena_only,
            without_arena=without_arena,
        )

        dialog = PendingVideosDialog(
            self.root,
            hierarchy_builder=self._build_video_hierarchy_snapshot,
            ready_with_trajectory=ready_with_trajectory,
            ready_with_zones=ready_with_zones,
            arena_only=arena_only,
            without_arena=without_arena,
        )

        return dialog.result

    def ask_ok_cancel(self, title, message):
        """Shows a confirmation dialog. Delegates to DialogManager."""
        return self.dialog_manager.ask_ok_cancel(title, message)

    def ask_string(self, title, prompt, initialvalue=None):
        """Shows a dialog for string input. Delegates to DialogManager."""
        return self.dialog_manager.ask_string(title, prompt, initialvalue=initialvalue)

    def ask_directory(self, title):
        """Shows a dialog to select a directory. Delegates to DialogManager."""
        return self.dialog_manager.ask_directory(title)

    def ask_open_filenames(self, title, filetypes):
        """Shows a dialog to select one or more files. Delegates to DialogManager."""
        return self.dialog_manager.ask_open_filenames(title, filetypes)


    def _on_zone_double_click(self, event):
        """Handle double-click on zone list - opens vertex editing mode."""
        self._edit_selected_zone_vertices()

    def _on_zone_right_click(self, event):
        """Mostra menu de contexto"""
        # Seleciona item sob o cursor
        item = self.zone_listbox.identify_row(event.y)
        if item:
            self.zone_listbox.selection_set(item)

            # Verifica se é ROI (não arena principal)
            values = self.zone_listbox.item(item)["values"]
            if values and "Arena Principal" not in values[0]:
                # ROI - show full menu
                if self.roi_context_menu:
                    self.roi_context_menu.post(event.x_root, event.y_root)
            elif values and "Arena Principal" in values[0]:
                # Arena Principal - show limited menu (only edit vertices)
                arena_menu = Menu(self.root, tearoff=0)
                arena_menu.add_command(
                    label="🔧 Editar Vértices",
                    command=self._edit_selected_zone_vertices,
                )
                arena_menu.post(event.x_root, event.y_root)

    def _edit_selected_zone_vertices(self):
        """Enables interactive editing of selected zone vertices. Delegates to CanvasManager."""
        return self.canvas_manager.edit_selected_zone_vertices()

    def _rename_selected_roi(self):
        """Renomeia ROI selecionada"""
        selected = self.zone_listbox.selection()
        if not selected:
            return

        item = self.zone_listbox.item(selected[0])
        old_name = item["values"][0].replace("📍 ", "")

        new_name = self.ask_string(
            "Renomear ROI", f"Novo nome para '{old_name}':", initialvalue=old_name
        )

        if new_name and new_name != old_name:
            # Atualiza no projeto
            zone_data = self._get_zone_data_for_active_context()
            try:
                idx = zone_data.roi_names.index(old_name)
                zone_data.roi_names[idx] = new_name

                # Persist updated ROI name
                self.controller.project_manager.save_zone_data(zone_data)

                # Atualiza visualização
                self.canvas_manager.redraw_zones_from_project_data()
                self.show_info("Sucesso", f"ROI renomeada para '{new_name}'")
                status_message = f"ROI renomeada para '{new_name}'."
                self.set_status(status_message)
                self._request_overview_refresh(reason=status_message, append_summary=True)

            except ValueError:
                self.show_error("Erro", "ROI não encontrada")

    def _change_roi_color(self):
        """Muda cor da ROI selecionada"""
        selected = self.zone_listbox.selection()
        if not selected:
            return

        item = self.zone_listbox.item(selected[0])
        old_name = item["values"][0].replace("📍 ", "")

        # Usa o diálogo de cores personalizado
        color_dialog = ColorSelectionDialog(self.root, "Mudar Cor da ROI")
        if not color_dialog.result:
            return

        selected_color = color_dialog.result
        new_color = selected_color["rgb"]
        color_name = selected_color["name"]

        # Atualiza no projeto
        zone_data = self._get_zone_data_for_active_context()
        try:
            idx = zone_data.roi_names.index(old_name)
            zone_data.roi_colors[idx] = new_color

            # Persist color change
            self.controller.project_manager.save_zone_data(zone_data)

            # Atualiza visualização
            self.canvas_manager.redraw_zones_from_project_data()
            self.show_info("Sucesso", f"Cor da ROI '{old_name}' alterada para {color_name}")
            status_message = f"Cor da ROI '{old_name}' alterada para {color_name}."
            self.set_status(status_message)
            self._request_overview_refresh(reason=status_message, append_summary=True)

        except ValueError:
            self.show_error("Erro", "ROI não encontrada")
        except IndexError:
            self.show_error("Erro", "Dados de cor da ROI não encontrados")

    def _remove_selected_roi_confirm(self):
        """Remove ROI selecionada com confirmação"""
        selected = self.zone_listbox.selection()
        if not selected:
            return

        item = self.zone_listbox.item(selected[0])
        roi_name = item["values"][0].replace("📍 ", "")

        # Confirmação
        from tkinter import messagebox

        confirm = messagebox.askyesno(
            "Confirmar Remoção",
            f"Tem certeza que deseja remover a ROI '{roi_name}'?\n\n"
            "Esta ação não pode ser desfeita.",
            icon="warning",
        )

        if confirm:
            # Remove do projeto
            zone_data = self._get_zone_data_for_active_context()
            try:
                idx = zone_data.roi_names.index(roi_name)

                # Remove da lista de nomes
                zone_data.roi_names.pop(idx)

                # Remove da lista de polígonos
                if idx < len(zone_data.roi_polygons):
                    zone_data.roi_polygons.pop(idx)

                # Remove da lista de cores
                if idx < len(zone_data.roi_colors):
                    zone_data.roi_colors.pop(idx)

                # Persist removals
                self.controller.project_manager.save_zone_data(zone_data)

                # Atualiza visualização
                self.canvas_manager.redraw_zones_from_project_data()
                self.show_info("Sucesso", f"ROI '{roi_name}' removida com sucesso")
                status_message = f"ROI '{roi_name}' removida com sucesso."
                self.set_status(status_message)
                self._request_overview_refresh(reason=status_message, append_summary=True)

            except ValueError:
                self.show_error("Erro", "ROI não encontrada")

    def ask_save_filename(self, **options):
        """Shows a dialog to select a save file path."""
        return filedialog.asksaveasfilename(**options)

    def update_button_state(self, button_name, state):
        """Updates the state of a button ('normal' or 'disabled')."""
        if button_name == "start_rec" and self.start_rec_btn is not None:
            self.start_rec_btn.config(state=state)
        elif button_name == "stop_rec" and self.stop_rec_btn is not None:
            self.stop_rec_btn.config(state=state)
        elif button_name == "process_video" and self.process_video_btn is not None:
            self.process_video_btn.config(state=state)
        elif button_name == "cancel_processing" and self.cancel_proc_btn is not None:
            self.cancel_proc_btn.config(state=state)

    def ask_recording_details_unified(self):
        """Shows a unified dialog to get day, group, and subject."""
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

    def ask_missing_metadata(self, experiment_id):
        """Shows a dialog to get missing metadata from the user."""
        dialog = MissingMetadataDialog(self.root, experiment_id)
        return dialog.result


# ==============================================================================
# Backward Compatibility Properties for Component Migration
# ==============================================================================
# These properties allow legacy code to continue working while we gradually
# migrate to the new component-based architecture. They map old attribute names
# to the new component APIs.
# TODO: Remove these after full migration is complete.


def _add_compatibility_properties_to_application_gui():
    """Add backward compatibility properties to ApplicationGUI class."""

    @property
    def roi_canvas(self):
        """
        Backward compatibility property: maps roi_canvas to video_display.canvas.

        This allows existing drawing code to continue working during the gradual
        migration to VideoDisplayWidget. Should be removed after migration is complete.
        """
        if hasattr(self, "video_display") and self.video_display:
            return self.video_display.canvas
        # Fallback to old widget if component not yet created
        if hasattr(self, "_roi_canvas_widget"):
            return self._roi_canvas_widget
        return None

    @property
    def zone_listbox(self):
        """Backward compatibility: map zone_listbox to zone_controls.zone_listbox."""
        if hasattr(self, "zone_controls") and self.zone_controls:
            return self.zone_controls.zone_listbox
        return None

    @property
    def draw_roi_button(self):
        """Backward compatibility: map draw_roi_button to zone_controls.draw_roi_button."""
        if hasattr(self, "zone_controls") and self.zone_controls:
            return self.zone_controls.draw_roi_button
        return None

    @property
    def toggle_view_btn(self):
        """Backward compatibility: map toggle_view_btn to zone_controls.toggle_view_btn."""
        if hasattr(self, "zone_controls") and self.zone_controls:
            return self.zone_controls.toggle_view_btn
        return None

    @property
    def roi_template_combobox(self):
        """
        Backward compatibility: map roi_template_combobox to
        zone_controls.roi_template_combobox.
        """
        if hasattr(self, "zone_controls") and self.zone_controls:
            return self.zone_controls.roi_template_combobox
        return None

    @property
    def video_selector_tree(self):
        """Backward compatibility: map video_selector_tree to zone_controls.video_selector_tree."""
        if hasattr(self, "zone_controls") and self.zone_controls:
            return self.zone_controls.video_selector_tree
        return None

    @property
    def interactive_buttons_frame(self):
        """
        Backward compatibility: map interactive_buttons_frame to
        zone_controls.interactive_buttons_frame.
        """
        if hasattr(self, "zone_controls") and self.zone_controls:
            return self.zone_controls.interactive_buttons_frame
        return None

    @property
    def project_overview_tree(self):
        """Backward compatibility: map project_overview_tree to widget."""
        if hasattr(self, "project_overview_widget") and self.project_overview_widget:
            return self.project_overview_widget.project_overview_tree
        return None

    @property
    def project_status_vars(self):
        """Backward compatibility: map project_status_vars to widget."""
        if hasattr(self, "project_overview_widget") and self.project_overview_widget:
            return self.project_overview_widget.project_status_vars
        return {}

    # Add properties to ApplicationGUI class
    ApplicationGUI.roi_canvas = roi_canvas
    ApplicationGUI.zone_listbox = zone_listbox
    ApplicationGUI.draw_roi_button = draw_roi_button
    ApplicationGUI.toggle_view_btn = toggle_view_btn
    ApplicationGUI.roi_template_combobox = roi_template_combobox
    ApplicationGUI.video_selector_tree = video_selector_tree
    ApplicationGUI.interactive_buttons_frame = interactive_buttons_frame
    ApplicationGUI.project_overview_tree = project_overview_tree
    ApplicationGUI.project_status_vars = project_status_vars


# Apply compatibility properties
_add_compatibility_properties_to_application_gui()


if __name__ == "__main__":
    # Using print is fine here as it's for direct execution feedback
    print("Este arquivo deve ser importado, não executado diretamente.")
    print("Execute o script principal da aplicação para iniciar o Zebtrack.")
