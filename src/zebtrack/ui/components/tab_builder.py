from tkinter import Button, Label, ttk
from typing import TYPE_CHECKING, Any, cast

import structlog

from zebtrack.ui import payloads
from zebtrack.ui.components.arduino_dashboard import ArduinoDashboardWidget
from zebtrack.ui.components.model_diagnostics_panel import ModelDiagnosticsPanel
from zebtrack.ui.components.project_model_configuration_panel import (
    ProjectModelConfigurationPanel,
)
from zebtrack.ui.components.video_display import VideoDisplayWidget
from zebtrack.ui.components.zone_controls import ZoneControlsWidget
from zebtrack.ui.event_bus_v2 import Event, UIEvents

if TYPE_CHECKING:
    from zebtrack.ui.gui import ApplicationGUI

log = structlog.get_logger()


class TabBuilder:
    """Builds notebook tabs for the main application."""

    def __init__(self, gui: "ApplicationGUI"):
        self.gui = gui
        # Use project_manager injected into GUI (Phase 4 dependency injection)
        self.project_manager = gui.project_manager

    def build_main_controls_tab(self) -> ttk.Frame:
        """Build main controls tab based on project type."""
        if self.gui.notebook is None:
            return ttk.Frame(self.gui.root)  # Fallback

        self.gui.main_controls_frame = ttk.Frame(self.gui.notebook, padding="10")
        self.gui.notebook.add(self.gui.main_controls_frame, text="Controle Principal")

        if not self.project_manager:
            return self.gui.main_controls_frame

        project_type = self.project_manager.get_project_type()
        self.gui.process_video_btn = None

        controls_container = ttk.Frame(self.gui.main_controls_frame)
        controls_container.pack(fill="x", pady=(0, 10))

        if project_type == "live":
            self._add_recording_buttons(controls_container)
        elif project_type == "pre-recorded":
            self._add_processing_buttons(controls_container)

        self._add_project_model_navigation_buttons(controls_container)

        # Botão fechar (sempre presente)
        Button(
            controls_container,
            text="Fechar Projeto",
            command=lambda: self.gui.event_dispatcher.publish_event(
                UIEvents.PROJECT_CLOSE,
                payloads.EmptyPayload(),
            ),
        ).pack(side="right", padx=5)

        # Build overview panel (Delegates to GUI/WidgetFactory)
        self.gui._create_project_overview_panel(self.gui.main_controls_frame)

        # Container for side-by-side widgets at the bottom
        bottom_container = ttk.Frame(self.gui.main_controls_frame)
        bottom_container.pack(fill="x", pady=(5, 10), padx=10)

        # Model status - right side (takes full width now)
        self._build_model_status_section(bottom_container)

        # Build project-type-specific widgets
        if project_type == "live":
            self._build_live_project_widgets(self.gui.main_controls_frame)

        if self.gui.event_bus_v2:
            self.gui.event_bus_v2.publish(
                Event(
                    type=UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
                    data=payloads.ProjectViewsRefreshRequestedPayload(
                        reason="TabBuilder initialization",
                        append_summary=False,
                        immediate=False,
                    ),
                    source="TabBuilder.build_main_controls_tab",
                )
            )

        return self.gui.main_controls_frame

    def build_zone_tab(self) -> None:
        """Create the tab for ROI and detection zone configuration."""
        # Use Any cast to set dynamic attributes
        gui = cast(Any, self.gui)
        gui.roi_data = {}
        gui._bg_scale = 1.0
        gui._bg_offset = (0, 0)
        gui._bg_img_size = (0, 0)
        gui._canvas_bg_image = None
        gui._drawing_buttons_frame = None

        if self.gui.notebook is None:
            return

        # 1. Create the main frame for the tab and rename it
        self.gui.zone_tab_frame = ttk.Frame(self.gui.notebook, padding="10")
        self.gui.notebook.add(self.gui.zone_tab_frame, text="Configuração de Zonas")

        # 2. Create the PanedWindow for side-by-side panels
        main_pane = ttk.PanedWindow(self.gui.zone_tab_frame, orient="horizontal")
        main_pane.pack(expand=True, fill="both")

        # 3. Create the control panel on the left with scrollable frame
        # Reduced weight to make it narrower by default
        left_panel_frame = ttk.Frame(main_pane, padding=5, relief="groove", borderwidth=2)
        main_pane.add(left_panel_frame, weight=1)

        # 4. Create the visualization panel on the right
        self.gui.viz_frame = ttk.Frame(main_pane, padding=5, relief="sunken", borderwidth=2)
        main_pane.add(self.gui.viz_frame, weight=4)

        # Create containers for relocated controls (Top and Bottom of viz frame)
        self.gui.viz_top_container = ttk.Frame(self.gui.viz_frame)
        self.gui.viz_top_container.pack(side="top", fill="x", pady=(0, 5))

        self.gui.viz_bottom_container = ttk.Frame(self.gui.viz_frame)
        self.gui.viz_bottom_container.pack(side="bottom", fill="x", pady=(5, 0))

        # Update ZoneControlsWidget to accept these containers
        self.gui.zone_controls = ZoneControlsWidget(
            left_panel_frame,
            event_bus=self.gui.event_bus,
            template_actions_parent=self.gui.viz_bottom_container,
            drawing_actions_parent=self.gui.viz_top_container,
        )
        self.gui.zone_controls.pack(fill="both", expand=True)

        # Keep legacy attributes in sync with the new component state
        self.gui.stabilization_frames_var = self.gui.zone_controls.stabilization_frames_var
        self.gui.zone_controls_frame = self.gui.zone_controls.zone_controls_frame
        self.gui.fixed_button_frame = self.gui.zone_controls.fixed_button_frame
        self.gui.controls_canvas = self.gui.zone_controls.controls_canvas
        self.gui.controls_canvas_window = self.gui.zone_controls.controls_canvas_window

        def _on_pane_configure(event=None):
            try:
                current_pos = main_pane.sashpos(0)
                if current_pos < 420:  # Minimum width for left panel
                    main_pane.sashpos(0, 420)
            except Exception:
                log.debug("tab_builder.pane_configure_sash.suppressed", exc_info=True)

        main_pane.bind("<Configure>", _on_pane_configure)

        # 5. ✨ NEW: Create VideoDisplayWidget instead of manual Canvas
        self.gui.video_display = VideoDisplayWidget(
            self.gui.viz_frame, event_bus=self.gui.event_bus, width=800, height=600, bg="gray"
        )
        self.gui.video_display.pack(expand=True, fill="both")

        roi_canvas = self.gui.video_display.canvas
        self.gui._roi_canvas_widget = roi_canvas
        if roi_canvas:
            roi_canvas.bind("<Configure>", self.gui.canvas_manager.on_canvas_configure)

        # 7. ✨ NEW: Create context menu before subscribing to events
        gui.roi_context_menu = None
        self.gui.menu_manager.create_roi_context_menu()

        # 8. ✨ NEW: Subscribe to events emitted by the components
        self.gui.event_dispatcher.subscribe_zone_component_events()

        def _set_initial_sash():
            try:
                main_pane.update_idletasks()
                # Set sash position to a comfortable default
                main_pane.sashpos(0, 450)
            except Exception:
                log.debug("tab_builder.initial_sash_set.suppressed", exc_info=True)

        main_pane.after(10, _set_initial_sash)
        main_pane.after(50, _set_initial_sash)
        main_pane.after(100, _set_initial_sash)
        main_pane.after(200, _set_initial_sash)

    def build_model_configuration_tab(self) -> None:
        """Create the project-only model configuration tab."""
        if self.gui.notebook is None:
            return

        self.gui.model_configuration_tab_frame = ttk.Frame(self.gui.notebook, padding="10")
        self.gui.notebook.add(
            self.gui.model_configuration_tab_frame,
            text="Config. Modelo IA",
        )
        panel = ProjectModelConfigurationPanel(
            self.gui.model_configuration_tab_frame,
            self.gui.controller,
        )
        panel.pack(fill="both", expand=True)
        self.gui.project_model_configuration_panel = panel

    def build_diagnostics_tab(self) -> None:
        """Create the project-only diagnostics tab."""
        if self.gui.notebook is None:
            return

        self.gui.diagnostics_tab_frame = ttk.Frame(self.gui.notebook, padding="10")
        self.gui.notebook.add(self.gui.diagnostics_tab_frame, text="Diagnóstico Modelo IA")
        panel = ModelDiagnosticsPanel(
            self.gui.diagnostics_tab_frame,
            self.gui.controller,
            scope="project",
        )
        panel.pack(fill="both", expand=True)
        self.gui.project_diagnostics_panel = panel

    def build_processing_reports_tab(self) -> None:
        """Create the processing reports tab. Delegates to WidgetFactory."""
        return self.gui.widget_factory.create_processing_reports_tab()

    def build_analysis_tab(self) -> None:
        """Create the analysis tab. Delegates to WidgetFactory."""
        return self.gui.widget_factory.create_analysis_tab_widget()

    def build_configuration_tab(self) -> None:
        """Create the configuration tab. Delegates to WidgetFactory."""
        return self.gui.widget_factory.create_configuration_tab_widget()

    def _add_project_model_navigation_buttons(self, parent) -> None:
        ttk.Button(
            parent,
            text="Config. Modelo IA",
            command=self._select_model_configuration_tab,
        ).pack(side="left", padx=5)
        ttk.Button(
            parent,
            text="Diagnóstico Modelo IA",
            command=self._select_diagnostics_tab,
        ).pack(side="left", padx=5)

    def _select_model_configuration_tab(self) -> None:
        if self.gui.notebook and getattr(self.gui, "model_configuration_tab_frame", None):
            self.gui.notebook.select(self.gui.model_configuration_tab_frame)

    def _select_diagnostics_tab(self) -> None:
        if self.gui.notebook and getattr(self.gui, "diagnostics_tab_frame", None):
            self.gui.notebook.select(self.gui.diagnostics_tab_frame)

    def _add_recording_buttons(self, parent):
        """Add recording buttons for live projects."""
        self.gui.start_rec_btn = Button(
            parent,
            text="Iniciar Gravação",
            command=lambda: self.gui.event_dispatcher.publish_event(
                UIEvents.RECORDING_START,
                payloads.EmptyPayload(),
            ),
        )
        self.gui.start_rec_btn.pack(side="left", padx=5)

        self.gui.stop_rec_btn = Button(
            parent,
            text="Parar Gravação",
            command=lambda: self.gui.event_dispatcher.publish_event(
                UIEvents.RECORDING_STOP,
                payloads.EmptyPayload(),
            ),
            state="disabled",
        )
        self.gui.stop_rec_btn.pack(side="left", padx=5)

    def _add_processing_buttons(self, parent):
        """Add processing buttons for pre-recorded projects."""
        ttk.Button(
            parent,
            text="Adicionar Vídeos/Pastas ao Projeto...",
            command=lambda: self.gui.event_dispatcher.publish_event(
                UIEvents.PROJECT_IMPORT_VIDEOS,
                payloads.ProjectImportVideosPayload(),
            ),
        ).pack(side="left", padx=5)

        ttk.Button(
            parent,
            text="Processar Vídeos Pendentes...",
            command=lambda: self.gui.event_dispatcher.publish_event(
                UIEvents.PROJECT_PROCESS_VIDEOS,
                payloads.ProjectProcessVideosPayload(video_paths=()),
            ),
        ).pack(side="left", padx=5)

    def _build_model_status_section(self, parent):
        """Build model status section (project context — 2-slot summary)."""
        model_status_frame = ttk.LabelFrame(
            parent,
            text="Estado do Modelo de Detecção",
            padding=10,
        )
        model_status_frame.pack(side="left", fill="both", expand=True, padx=(5, 0))
        # ``_active_weight_display_var`` carries a multi-line slot summary; in
        # the project tab we filter to the 2 slots actually consumed by this
        # project (delegated to WeightHardwareManager once the panel exists).
        ttk.Label(
            model_status_frame,
            textvariable=self.gui._active_weight_display_var,
            justify="left",
        ).pack(anchor="w")
        ttk.Label(
            model_status_frame,
            textvariable=self.gui._openvino_display_var,
        ).pack(anchor="w", pady=(4, 0))
        ttk.Label(
            model_status_frame,
            textvariable=self.gui._gpu_hardware_display_var,
            foreground="gray",
        ).pack(anchor="w", pady=(4, 0))

        # Trigger the project-scoped refresh so the label switches from the
        # global 4-slot view to the 2 slots used by this project.
        weight_hw = getattr(self.gui, "weight_hardware_manager", None)
        if weight_hw is not None:
            weight_hw.refresh_weights_summary(scope="project")

    def _build_live_project_widgets(self, parent):
        """Build widgets specific to live projects."""
        label = Label(
            parent,
            textvariable=self.gui.external_trigger_notice_var,
            anchor="w",
            justify="left",
            wraplength=600,
            padx=10,
            pady=6,
        )
        label.pack(fill="x", pady=(0, 8))
        self.gui.external_trigger_notice_label = label

        # Safe access to cget with defaults if needed
        self.gui._external_notice_default_bg = str(label.cget("background"))
        self.gui._external_notice_default_fg = str(label.cget("foreground"))

        self.gui.arduino_dashboard_widget = ArduinoDashboardWidget(
            parent,
            event_bus=self.gui.event_bus,
            project_manager=self.project_manager,
        )
        self.gui.arduino_dashboard_widget.pack(fill="both", expand=False, pady=(0, 10))

        if self.gui.event_bus_v2:
            self.gui.event_bus_v2.publish(
                Event(
                    type=UIEvents.EXTERNAL_TRIGGER_NOTICE_CLEARED,
                    source="TabBuilder._build_live_project_widgets",
                )
            )
