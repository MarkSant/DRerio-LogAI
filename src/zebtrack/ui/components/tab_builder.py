import tkinter as tk
from tkinter import ttk, Button, Label
from typing import TYPE_CHECKING

import structlog

from zebtrack.ui.components.arduino_dashboard import ArduinoDashboardWidget
from zebtrack.ui.events import Events

if TYPE_CHECKING:
    from zebtrack.ui.gui import ApplicationGUI

log = structlog.get_logger()

class TabBuilder:
    """Constrói abas de notebook para aplicação principal."""

    def __init__(self, gui: "ApplicationGUI"):
        self.gui = gui
        self.project_manager = gui.controller.project_manager
        self.notebook = gui.notebook

    def build_main_controls_tab(self) -> ttk.Frame:
        """Constrói aba de controles principais baseada no tipo de projeto."""
        self.gui.main_controls_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.gui.main_controls_frame, text="Controle Principal")

        project_type = self.project_manager.get_project_type()
        self.gui.process_video_btn = None

        controls_container = ttk.Frame(self.gui.main_controls_frame)
        controls_container.pack(fill="x", pady=(0, 10))

        if project_type == "live":
            self._add_recording_buttons(controls_container)
        elif project_type == "pre-recorded":
            self._add_processing_buttons(controls_container)
            self._add_interval_settings(self.gui.main_controls_frame)

        # Botão fechar (sempre presente)
        Button(
            controls_container,
            text="Fechar Projeto",
            command=lambda: self.gui.event_dispatcher.publish_event(Events.PROJECT_CLOSE, {}),
        ).pack(side="right", padx=5)

        # Constrói painel de overview (Delegates to GUI/WidgetFactory)
        self.gui._create_project_overview_panel(self.gui.main_controls_frame)

        # Constrói status de modelo
        self._build_model_status_section(self.gui.main_controls_frame)

        # Constrói widgets específicos de tipo de projeto
        if project_type == "live":
            self._build_live_project_widgets(self.gui.main_controls_frame)

        self.gui._request_overview_refresh()
        return self.gui.main_controls_frame

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
        # Primary action: add/process new videos (legacy location)
        ttk.Button(
            parent,
            text="Adicionar e Processar Novos Vídeos/Pastas...",
            command=lambda: self.gui.event_dispatcher.publish_event(
                Events.PROJECT_PROCESS_VIDEOS, {}
            ),
        ).pack(side="left", padx=5)

    def _add_interval_settings(self, parent):
        """Adiciona controles de configuração de intervalo."""
        # Project-wide interval settings
        intervals_frame = ttk.LabelFrame(
            parent, text="Intervalos de Processamento", padding=10
        )
        # Note: In legacy code it was packed *after* controls_container? No, in legacy code:
        # controls_container.pack
        # intervals_frame.pack (inside elif)
        # Button(Close) inside controls_container.
        # So in legacy code, intervals_frame appeared BELOW controls_container.
        # Here I call it after `_add_processing_buttons`.
        intervals_frame.pack(fill="x", pady=10, padx=10)

        # Analysis interval
        analysis_label_frame = ttk.Frame(intervals_frame)
        analysis_label_frame.pack(fill="x", pady=2)
        ttk.Label(analysis_label_frame, text="Intervalo de Análise (frames):").pack(side="left")
        ttk.Entry(analysis_label_frame, textvariable=self.gui.analysis_interval_var, width=10).pack(
            side="right"
        )

        # Display interval
        display_label_frame = ttk.Frame(intervals_frame)
        display_label_frame.pack(fill="x", pady=2)
        ttk.Label(display_label_frame, text="Intervalo de Exibição (frames):").pack(side="left")
        ttk.Entry(display_label_frame, textvariable=self.gui.display_interval_var, width=10).pack(
            side="right"
        )

    def _build_model_status_section(self, parent):
        """Constrói seção de status de modelo."""
        model_status_frame = ttk.LabelFrame(
            parent,
            text="Estado do Modelo de Detecção",
            padding=10,
        )
        model_status_frame.pack(fill="x", pady=(10, 10))
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
        self.gui._external_notice_default_bg = self.gui.external_trigger_notice_label.cget("background")
        self.gui._external_notice_default_fg = self.gui.external_trigger_notice_label.cget("foreground")

        # Create Arduino dashboard widget
        self.gui.arduino_dashboard_widget = ArduinoDashboardWidget(
            parent,
            event_bus=self.gui.event_bus,
            project_manager=self.project_manager,
        )
        self.gui.arduino_dashboard_widget.pack(fill="both", expand=False, pady=(0, 10))
        self.gui.clear_external_trigger_notice()
