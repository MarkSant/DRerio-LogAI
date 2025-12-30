"""
Zone Control Builder for creating zone configuration and drawing widgets.

Extracted from WidgetFactory to separate concern of zone control construction.
"""

from tkinter import StringVar, ttk

import structlog

from zebtrack.ui.window_utils import create_scrollbar

log = structlog.get_logger()


class ZoneControlBuilder:
    """
    Builder for creating zone configuration and drawing widgets.
    """

    def __init__(self, gui, event_bus_v2=None):
        """
        Initialize ZoneControlBuilder.

        Args:
            gui: Reference to ApplicationGUI instance
            event_bus_v2: EventBusV2 instance for v4.0 Event-Driven Architecture (optional)
        """
        self.gui = gui
        self.event_bus_v2 = event_bus_v2

    def _refresh_video_tree_dual_mode(self, filter_text: str | None = None):
        """Refresh video tree via Event Bus.

        Args:
            filter_text: Optional filter text for video tree
        """
        # NEW PATH - Event-Driven Architecture v4.0
        if self.event_bus_v2:
            from zebtrack.ui.event_bus_v2 import Event, UIEvents

            self.event_bus_v2.publish(
                Event(
                    type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
                    data={"filter_text": filter_text},
                    source="ZoneControlBuilder._refresh_video_tree_dual_mode",
                )
            )
        else:
            log.warning("zone_control_builder.refresh_tree.no_event_bus")

    def _on_conclude_video(self):
        """Handle 'Concluir Edição do Vídeo' button click."""
        # 1. Save Project (Persist flags and data)
        if hasattr(self.gui, "controller") and self.gui.controller.project_manager:
            try:
                self.gui.controller.project_manager.save_project()
            except Exception as e:
                # In Single Video Mode, project might not be created yet.
                # This is expected and safe to ignore for "Conclude" action which mostly updates UI.
                if "ProjectInvalidError" in str(
                    type(e).__name__
                ) or "caminho do projeto não definido" in str(e):
                    log.debug("zone_control_builder.save_project.skipped", reason=str(e))
                else:
                    log.error("zone_control_builder.save_project.failed", error=str(e))

        self._refresh_video_tree_dual_mode()

        # 2. Emit zone saved event to resume pending recording (if any)
        from zebtrack.ui.events import Events

        if hasattr(self.gui, "event_bus") and self.gui.event_bus:
            self.gui.event_bus.publish_event(Events.ZONE_SAVE_ARENA, {})
            log.info("zone_control_builder.conclude_video.zone_saved_event_emitted")

        # 3. Optional: Feedback
        if hasattr(self.gui, "set_status"):
            self.gui.set_status("Edição concluída. Dados salvos e indicadores atualizados.")

    def create_zone_control_widgets(self) -> None:
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

        # Conclude Video Button (Explicit user request)
        ttk.Separator(actions_frame, orient="horizontal").pack(fill="x", pady=5)
        ttk.Button(
            actions_frame,
            text="✅ Concluir Edição do Vídeo",
            command=self._on_conclude_video,
            style="Accent.TButton",
        ).pack(fill="x", pady=2)

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
            command=lambda: self._refresh_video_tree_dual_mode(),
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

        # 3.2. Legend section
        legend_frame = ttk.Frame(controls_container)
        legend_frame.pack(fill="x", padx=10, pady=(5, 5))

        self.status_legend_label = ttk.Label(
            legend_frame,
            text=self.gui.widget_factory.build_status_icon_legend_simple(),
            foreground="gray",
            font=("TkDefaultFont", 8),
        )

        self._refresh_video_tree_dual_mode()

        # --- Zone List ---
        zone_list_frame = ttk.LabelFrame(
            self.gui.zone_controls_frame, text="Zonas Definidas", padding=10
        )
        zone_list_frame.pack(fill="x", pady=5)

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
