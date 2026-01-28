from tkinter import Button, Label, ttk
from typing import TYPE_CHECKING

import structlog

from zebtrack.ui.components.arduino_dashboard import ArduinoDashboardWidget
from zebtrack.ui.components.video_display import VideoDisplayWidget
from zebtrack.ui.components.zone_controls import ZoneControlsWidget
from zebtrack.ui.event_bus_v2 import Event, UIEvents
from zebtrack.ui.events import Events

if TYPE_CHECKING:
    from zebtrack.ui.gui import ApplicationGUI

log = structlog.get_logger()


class TabBuilder:
    """Constrói abas de notebook para aplicação principal."""

    def __init__(self, gui: "ApplicationGUI"):
        self.gui = gui
        # Use project_manager injected into GUI (Phase 4 dependency injection)
        self.project_manager = gui.project_manager

    def build_main_controls_tab(self) -> ttk.Frame:
        """Constrói aba de controles principais baseada no tipo de projeto."""
        self.gui.main_controls_frame = ttk.Frame(self.gui.notebook, padding="10")
        self.gui.notebook.add(self.gui.main_controls_frame, text="Controle Principal")

        project_type = self.project_manager.get_project_type()
        self.gui.process_video_btn = None

        controls_container = ttk.Frame(self.gui.main_controls_frame)
        controls_container.pack(fill="x", pady=(0, 10))

        if project_type == "live":
            self._add_recording_buttons(controls_container)
        elif project_type == "pre-recorded":
            self._add_processing_buttons(controls_container)

        # Botão fechar (sempre presente)
        Button(
            controls_container,
            text="Fechar Projeto",
            command=lambda: self.gui.event_dispatcher.publish_event(Events.PROJECT_CLOSE, {}),
        ).pack(side="right", padx=5)

        # Constrói painel de overview (Delegates to GUI/WidgetFactory)
        self.gui._create_project_overview_panel(self.gui.main_controls_frame)

        # Container para widgets lado a lado na parte inferior
        bottom_container = ttk.Frame(self.gui.main_controls_frame)
        bottom_container.pack(fill="x", pady=(5, 10), padx=10)

        # Status de modelo - lado direito (ocupa largura total agora)
        self._build_model_status_section(bottom_container)

        # Constrói widgets específicos de tipo de projeto
        if project_type == "live":
            self._build_live_project_widgets(self.gui.main_controls_frame)

        if self.gui.event_bus_v2:
            self.gui.event_bus_v2.publish(
                Event(
                    type=UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED,
                    data={
                        "reason": "TabBuilder initialization",
                        "append_summary": False,
                        "immediate": False,
                    },
                    source="TabBuilder.build_main_controls_tab",
                )
            )

        return self.gui.main_controls_frame

    def build_zone_tab(self) -> None:
        """Create the tab for ROI and detection zone configuration."""
        self.gui.roi_data = {}
        self.gui._bg_scale = 1.0
        self.gui._bg_offset = (0, 0)
        self.gui._bg_img_size = (0, 0)
        self.gui._canvas_bg_image = None
        self.gui._drawing_buttons_frame = None

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
                pass

        main_pane.bind("<Configure>", _on_pane_configure)

        # 5. ✨ NEW: Create VideoDisplayWidget instead of manual Canvas
        self.gui.video_display = VideoDisplayWidget(
            self.gui.viz_frame, event_bus=self.gui.event_bus, width=800, height=600, bg="gray"
        )
        self.gui.video_display.pack(expand=True, fill="both")

        self.gui._roi_canvas_widget = self.gui.video_display.canvas
        self.gui._roi_canvas_widget.bind("<Configure>", self.gui._on_canvas_configure)

        # 7. ✨ NEW: Create context menu before subscribing to events
        self.gui.roi_context_menu = None
        self.gui.menu_manager.create_roi_context_menu()

        # 8. ✨ NEW: Subscribe to events emitted by the components
        self.gui._subscribe_zone_component_events()

        def _set_initial_sash():
            try:
                main_pane.update_idletasks()
                # Set sash position to a comfortable default
                main_pane.sashpos(0, 450)
            except Exception:
                pass

        main_pane.after(10, _set_initial_sash)
        main_pane.after(50, _set_initial_sash)
        main_pane.after(100, _set_initial_sash)
        main_pane.after(200, _set_initial_sash)

    def build_processing_reports_tab(self) -> None:
        """Create the processing reports tab. Delegates to WidgetFactory."""
        return self.gui.widget_factory.create_processing_reports_tab()

    def build_analysis_tab(self) -> None:
        """Create the analysis tab. Delegates to WidgetFactory."""
        return self.gui.widget_factory.create_analysis_tab_widget()

    def build_configuration_tab(self) -> None:
        """Create the configuration tab. Delegates to WidgetFactory."""
        return self.gui.widget_factory.create_configuration_tab_widget()

    def _add_recording_buttons(self, parent):
        """Adiciona botões de gravação para projetos ao vivo."""
        self.gui.start_rec_btn = Button(
            parent,
            text="Iniciar Gravação",
            command=lambda: self.gui.event_dispatcher.publish_event(Events.RECORDING_START, {}),
        )
        self.gui.start_rec_btn.pack(side="left", padx=5)

        self.gui.stop_rec_btn = Button(
            parent,
            text="Parar Gravação",
            command=lambda: self.gui.event_dispatcher.publish_event(Events.RECORDING_STOP, {}),
            state="disabled",
        )
        self.gui.stop_rec_btn.pack(side="left", padx=5)

    def _add_processing_buttons(self, parent):
        """Adiciona botões de processamento para projetos pré-gravados."""
        ttk.Button(
            parent,
            text="Adicionar e Processar Novos Vídeos/Pastas...",
            command=lambda: self.gui.event_dispatcher.publish_event(
                Events.PROJECT_PROCESS_VIDEOS, {}
            ),
        ).pack(side="left", padx=5)

    def _build_model_status_section(self, parent):
        """Constrói seção de status de modelo."""
        model_status_frame = ttk.LabelFrame(
            parent,
            text="Estado do Modelo de Detecção",
            padding=10,
        )
        model_status_frame.pack(side="left", fill="both", expand=True, padx=(5, 0))
        ttk.Label(
            model_status_frame,
            textvariable=self.gui._active_weight_display_var,
        ).pack(anchor="w")
        ttk.Label(
            model_status_frame,
            textvariable=self.gui._openvino_display_var,
        ).pack(anchor="w", pady=(4, 0))

        button_row = ttk.Frame(model_status_frame)
        button_row.pack(anchor="w", pady=(6, 0))
        ttk.Button(
            button_row,
            text="Calibração Global...",
            command=self.gui._open_global_calibration_window,
        ).pack(side="left", padx=(0, 6))

        if getattr(self.project_manager, "project_path", None):
            ttk.Button(
                button_row,
                text="Calibração e Preferências do Projeto...",
                command=self.gui._open_project_calibration_window,
            ).pack(side="left")

    def _build_live_project_widgets(self, parent):
        """Constrói widgets específicos para projetos ao vivo."""
        self.gui.external_trigger_notice_label = Label(
            parent,
            textvariable=self.gui.external_trigger_notice_var,
            anchor="w",
            justify="left",
            wraplength=600,
            padx=10,
            pady=6,
        )
        self.gui.external_trigger_notice_label.pack(fill="x", pady=(0, 8))
        self.gui._external_notice_default_bg = self.gui.external_trigger_notice_label.cget(
            "background"
        )
        self.gui._external_notice_default_fg = self.gui.external_trigger_notice_label.cget(
            "foreground"
        )

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
