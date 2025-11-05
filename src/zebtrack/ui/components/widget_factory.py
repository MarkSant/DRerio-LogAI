"""
Widget Factory Component for ApplicationGUI.

Responsável por criar widgets, frames, abas e helpers de layout da aplicação.
Centraliza a lógica de construção de UI em um único componente reutilizável.

Categories:
1. Utilitários Simples - formatação e identificadores
2. Construtores Simples - widgets básicos
3. Helpers de Layout - callbacks e configuração de layout
4. Construtores de Abas - abas completas da aplicação
5. Construtores Complexos - frames complexos multi-componente
6. Config Handlers - manipulação de configurações
7. Processadores de Dados - preparação de dados para exibição
"""

import hashlib
from pathlib import Path
from tkinter import Canvas, Frame, Label, StringVar, ttk
from typing import Any

import structlog
import yaml
from pydantic import ValidationError

import zebtrack.settings as settings_module
from zebtrack.ui.window_utils import reset_geometry_if_not_maximized

log = structlog.get_logger()

# Status symbols used in UI
STATUS_SYMBOLS = {
    "arena": "\U0001f3df",  # 🏟
    "rois": "\U0001f3af",  # 🎯
    "trajectory": "\U0001f9ed",  # 🧭
    "summary": "\u03a3",  # Σ
}


class WidgetFactory:
    """
    Factory for creating UI widgets, frames, and tabs.

    Encapsulates all widget creation logic extracted from ApplicationGUI.
    Uses self.gui to access parent GUI state and methods.

    Thread-safety: All UI updates must use gui.root.after(0, ...) pattern.
    """

    def __init__(self, gui):
        """
        Initialize WidgetFactory with reference to parent GUI.

        Args:
            gui: Reference to ApplicationGUI instance
        """
        self.gui = gui

    # ===========================================================================
    # CATEGORIA 1: UTILITÁRIOS SIMPLES
    # ===========================================================================

    def build_status_icon_legend_simple(self, *, include_summary: bool = False) -> str:
        """Compose a compact legend string for the status glyphs."""
        legend_parts = [
            f"{STATUS_SYMBOLS['arena']} ✓ Arena",
            f"{STATUS_SYMBOLS['rois']} ✓ ROIs",
            f"{STATUS_SYMBOLS['trajectory']} ✓ Trajetória",
        ]
        if include_summary:
            legend_parts.append(f"{STATUS_SYMBOLS['summary']} ✓ Sumário")
        legend_parts.append("✗ Ausente")
        return "Legenda: " + " | ".join(legend_parts)

    def get_zone_summary_helper_text(self) -> str:
        """Return helper text for zone summary section."""
        return (
            f"{STATUS_SYMBOLS['summary']} indica vídeos prontos para gerar "
            "trajetórias (arena e ROIs salvos). O valor mostra quantos ainda "
            "aguardam processamento."
        )

    def build_status_icon_legend(self, *, include_summary: bool = False) -> str:
        """
        Compose a compact legend string for the status glyphs.

        Args:
            include_summary: Whether to include summary symbol in legend

        Returns:
            Formatted legend string with status symbols
        """
        legend_parts = [
            f"{STATUS_SYMBOLS['arena']} ✓ Arena",
            f"{STATUS_SYMBOLS['rois']} ✓ ROIs",
            f"{STATUS_SYMBOLS['trajectory']} ✓ Trajetória",
        ]
        if include_summary:
            legend_parts.append(f"{STATUS_SYMBOLS['summary']} ✓ Sumário")
        legend_parts.append("✗ Ausente")
        return "Legenda: " + " | ".join(legend_parts)

    def build_day_title(self, day_value, metadata: dict | None = None) -> str:
        """
        Build formatted day title for display.

        Args:
            day_value: Day value (int, str, or None)
            metadata: Optional metadata dict with day info

        Returns:
            Formatted day title string
        """
        metadata = metadata or {}
        candidate = metadata.get("day_label") or ""
        if not candidate and metadata.get("day") is not None:
            candidate = self.gui._format_day_display(metadata.get("day"))
        if not candidate:
            candidate = self.gui._format_day_display(day_value)
        if not candidate:
            base_value = day_value if day_value not in (None, "") else None
            candidate = str(base_value) if base_value is not None else "Sem Dia"
        candidate_str = str(candidate).strip()
        if not candidate_str:
            candidate_str = "Sem Dia"
        if candidate_str.lower() == "sem dia":
            return "Sem Dia"
        return f"Dia {candidate_str}"

    def build_processing_report_artifact_id(
        self, parent_id: str, artifact_path: str
    ) -> str:
        """
        Create a stable item id for report artifacts while avoiding duplicates.

        Args:
            parent_id: Parent item ID
            artifact_path: Path to artifact file

        Returns:
            Unique file identifier string
        """
        digest_source = f"{parent_id}|{artifact_path}".encode("utf-8", "ignore")
        digest = hashlib.sha1(digest_source).hexdigest()[:16]
        return f"file_{digest}"

    def build_roi_template_identifier(self, template: dict[str, Any]) -> str:
        """
        Build unique identifier for ROI template.

        Args:
            template: Template dictionary

        Returns:
            Template identifier string
        """
        location = template.get("location", "project")
        slug = template.get("slug") or ""
        file_ref = template.get("file") or ""

        if location == "project" and slug:
            return f"{location}:{slug}"

        if file_ref:
            return f"{location}:{file_ref}"

        return f"{location}:{template.get('name', '')}"

    def build_track_options(self, detections: list[tuple]) -> list[str]:
        """
        Build list of track IDs from detections for selector.

        Args:
            detections: List of detection tuples

        Returns:
            Sorted list of track IDs with "Todos" prefix
        """
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

    # ===========================================================================
    # CATEGORIA 2: CONSTRUTORES SIMPLES
    # ===========================================================================

    def build_project_actions(self, parent) -> None:
        """
        Create the project actions controls in the welcome frame.

        Args:
            parent: Parent frame to add buttons to
        """
        project_actions_frame = ttk.LabelFrame(
            parent, text="Ações do Projeto", padding=10
        )
        project_actions_frame.pack(fill="x", pady=10, expand=True)

        ttk.Button(
            project_actions_frame,
            text="Calibração Global (Pesos e Diagnóstico)...",
            command=self.gui._open_global_calibration_window,
        ).pack(fill="x", padx=10, pady=5)
        ttk.Button(
            project_actions_frame,
            text="Analisar Vídeo Único",
            command=self.gui._on_analyze_single_video_clicked,
        ).pack(fill="x", padx=10, pady=5)
        ttk.Button(
            project_actions_frame,
            text="Criar Novo Projeto",
            command=self.gui._create_project_workflow,
        ).pack(fill="x", padx=10, pady=5)
        ttk.Button(
            project_actions_frame,
            text="Abrir Projeto Existente",
            command=self.gui._open_project_workflow,
        ).pack(fill="x", padx=10, pady=5)

    def build_model_status(self, parent) -> None:
        """
        Create the model status display in the welcome frame.

        Args:
            parent: Parent frame to add labels to
        """
        model_status_frame = ttk.LabelFrame(
            parent, text="Estado do Modelo de Detecção", padding=10
        )
        model_status_frame.pack(fill="x", pady=10, expand=True)
        ttk.Label(
            model_status_frame,
            textvariable=self.gui._active_weight_display_var,
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

    def create_zone_summary_cards_section(self) -> None:
        """
        Renderiza os cartões com indicadores numéricos da etapa de zonas.

        Creates summary cards showing:
        - Arena pendente count
        - ROIs pendente count
        - Ready for processing count
        """
        if not getattr(self.gui, "zone_controls_frame", None):
            return

        if (
            self.gui.zone_summary_frame
            and self.gui.zone_summary_frame.winfo_exists()
        ):
            try:
                self.gui.zone_summary_frame.destroy()
            except Exception:
                pass

        self.gui.zone_summary_cards = {}
        self.gui.zone_summary_frame = ttk.LabelFrame(
            self.gui.zone_controls_frame,
            text=f"{STATUS_SYMBOLS['summary']} Indicadores de Preparação",
            padding=10,
        )
        self.gui.zone_summary_frame.pack(fill="x", pady=(0, 5))

        cards_container = ttk.Frame(self.gui.zone_summary_frame)
        cards_container.pack(fill="x")

        card_specs = [
            ("arena_missing", f"{STATUS_SYMBOLS['arena']} Arenas pendentes"),
            ("rois_missing", f"{STATUS_SYMBOLS['rois']} ROIs pendentes"),
            (
                "ready_for_processing",
                f"{STATUS_SYMBOLS['summary']} Prontos para trajetórias",
            ),
        ]

        for idx, (key, title) in enumerate(card_specs):
            card = ttk.Frame(
                cards_container, padding=10, relief="ridge", borderwidth=1
            )
            card.grid(row=0, column=idx, padx=5, pady=5, sticky="nsew")
            cards_container.columnconfigure(idx, weight=1)

            value_var = StringVar(value="0")
            detail_var = StringVar(value="Nenhum vídeo listado")

            ttk.Label(
                card, text=title, font=("TkDefaultFont", 9, "bold")
            ).pack(anchor="w")
            value_label = ttk.Label(
                card, textvariable=value_var, font=("TkDefaultFont", 20, "bold")
            )
            value_label.pack(anchor="w", pady=(5, 0))
            ttk.Label(card, textvariable=detail_var, font=("TkDefaultFont", 8)).pack(
                anchor="w", pady=(2, 0)
            )

            self.gui.zone_summary_cards[key] = {
                "value": value_var,
                "detail": detail_var,
            }

        # Add helper text at bottom
        helper_text = self.gui._get_zone_summary_helper_text()
        if helper_text:
            ttk.Label(
                self.gui.zone_summary_frame,
                text=helper_text,
                font=("TkDefaultFont", 8),
                foreground="gray",
            ).pack(anchor="w", pady=(5, 0))

        # Initial update
        self.gui._update_zone_summary_cards()

    def create_drawing_buttons(self):
        """
        Creates floating undo/redo buttons over the canvas.

        Buttons are positioned in top-right corner of viz_frame.
        """
        if self.gui._drawing_buttons_frame:
            self.gui._drawing_buttons_frame.destroy()

        # Create a frame that floats over the canvas (top-right corner)
        self.gui._drawing_buttons_frame = ttk.Frame(
            self.gui.viz_frame, relief="raised", borderwidth=2
        )

        # Undo button
        undo_btn = ttk.Button(
            self.gui._drawing_buttons_frame,
            text="↶ Desfazer (Ctrl+Z)",
            command=lambda: self.gui._on_drawing_undo(None),
            width=20,
        )
        undo_btn.pack(side="left", padx=2)

        # Redo button
        redo_btn = ttk.Button(
            self.gui._drawing_buttons_frame,
            text="↷ Refazer (Ctrl+Y)",
            command=lambda: self.gui._on_drawing_redo(None),
            width=20,
        )
        redo_btn.pack(side="left", padx=2)

        # Position the frame in top-right corner of canvas
        self.gui._drawing_buttons_frame.place(
            relx=1.0, rely=0.0, anchor="ne", x=-10, y=10
        )

    def create_progress_grid_tab(self):
        """
        Creates the tab for viewing the experimental progress grid.

        Used for live camera projects to show recording progress.
        """
        self.gui.progress_grid_frame = ttk.Frame(self.gui.notebook, padding="10")
        self.gui.notebook.add(
            self.gui.progress_grid_frame, text="Progresso do Experimento"
        )

        # This frame will hold the actual grid of buttons, which is rendered later
        self.gui.grid_container = ttk.Frame(self.gui.progress_grid_frame)
        self.gui.grid_container.pack(expand=True, fill="both")

        # Add a refresh button
        refresh_button = ttk.Button(
            self.gui.progress_grid_frame,
            text="Atualizar Grade",
            command=self.gui._render_progress_grid,
        )
        refresh_button.pack(side="bottom", pady=10)

    # ===========================================================================
    # CATEGORIA 3: HELPERS DE LAYOUT
    # ===========================================================================

    def on_frame_configure(self, event=None):
        """
        Update scroll region when frame size changes.

        Args:
            event: Tkinter configure event
        """
        self.gui.controls_canvas.configure(
            scrollregion=self.gui.controls_canvas.bbox("all")
        )

    def on_canvas_configure_scroll(self, event=None):
        """
        Update frame width when canvas size changes.

        Args:
            event: Tkinter configure event
        """
        canvas_width = (
            event.width if event else self.gui.controls_canvas.winfo_width()
        )
        self.gui.controls_canvas.itemconfig(
            self.gui.controls_canvas_window, width=canvas_width
        )

    def on_canvas_configure(self, event=None):
        """
        Handle canvas resize events to properly scale and center the image.

        Args:
            event: Tkinter configure event
        """
        # Skip if this is not the main roi_canvas being resized
        if event and event.widget != self.gui.roi_canvas:
            return

        if not hasattr(self.gui, "_raw_bg_image") or not self.gui._raw_bg_image:
            if hasattr(self.gui, "_original_image") and self.gui._original_image:
                self.gui._raw_bg_image = self.gui._original_image
            else:
                return

        # Get the current canvas dimensions
        canvas_width = self.gui.roi_canvas.winfo_width()
        canvas_height = self.gui.roi_canvas.winfo_height()

        if canvas_width <= 1 or canvas_height <= 1:
            return

        # Re-scale and center the background image using the new method
        try:
            self.gui.canvas_manager._draw_bg_image_to_canvas()
            # After updating the background, redraw any zones that exist
            if hasattr(self.gui, "controller") and self.gui.controller:
                self.gui.canvas_manager.redraw_zones_from_project_data()
        except Exception as e:
            log.warning("gui.canvas.configure_error", error=str(e))

    def create_scrollable_controls_frame(self, parent):
        """
        Create a scrollable frame for the zone controls.

        Args:
            parent: Parent widget to add scrollable frame to
        """
        # Create a canvas and scrollbar for scrolling
        self.gui.controls_canvas = Canvas(parent, highlightthickness=0)
        self.gui.controls_scrollbar = ttk.Scrollbar(
            parent, orient="vertical", command=self.gui.controls_canvas.yview
        )

        # Create the main scrollable frame inside the canvas
        self.gui.zone_controls_frame = ttk.Frame(self.gui.controls_canvas)

        # Create a frame for the fixed button at the bottom
        self.gui.fixed_button_frame = ttk.Frame(parent)

        # Configure canvas scrolling
        self.gui.controls_canvas.configure(
            yscrollcommand=self.gui.controls_scrollbar.set
        )

        # Pack the scrollbar and canvas
        self.gui.controls_scrollbar.pack(side="right", fill="y")
        self.gui.fixed_button_frame.pack(side="bottom", fill="x", padx=5, pady=5)
        self.gui.controls_canvas.pack(side="left", fill="both", expand=True)

        # Create window in canvas for the scrollable frame
        self.gui.controls_canvas_window = self.gui.controls_canvas.create_window(
            0, 0, anchor="nw", window=self.gui.zone_controls_frame
        )

        # Bind events for proper scrolling behavior
        self.gui.zone_controls_frame.bind(
            "<Configure>", self.on_frame_configure
        )
        self.gui.controls_canvas.bind(
            "<Configure>", self.on_canvas_configure_scroll
        )
        self.gui._bind_mousewheel()

    # ===========================================================================
    # CATEGORIA 4: CONSTRUTORES DE ABAS DELEGADORAS
    # ===========================================================================

    def create_configuration_tab_widget(self) -> None:
        """
        Creates the configuration tab using ConfigEditorWidget.

        Sets up event handlers for config save/reset actions.
        """
        if not self.gui.notebook:
            return

        # Import here to avoid circular dependency
        from zebtrack.ui.components import ConfigEditorWidget

        # Create widget
        self.gui.config_editor_widget = ConfigEditorWidget(
            self.gui.notebook,
            event_bus=self.gui.event_bus,
        )

        # Add to notebook
        self.gui.notebook.add(
            self.gui.config_editor_widget, text="Config. Avançadas"
        )

        # Connect events
        if self.gui.event_bus:
            self.gui._event_bus_handlers["config.save_requested"] = (
                lambda data: self.gui._on_save_global_config_from_widget(
                    data["values"]
                )
            )
            self.gui._event_bus_handlers["config.reset_requested"] = (
                lambda data: self.gui._on_reset_global_config_form_widget()
            )
            self.gui._event_bus_handlers["config.roi_rule_changed"] = (
                lambda data: self.gui._on_roi_rule_change_widget(data["rule"])
            )

        # Load current values
        self.gui._reload_config_editor_values_widget()

    def create_analysis_tab_widget(self):
        """
        Creates the analysis tab using the AnalysisDisplayWidget.

        Sets up event handlers for track selection and cancel actions.
        """
        if not self.gui.notebook:
            return

        # Import here to avoid circular dependency
        from zebtrack.ui.components import AnalysisDisplayWidget
        from zebtrack.ui.events import Events

        # Create the widget
        self.gui.analysis_display_widget = AnalysisDisplayWidget(
            self.gui.notebook,
            event_bus=self.gui.event_bus,
            available_track_options=list(self.gui._available_track_options),
        )

        # Add to notebook
        self.gui.notebook.add(
            self.gui.analysis_display_widget, text="Análise de Vídeo"
        )

        # Connect widget events to GUI handlers
        if self.gui.event_bus:
            self.gui._event_bus_handlers["analysis.track_selected"] = (
                lambda data: self.gui._on_track_selection_changed()
            )
            self.gui._event_bus_handlers["analysis.cancel_requested"] = (
                lambda data: self.gui.event_dispatcher.publish_event(
                    Events.VIDEO_CANCEL_ANALYSIS, {}
                )
            )

        # Set up backward compatibility aliases
        self.gui.video_label = self.gui.analysis_display_widget.video_label
        self.gui.progress_frame = self.gui.analysis_display_widget.progress_frame
        self.gui.progress_bar = self.gui.analysis_display_widget.progress_bar
        self.gui.progress_labels = (
            self.gui.analysis_display_widget.progress_labels
        )
        self.gui.cancel_proc_btn = self.gui.analysis_display_widget.cancel_btn
        self.gui.track_selector_var = (
            self.gui.analysis_display_widget.track_selector_var
        )
        self.gui.track_selector_widget = (
            self.gui.analysis_display_widget.track_selector_widget
        )
        self.gui.social_summary_var = (
            self.gui.analysis_display_widget.social_summary_var
        )

    def create_processing_reports_tab(self) -> None:
        """
        Creates the unified Processing and Reports tab.

        This tab consolidates functionality from the old "Trajectories and Summaries"
        and "Reports" tabs into a single interface for better UX and reduced redundancy.
        """
        if not self.gui.notebook:
            return

        # Clean up existing tab if present
        if (
            self.gui.processing_reports_tab_frame
            and self.gui.processing_reports_tab_frame.winfo_exists()
        ):
            try:
                self.gui.processing_reports_tab_frame.destroy()
            except Exception:
                pass

        # Create tab frame
        self.gui.processing_reports_tab_frame = ttk.Frame(
            self.gui.notebook, padding="10"
        )
        self.gui.notebook.add(
            self.gui.processing_reports_tab_frame, text="Processamento e Relatórios"
        )

        # Import the component
        from zebtrack.ui.components.processing_reports import ProcessingReportsWidget

        # Create the widget with callbacks
        self.gui.processing_reports_widget = ProcessingReportsWidget(
            self.gui.processing_reports_tab_frame,
            event_bus=self.gui.event_bus,
            on_generate_trajectories=self.gui._trigger_batch_trajectory_processing,
            on_export_summaries=self.gui._trigger_parquet_summaries,
            on_generate_partial_report=self.gui._on_processing_reports_generate_partial,
            on_generate_unified_report=self.gui._generate_unified_report,
        )
        self.gui.processing_reports_widget.pack(fill="both", expand=True)

        # Bind double-click event for opening files
        if self.gui.processing_reports_widget.tree:
            self.gui.processing_reports_widget.tree.bind(
                "<Double-Button-1>",
                self.gui._on_processing_reports_item_double_click,
            )

        # Initial refresh
        self.gui._refresh_processing_reports_tab()

    def create_project_overview_panel(self, parent: ttk.Frame) -> None:
        """
        Create the project overview panel using ProjectOverviewWidget.

        Args:
            parent: Parent frame to add panel to
        """
        if not parent:
            return

        if (
            self.gui.project_overview_frame
            and self.gui.project_overview_frame.winfo_exists()
        ):
            try:
                self.gui.project_overview_frame.destroy()
            except Exception:
                pass

        self.gui.project_overview_frame = ttk.LabelFrame(
            parent, text="Resumo do Projeto", padding=10
        )
        self.gui.project_overview_frame.pack(fill="both", expand=True, pady=(10, 10))

        # Import here to avoid circular dependency
        from zebtrack.ui.components import ProjectOverviewWidget

        # Create the ProjectOverviewWidget
        self.gui.project_overview_widget = ProjectOverviewWidget(
            self.gui.project_overview_frame, event_bus=self.gui.event_bus
        )
        self.gui.project_overview_widget.pack(fill="both", expand=True)

        # Subscribe to widget events
        if self.gui.event_bus:
            self.gui.event_bus.subscribe(
                "project.refresh_requested",
                self.gui._handle_project_refresh_requested,
            )
            self.gui.event_bus.subscribe(
                "project.video_double_click",
                self.gui._handle_project_video_double_click,
            )
            self.gui.event_bus.subscribe(
                "project.video_right_click",
                self.gui._handle_project_video_right_click,
            )

        # Separator
        ttk.Separator(
            self.gui.project_overview_frame, orient="horizontal"
        ).pack(fill="x", pady=10)

        # Navigation button
        ttk.Button(
            self.gui.project_overview_frame,
            text="Ir para Processamento e Relatórios →",
            command=self.gui._navigate_to_processing_reports_tab,
        ).pack(fill="x", padx=5, pady=(0, 5))

    # ===========================================================================
    # CATEGORIA 5: CONSTRUTORES COMPLEXOS
    # ===========================================================================

    def create_welcome_frame(self):
        """
        Creates the initial UI for project selection and model configuration.

        This is the main entry screen shown when no project is loaded.
        """
        # Reset title to default (no project)
        self.gui._update_window_title()

        self.gui._cleanup_single_analysis_button()
        # CRITICAL: Force process all pending GUI events before cleanup
        # This ensures all scheduled callbacks are executed
        self.gui.root.update_idletasks()

        # Reset + destroy analysis-related widgets
        self.gui._reset_analysis_widgets()

        # Force final GUI update before creating welcome frame
        self.gui.root.update_idletasks()

        reset_geometry_if_not_maximized(self.gui.root)
        self.gui.welcome_frame = ttk.Frame(self.gui.root, padding="10")
        self.gui.welcome_frame.pack(expand=True, fill="both")

        # --- Logo Image ---
        self.gui._display_welcome_logo()

        # Project actions and model status widgets
        self.build_project_actions(self.gui.welcome_frame)
        self.build_model_status(self.gui.welcome_frame)

    def create_main_control_frame(self):
        """
        Creates the main UI with tabs for controlling the app.

        This is the main screen shown when a project is loaded.
        Creates all tabs and status bar.
        """
        if self.gui.welcome_frame:
            self.gui.welcome_frame.destroy()
        reset_geometry_if_not_maximized(self.gui.root)

        self.gui.notebook = ttk.Notebook(
            self.gui.root, style="Zebtrack.TNotebook"
        )
        self.gui.notebook.pack(expand=True, fill="both", padx=5, pady=5)

        # Bind tab change event to hide analysis overlay when switching tabs
        self.gui.notebook.bind(
            "<<NotebookTabChanged>>", self.gui._on_tab_changed
        )

        # Create the tabs
        self.gui._create_main_controls_tab()
        if self.gui.controller.project_manager.get_project_type() == "live":
            self.create_progress_grid_tab()
        self.gui._create_roi_analysis_tab()
        self.create_processing_reports_tab()  # New unified tab
        self.create_analysis_tab_widget()
        self.create_configuration_tab_widget()

        # Status frame below the notebook
        project_type_str = self.gui.controller.project_manager.get_project_type()
        if project_type_str == "live":
            project_type_display = "Ao Vivo"
        elif project_type_str == "pre-recorded":
            project_type_display = "Pré-gravado"
        else:
            project_type_display = project_type_str

        status_text = (
            f"Projeto: {self.gui.controller.project_manager.get_project_name()} "
            f"({project_type_display})"
        )
        self.gui.status_var.set(status_text)
        status_frame = Frame(self.gui.root)
        status_frame.pack(pady=5, fill="x", padx=10, side="bottom")
        Label(status_frame, textvariable=self.gui.status_var).pack()

        # Ensure analysis UI starts hidden
        self.gui.hide_progress_bar()

    # ===========================================================================
    # CATEGORIA 6: CONFIG HANDLERS
    # ===========================================================================

    def reload_config_editor_values_widget(self) -> None:
        """
        Load current settings into ConfigEditorWidget.

        Reads from zebtrack.settings and populates the config editor form.
        """
        current = settings_module.settings
        if current is None:
            try:
                current = settings_module.load_settings()
                settings_module.settings = current
            except Exception as exc:  # pragma: no cover - defensive UI feedback
                self.gui.show_error(
                    "Erro", f"Não foi possível carregar config.yaml: {exc}"
                )
                return

        values = {
            "video_processing": {
                "fps": self.gui._extract_setting(
                    current, ("video_processing", "fps"), 30
                ),
                "processing_interval": self.gui._extract_setting(
                    current, ("video_processing", "processing_interval"), 10
                ),
                "processing_offset": self.gui._extract_setting(
                    current, ("video_processing", "processing_offset"), 0
                ),
            },
            "trajectory_smoothing": {
                "window_length": self.gui._extract_setting(
                    current, ("trajectory_smoothing", "window_length"), 7
                ),
                "polyorder": self.gui._extract_setting(
                    current, ("trajectory_smoothing", "polyorder"), 3
                ),
            },
            "recorder": {
                "flush_interval_seconds": self.gui._extract_setting(
                    current, ("recorder", "flush_interval_seconds"), 5.0
                ),
                "flush_row_threshold": self.gui._extract_setting(
                    current, ("recorder", "flush_row_threshold"), 500
                ),
            },
            "roi_inclusion_rule": self.gui._extract_setting(
                current, ("roi_inclusion_rule",), "centroid_in"
            ),
            "roi_buffer_radius_value": self.gui._extract_setting(
                current, ("roi_buffer_radius_value",), 0.0
            ),
            "roi_min_bbox_overlap_ratio": self.gui._extract_setting(
                current, ("roi_min_bbox_overlap_ratio",), 0.5
            ),
        }

        if self.gui.config_editor_widget:
            self.gui.config_editor_widget.set_values(values)

    def on_reset_global_config_form_widget(self) -> None:
        """
        Reset ConfigEditorWidget form fields to reflect current settings object.

        Reloads values from settings and shows confirmation message.
        """
        self.reload_config_editor_values_widget()
        self.gui.show_info(
            "Formulário recarregado",
            "Valores restaurados para refletir as configurações atuais.",
        )

    def on_save_global_config_from_widget(self, values: dict) -> None:
        """
        Validate and save config from ConfigEditorWidget values.

        Args:
            values: Dictionary of config values from widget

        Validates values, merges with existing config, saves to config.local.yaml,
        and updates runtime settings.
        """
        try:
            # Extract values (already parsed by widget)
            fps = values["video_processing"]["fps"]
            processing_interval = values["video_processing"]["processing_interval"]
            processing_offset = values["video_processing"]["processing_offset"]
            flush_interval = values["recorder"]["flush_interval_seconds"]
            flush_rows = values["recorder"]["flush_row_threshold"]
            window_length = values["trajectory_smoothing"]["window_length"]
            polyorder = values["trajectory_smoothing"]["polyorder"]

            # Validate
            if fps <= 0:
                raise ValueError("FPS deve ser maior que 0.")
            if processing_interval <= 0:
                raise ValueError("O intervalo de processamento deve ser maior que 0.")
            if processing_offset < 0:
                raise ValueError("O offset deve ser maior ou igual a 0.")
            if flush_interval < 0:
                raise ValueError("O intervalo de flush deve ser >= 0.")
            if flush_rows < 1:
                raise ValueError("O limite de linhas para flush deve ser >= 1.")
            if window_length < 3 or window_length % 2 == 0:
                raise ValueError("Window length deve ser ímpar e pelo menos 3.")
            if polyorder < 1:
                raise ValueError("Polyorder deve ser pelo menos 1.")

        except ValueError as exc:
            self.gui.show_error("Erro de Validação", str(exc))
            return

        update_payload: dict[str, Any] = values

        active_settings = settings_module.settings
        if active_settings is None:
            try:
                active_settings = settings_module.load_settings()
                settings_module.settings = active_settings
            except Exception as exc:
                self.gui.show_error(
                    "Erro", f"Não foi possível carregar config.yaml: {exc}"
                )
                return

        merged = self.gui._deep_merge_dicts(
            active_settings.model_dump(), update_payload
        )

        try:
            validated = settings_module.Settings.model_validate(merged)
        except ValidationError as exc:
            self.gui.show_error("Erro de Validação", str(exc))
            return

        override_path = Path("config.local.yaml")
        try:
            if override_path.exists():
                with open(override_path, encoding="utf-8") as handle:
                    override_content = yaml.safe_load(handle) or {}
            else:
                override_content = {}

            merged_override = self.gui._deep_merge_dicts(
                override_content, update_payload
            )
            with open(override_path, "w", encoding="utf-8") as handle:
                yaml.safe_dump(
                    merged_override,
                    handle,
                    sort_keys=False,
                    allow_unicode=True,
                )
        except Exception as exc:
            self.gui.show_error(
                "Erro", f"Não foi possível salvar config.local.yaml: {exc}"
            )
            return

        if settings_module.settings is None:
            settings_module.settings = validated
        else:
            for field_name in validated.model_fields:
                setattr(
                    settings_module.settings,
                    field_name,
                    getattr(validated, field_name),
                )

        self.reload_config_editor_values_widget()
        self.gui.show_info(
            "Configurações salvas",
            "Alterações registradas em config.local.yaml e aplicadas ao aplicativo.",
        )

    # ===========================================================================
    # CATEGORIA 5: CONSTRUTORES COMPLEXOS - Zone Control Widgets
    # ===========================================================================

    def create_zone_control_widgets(self):
        """
        Create all zone control widgets in the scrollable frame.

        Creates comprehensive zone configuration UI including:
        - Zone summary cards
        - Drawing action buttons
        - Single analysis options
        - ROI template management
        - Video selector tree
        - Zone list
        - Interactive edit buttons
        - ROI inclusion rule panel
        """
        # Call zone summary cards creation (delegated separately)
        self.gui._create_zone_summary_cards_section()

        # --- Drawing Actions ---
        actions_frame = ttk.LabelFrame(
            self.gui.zone_controls_frame, text="Ações de Desenho", padding=10
        )
        actions_frame.pack(fill="x", pady=5)

        # --- Single Analysis Options ---
        self.gui.single_analysis_options_frame = ttk.LabelFrame(
            self.gui.zone_controls_frame,
            text="Opções de Análise de Vídeo Único",
            padding=10,
        )
        # This frame is packed on demand by setup_zone_configuration_for_video

        # ROI options
        self.gui.roi_choice_var = StringVar(value="none")
        ttk.Label(self.gui.single_analysis_options_frame, text="Opções de ROI:").pack(anchor="w")
        ttk.Radiobutton(
            self.gui.single_analysis_options_frame,
            text="Não usar ROIs",
            variable=self.gui.roi_choice_var,
            value="none",
        ).pack(anchor="w", padx=10)
        ttk.Radiobutton(
            self.gui.single_analysis_options_frame,
            text="Desenhar ROIs manualmente",
            variable=self.gui.roi_choice_var,
            value="manual",
        ).pack(anchor="w", padx=10)
        ttk.Radiobutton(
            self.gui.single_analysis_options_frame,
            text="Usar ROIs de template",
            variable=self.gui.roi_choice_var,
            value="template",
        ).pack(anchor="w", padx=10)

        # Frame intervals for analysis and display
        ttk.Label(
            self.gui.single_analysis_options_frame, text="Intervalo de Análise (frames):"
        ).pack(anchor="w", pady=(10, 0))
        ttk.Entry(
            self.gui.single_analysis_options_frame,
            textvariable=self.gui.analysis_interval_var,
            width=10,
        ).pack(anchor="w", padx=10)

        ttk.Label(
            self.gui.single_analysis_options_frame, text="Intervalo de Exibição (frames):"
        ).pack(anchor="w", pady=(5, 0))
        ttk.Entry(
            self.gui.single_analysis_options_frame,
            textvariable=self.gui.display_interval_var,
            width=10,
        ).pack(anchor="w", padx=10)

        # Button for automatic detection
        ttk.Button(
            actions_frame,
            text="Detectar Aquário (Auto)",
            command=self.gui._on_auto_detect_clicked,
        ).pack(fill="x", pady=2)

        # New Entry for stabilization frames
        stabilization_frame = ttk.Frame(actions_frame)
        ttk.Label(stabilization_frame, text="Frames para Análise:").pack(side="left", padx=(0, 5))
        ttk.Entry(
            stabilization_frame, textvariable=self.gui.stabilization_frames_var, width=5
        ).pack(side="left")
        stabilization_frame.pack(fill="x", pady=2, anchor="w")

        # Manual drawing buttons
        ttk.Button(
            actions_frame,
            text="Desenhar Polígono Principal",
            command=self.gui._start_main_arena_drawing,
        ).pack(fill="x", pady=2)

        # ROI button - initially disabled until main arena is drawn
        self.gui.draw_roi_button = ttk.Button(
            actions_frame,
            text="Desenhar Área de Interesse",
            command=self.gui._start_roi_drawing,
            state="disabled",
        )
        self.gui.draw_roi_button.pack(fill="x", pady=2)

        # View toggle button (initially hidden)
        self.gui.toggle_view_btn = ttk.Button(
            actions_frame,
            text="Ver Análise em Progresso",
            command=self.gui._toggle_canvas_view,
            state="disabled",
        )
        self.gui.toggle_view_btn.pack(fill="x", pady=2)

        template_frame = ttk.LabelFrame(
            self.gui.zone_controls_frame,
            text="Templates de ROI",
            padding=10,
        )
        template_frame.pack(fill="x", pady=5)

        template_selector = ttk.Frame(template_frame)
        template_selector.pack(fill="x", pady=(0, 6))

        ttk.Label(template_selector, text="Templates salvos:").pack(side="left", padx=(0, 5))
        self.gui.roi_template_combobox = ttk.Combobox(
            template_selector,
            state="readonly",
            textvariable=self.gui.roi_template_var,
            values=[],
            width=25,
        )
        self.gui.roi_template_combobox.pack(side="left", fill="x", expand=True)
        # Add binding to log selection changes
        self.gui.roi_template_combobox.bind(
            "<<ComboboxSelected>>", self.gui._on_template_combobox_changed
        )

        ttk.Button(
            template_selector,
            text="Aplicar",
            command=self.gui._on_apply_roi_template,
        ).pack(side="left", padx=4)

        template_actions = ttk.Frame(template_frame)
        template_actions.pack(fill="x")

        log.info("gui.zone_tab.creating_template_buttons")

        ttk.Button(
            template_actions,
            text="💾 Salvar Zonas Atuais",
            command=self.gui._on_save_roi_template,
        ).pack(side="left", padx=(0, 4))

        ttk.Button(
            template_actions,
            text="📂 Importar e Aplicar Arquivo...",
            command=self.gui._on_import_and_apply_roi_template,
        ).pack(side="left", padx=(0, 4))

        # Delete button - store reference to control state
        self.gui.delete_template_btn = ttk.Button(
            template_actions,
            text="🗑️ Deletar Template",
            command=self.gui._on_delete_roi_template,
            state="disabled",  # Start disabled
        )
        self.gui.delete_template_btn.pack(side="left")

        log.info(
            "gui.zone_tab.delete_button_created",
            button_exists=self.gui.delete_template_btn is not None,
            button_state=(
                self.gui.delete_template_btn["state"] if self.gui.delete_template_btn else None
            ),
        )

        ttk.Label(
            template_frame,
            text=(
                "Templates armazenam o polígono principal e todas as ROIs "
                "para reutilizar em outros vídeos do projeto."
            ),
            wraplength=280,
            style="Small.TLabel",
        ).pack(anchor="w", pady=(6, 0))

        self.gui._refresh_roi_templates()

        # --- Video Selector ---
        video_selector_frame = ttk.LabelFrame(
            self.gui.zone_controls_frame,
            text="📹 Selecionar Vídeo para Desenho",
            padding=10,
        )
        video_selector_frame.pack(fill="both", pady=5)

        search_frame = ttk.Frame(video_selector_frame)
        search_frame.pack(fill="x", pady=(0, 5))

        ttk.Label(search_frame, text="🔍 Buscar:").pack(side="left", padx=(0, 5))
        self.gui.video_search_var = StringVar()
        self.gui.video_search_var.trace_add("write", lambda *_: self.gui._filter_video_tree())
        ttk.Entry(
            search_frame,
            textvariable=self.gui.video_search_var,
            width=25,
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Button(
            search_frame,
            text="🔄",
            width=3,
            command=lambda: self.gui._populate_video_selector_tree(),
        ).pack(side="left")

        tree_container = ttk.Frame(video_selector_frame)
        tree_container.pack(fill="both", expand=True)

        self.gui.video_selector_tree = ttk.Treeview(
            tree_container,
            columns=("status", "filename"),
            show="tree headings",
            height=10,
            selectmode="browse",
        )
        self.gui.video_selector_tree.heading("#0", text="Hierarquia")
        self.gui.video_selector_tree.heading("status", text="Dados")
        self.gui.video_selector_tree.heading("filename", text="Arquivo")

        self.gui.video_selector_tree.column("#0", width=220, stretch=True)
        self.gui.video_selector_tree.column(
            "status",
            width=120,
            anchor="center",
            stretch=False,
        )
        self.gui.video_selector_tree.column("filename", width=180, stretch=True)

        scrollbar = ttk.Scrollbar(
            tree_container,
            orient="vertical",
            command=self.gui.video_selector_tree.yview,
        )
        self.gui.video_selector_tree.configure(yscrollcommand=scrollbar.set)
        self.gui.video_selector_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.gui.video_selector_tree.bind(
            "<Double-Button-1>",
            self.gui._on_video_tree_double_click,
        )

        ttk.Button(
            video_selector_frame,
            text="📹 Carregar Frame do Vídeo Selecionado",
            command=self.gui._load_selected_video_frame,
        ).pack(pady=(5, 0))

        legend_frame = ttk.Frame(video_selector_frame)
        legend_frame.pack(fill="x", pady=(5, 0))
        ttk.Label(
            legend_frame,
            text=self.gui._build_status_icon_legend(),
            font=("TkDefaultFont", 8),
            foreground="gray",
        ).pack(anchor="w")

        self.gui._populate_video_selector_tree()

        # --- Zone List ---
        zone_list_frame = ttk.LabelFrame(
            self.gui.zone_controls_frame, text="Zonas Definidas", padding=10
        )
        zone_list_frame.pack(fill="x", pady=5)

        from zebtrack.ui.window_utils import create_scrollbar

        self.gui.zone_listbox = ttk.Treeview(
            zone_list_frame,
            columns=("name", "type", "color"),
            show="headings",
            height=6,
        )
        self.gui.zone_listbox.heading("name", text="Nome")
        self.gui.zone_listbox.heading("type", text="Tipo")
        self.gui.zone_listbox.heading("color", text="Cor")

        # Configure column widths
        self.gui.zone_listbox.column("name", width=240, minwidth=160, stretch=True)
        self.gui.zone_listbox.column("type", width=90, minwidth=80, stretch=False)
        self.gui.zone_listbox.column("color", width=70, minwidth=60, stretch=False)

        self.gui.zone_listbox.pack(side="left", fill="both", expand=True)

        # Scrollbar
        scrollbar = create_scrollbar(
            zone_list_frame, orient="vertical", command=self.gui.zone_listbox.yview
        )
        self.gui.zone_listbox.configure(yscrollcommand=scrollbar.set)

        # Bind events
        self.gui.zone_listbox.bind("<Button-3>", self.gui._on_zone_right_click)
        self.gui.zone_listbox.bind("<Double-Button-1>", self.gui._on_zone_double_click)

        # Menu de contexto para ROIs
        self.gui.roi_context_menu = None
        self.gui.menu_manager.create_roi_context_menu()

        scrollbar.pack(side="right", fill="y")

        # --- Interactive Buttons (initially hidden) ---
        # Positioned right after zone list, before ROI Inclusion Rule Panel
        self.gui.interactive_buttons_frame = ttk.Frame(self.gui.zone_controls_frame)
        self.gui.save_arena_btn = ttk.Button(
            self.gui.interactive_buttons_frame,
            text="✅ Salvar Edição",
            command=self.gui._on_save_arena,
        )
        self.gui.save_arena_btn.pack(side="left", fill="x", expand=True, padx=2)
        self.gui.discard_arena_btn = ttk.Button(
            self.gui.interactive_buttons_frame,
            text="❌ Descartar",
            command=self.gui._on_discard_arena,
        )
        self.gui.discard_arena_btn.pack(side="left", fill="x", expand=True, padx=2)
        # This frame is packed later when needed (via pack() in _enter_edit_mode)

        # --- ROI Inclusion Rule Panel ---
        self.gui.roi_inclusion_frame = ttk.LabelFrame(
            self.gui.zone_controls_frame, text="Regra de Inclusão em ROI", padding=10
        )
        self.gui.roi_inclusion_frame.pack(fill="x", pady=5)

        # Rule selection combobox
        rule_frame = ttk.Frame(self.gui.roi_inclusion_frame)
        rule_frame.pack(fill="x", pady=2)
        ttk.Label(rule_frame, text="Regra:").pack(side="left", padx=(0, 5))
        self.gui.roi_rule_combo = ttk.Combobox(
            rule_frame,
            textvariable=self.gui.roi_inclusion_rule_var,
            values=[
                "centroid_in",
                "centroid_in_on_buffered_roi",
                "bbox_intersects",
                "seg_overlap",
            ],
            state="readonly",
            width=30,
        )
        self.gui.roi_rule_combo.pack(side="left", fill="x", expand=True)
        self.gui.roi_rule_combo.bind("<<ComboboxSelected>>", self.gui._on_roi_rule_change)

        # Parameter fields (shown/hidden based on rule)
        self.gui.radius_frame = ttk.Frame(self.gui.roi_inclusion_frame)
        ttk.Label(self.gui.radius_frame, text="Raio de buffer (r):").pack(side="left", padx=(0, 5))
        self.gui.radius_entry = ttk.Entry(
            self.gui.radius_frame, textvariable=self.gui.roi_buffer_radius_var, width=10
        )
        self.gui.radius_entry.pack(side="left", padx=(0, 10))
        ttk.Label(
            self.gui.radius_frame,
            text="Usado para dilatar a ROI. Interpretado em cm quando houver "
            "calibração (px/cm); caso contrário, em pixels.",
            font=("TkDefaultFont", 8),
        ).pack(side="left")

        self.gui.overlap_frame = ttk.Frame(self.gui.roi_inclusion_frame)
        ttk.Label(self.gui.overlap_frame, text="Mín. fração de sobreposição (0–1):").pack(
            side="left", padx=(0, 5)
        )
        self.gui.overlap_entry = ttk.Entry(
            self.gui.overlap_frame, textvariable=self.gui.roi_overlap_ratio_var, width=10
        )
        self.gui.overlap_entry.pack(side="left", padx=(0, 10))
        self.gui.overlap_help_label = ttk.Label(
            self.gui.overlap_frame,
            text="A detecção é considerada dentro da ROI quando a fração de "
            "área do bbox contida na ROI atinge este valor.",
            font=("TkDefaultFont", 8),
        )
        self.gui.overlap_help_label.pack(side="left")

        # Help text that changes based on rule
        self.gui.rule_help_label = ttk.Label(
            self.gui.roi_inclusion_frame,
            text="",
            font=("TkDefaultFont", 8),
            wraplength=400,
            justify="left",
        )
        self.gui.rule_help_label.pack(fill="x", pady=(5, 0))

        # Save settings button
        save_settings_frame = ttk.Frame(self.gui.roi_inclusion_frame)
        save_settings_frame.pack(fill="x", pady=(5, 0))
        ttk.Button(
            save_settings_frame,
            text="Aplicar Configurações",
            command=self.gui._on_apply_roi_settings,
        ).pack(side="right")

        # Initialize display based on current rule
        self.gui._on_roi_rule_change()

    def configure_styles(self) -> None:
        """Configure custom styles for ttk components used by the GUI."""
        style = ttk.Style(self.gui.root)
        self.gui._style = style

        try:
            style.theme_use()
        except Exception:  # pragma: no cover - defensive safeguard
            style.theme_use("default")

        base_background = (
            style.lookup("TNotebook", "background", None)
            or (
                self.gui._ttkbootstrap_style.lookup("TFrame", "background")
                if self.gui._ttkbootstrap_style is not None
                else None
            )
            or "#f6f7fb"
        )
        accent_background = (
            style.lookup("TNotebook.Tab", "background", None, ("selected",))
            or style.lookup("TFrame", "background", None)
            or "#ffffff"
        )
        tab_inactive = style.lookup("TNotebook.Tab", "background", None) or "#dce3ee"
        border_color = (
            style.lookup("TNotebook", "bordercolor", None)
            or style.lookup("TNotebook", "lightcolor", None)
            or "#c5ccd9"
        )
        text_active = style.lookup("TNotebook.Tab", "foreground", None, ("selected",)) or "#1d2733"
        text_inactive = style.lookup("TNotebook.Tab", "foreground", None) or "#4a5568"

        style.configure(
            "Zebtrack.TNotebook",
            background=base_background,
            borderwidth=0,
            tabmargins=(10, 6, 10, 0),
        )

        style.configure(
            "Zebtrack.TNotebook.Tab",
            background=tab_inactive,
            padding=(18, 10),
            font=("Segoe UI", 10, "bold"),
            foreground=text_inactive,
            bordercolor=border_color,
        )

        style.map(
            "Zebtrack.TNotebook.Tab",
            background=[("selected", accent_background), ("!selected", tab_inactive)],
            foreground=[("selected", text_active), ("!selected", text_inactive)],
            bordercolor=[("selected", "#4c6997"), ("!selected", border_color)],
        )

        style.configure(
            "Zebtrack.TNotebook.Tab",
            focuscolor="",
        )
        style.configure("Zebtrack.TNotebook", padding=(4, 4))
