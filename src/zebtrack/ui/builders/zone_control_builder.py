"""
Zone Control Builder for creating zone configuration and drawing widgets.

Extracted from WidgetFactory to separate concern of zone control construction.
"""

from datetime import datetime
from tkinter import BooleanVar, StringVar, ttk
from typing import TYPE_CHECKING

import structlog

from zebtrack.ui import payloads
from zebtrack.ui.window_utils import create_scrollbar

if TYPE_CHECKING:
    from zebtrack.ui.components.zone_context_panel import ZoneContextPanel

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
        # Etapa 4 — Zone tab context panel (built on demand by
        # create_zone_control_widgets so headless unit tests don't pay for it).
        self.zone_context_panel: ZoneContextPanel | None = None
        # Audit Erro 4 (2026-05-25): opt-in flag that the user toggles before
        # Concluir to ask ZebTrack to reuse the current polygon as a template
        # in the next auto-detection runs. Lazily created in
        # ``_ensure_reuse_template_var`` because BooleanVar() requires a
        # default Tk root (headless unit tests instantiate the builder
        # without a real Tk).
        self._reuse_arena_template_var: BooleanVar | None = None

    def _ensure_reuse_template_var(self) -> BooleanVar:
        """Lazily create the reuse-template BooleanVar.

        Returns the existing instance or constructs one bound to the GUI
        root window (which exists by the time the widget tree is built).
        """
        if self._reuse_arena_template_var is None:
            master = getattr(self.gui, "root", None)
            self._reuse_arena_template_var = BooleanVar(master=master, value=False)
        return self._reuse_arena_template_var

    @property
    def reuse_arena_template_var(self) -> BooleanVar | None:
        """Public accessor — returns ``None`` until the widget is built."""
        return self._reuse_arena_template_var

    def _on_roi_rule_change(self, event=None) -> None:
        """Toggle visibility of ROI parameter frames based on the selected rule.

        This handles the <<ComboboxSelected>> event from the ROI rule combobox
        and the initial display setup at build time.
        """
        rule = self.gui.roi_inclusion_rule_var.get()

        # Hide all parameter frames first
        if hasattr(self.gui, "radius_frame") and self.gui.radius_frame:
            self.gui.radius_frame.pack_forget()
        if hasattr(self.gui, "overlap_frame") and self.gui.overlap_frame:
            self.gui.overlap_frame.pack_forget()

        if rule == "centroid_in":
            help_text = (
                "Considera dentro quando o centróide do animal está dentro do "
                "polígono da ROI. Simples e rápido; pode perder entradas parciais "
                "(ex.: cabeça entra primeiro)."
            )
        elif rule == "centroid_in_on_buffered_roi":
            if self.gui.radius_frame:
                self.gui.radius_frame.pack(fill="x", pady=2)
            help_text = (
                "Igual ao centróide, porém com ROI dilatada por r para capturar "
                "entradas parciais (ex.: cabeça). r em cm se houver calibração; "
                "senão em px."
            )
        elif rule == "bbox_intersects":
            if self.gui.overlap_frame:
                self.gui.overlap_frame.pack(fill="x", pady=2)
            if hasattr(self.gui, "overlap_help_label") and self.gui.overlap_help_label:
                self.gui.overlap_help_label.config(
                    text="A detecção é considerada dentro da ROI quando a fração "
                    "de área do bbox contida na ROI atinge este valor."
                )
            help_text = (
                "Considera dentro quando o retângulo do animal (bbox) sobrepõe "
                "a ROI ao menos pela fração definida. Captura entradas parciais; "
                "pode superestimar em bordas."
            )
        elif rule == "seg_overlap":
            if self.gui.overlap_frame:
                self.gui.overlap_frame.pack(fill="x", pady=2)
            if hasattr(self.gui, "overlap_help_label") and self.gui.overlap_help_label:
                self.gui.overlap_help_label.config(
                    text="Requer dados de máscara. Se não houver, selecione outra regra."
                )
            help_text = (
                "Considera dentro com base na sobreposição da máscara do animal "
                "com a ROI. Requer segmentação; mais preciso e mais custoso."
            )
        else:
            help_text = ""

        if hasattr(self.gui, "rule_help_label") and self.gui.rule_help_label:
            self.gui.rule_help_label.config(text=help_text)

    def _emit_apply_roi_settings(self) -> None:
        """Emit DETECTOR_UPDATE_PARAMETERS event with current ROI settings from UI."""
        from zebtrack.ui import payloads
        from zebtrack.ui.event_bus_v2 import Event, UIEvents

        if self.event_bus_v2:
            self.event_bus_v2.publish(
                Event(
                    type=UIEvents.DETECTOR_UPDATE_PARAMETERS,
                    data=payloads.DetectorUpdateParametersPayload(
                        rule=self.gui.roi_inclusion_rule_var.get(),
                        buffer_radius=float(self.gui.roi_buffer_radius_var.get() or 0.5),
                        overlap_ratio=float(self.gui.roi_overlap_ratio_var.get() or 0.10),
                    ),
                    source="ZoneControlBuilder._emit_apply_roi_settings",
                )
            )
        else:
            log.warning("zone_control_builder.apply_roi_settings.no_event_bus")

    def _refresh_video_tree_dual_mode(self, filter_text: str | None = None):
        """Refresh video tree via Event Bus.

        Args:
            filter_text: Optional filter text for video tree
        """
        # NEW PATH - Event-Driven Architecture v4.0
        if self.event_bus_v2:
            from zebtrack.ui import payloads
            from zebtrack.ui.event_bus_v2 import Event, UIEvents

            self.event_bus_v2.publish(
                Event(
                    type=UIEvents.VIDEO_TREE_REFRESH_REQUESTED,
                    data=payloads.VideoTreeRefreshRequestedPayload(filter_text=filter_text),
                    source="ZoneControlBuilder._refresh_video_tree_dual_mode",
                )
            )
        else:
            log.warning("zone_control_builder.refresh_tree.no_event_bus")

    def _apply_arena_template_choice(self) -> None:
        """Persist or drop the arena template based on the user's checkbox.

        Audit Erro 4 (2026-05-25): the "Reaproveitar este polígono em
        próximas autodetecções" checkbox is the explicit opt-in gate. When
        checked at Concluir time, copy the currently active arena polygon
        into ``project_data["arena_template"]`` so the next call to
        ``live_calibration_coordinator.run_live_calibration`` can seed the
        preview with it instead of running detection from scratch. When
        unchecked, drop any pre-existing template so it doesn't leak into
        the next video.
        """
        controller = getattr(self.gui, "controller", None)
        if controller is None or controller.project_manager is None:
            return

        pm = controller.project_manager
        project_data = getattr(pm, "project_data", None)
        if not isinstance(project_data, dict):
            return

        # The lazy var may still be None if the user opened/closed the project
        # without the zone controls ever being built (defensive fallback).
        reuse_var = self._reuse_arena_template_var
        reuse = bool(reuse_var.get()) if reuse_var is not None else False

        if not reuse:
            if project_data.pop("arena_template", None) is not None:
                log.info("zone_control_builder.arena_template.discarded")
            return

        # Pull the latest confirmed polygon from the active zone data.
        try:
            zone_data = pm.get_zone_data()
        except Exception:
            log.debug("zone_control_builder.arena_template.load_failed", exc_info=True)
            return

        polygon = list(getattr(zone_data, "polygon", []) or [])
        if not polygon:
            log.info("zone_control_builder.arena_template.skip_empty_polygon")
            project_data.pop("arena_template", None)
            return

        project_data["arena_template"] = {
            "polygon": [list(point) for point in polygon],
            "created_at": datetime.now().isoformat(),
        }
        log.info(
            "zone_control_builder.arena_template.saved",
            points=len(polygon),
        )

    def _on_conclude_video(self):
        """Handle 'Concluir Edição do Vídeo' button click."""
        # Fluxo de vídeo único de teste: "Concluir" deve INICIAR a análise.
        # O usuário conclui as zonas (incl. multi-aquário auto-detectado) e espera
        # que isso dispare o processamento — não há etapa de "marcar lote" aqui.
        # Delega ao mesmo caminho do botão "Iniciar Análise de Vídeo Único", que
        # valida zonas/config, trata edição de polígono e publica
        # VIDEO_START_SINGLE_PROCESSING. Gated em ``pending_single_video_path``,
        # então projetos e fluxo live mantêm o comportamento original (commit de
        # zonas + resume), intactos.
        if getattr(self.gui, "pending_single_video_path", None):
            single_video_workflow = getattr(self.gui, "single_video_workflow", None)
            if single_video_workflow is not None:
                log.info("zone_control_builder.conclude_video.single_video_start")
                single_video_workflow._on_start_single_video_processing_clicked()
                return

        # 1. Save Project (Persist flags and data)
        if hasattr(self.gui, "controller") and self.gui.controller.project_manager:
            try:
                self._apply_arena_template_choice()
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

        # Clear the dirty flag — zones are now fully committed
        if hasattr(self.gui, "_zones_dirty"):
            self.gui._zones_dirty = False

        self._refresh_video_tree_dual_mode()

        # The tree refresh above only rebuilds the drawing-tab video selector.
        # The main-control per-video grid (project overview) is a separate view;
        # without an explicit refresh it keeps showing stale arena/ROI badges
        # after Concluir. Force an overview rebuild so both views agree.
        video_selector_manager = getattr(self.gui, "video_selector_manager", None)
        if video_selector_manager is not None:
            try:
                video_selector_manager.request_overview_refresh(
                    reason="zones_concluded", force=True
                )
            except Exception:  # except Exception justified: refresh must not break Concluir
                log.debug(
                    "zone_control_builder.conclude_video.overview_refresh_failed",
                    exc_info=True,
                )

        from zebtrack.ui.event_bus_v2 import Event, UIEvents

        if hasattr(self.gui, "event_bus") and self.gui.event_bus:
            # 2. Commit an in-progress interactive edit, but ONLY when one is
            # actually active. ZONE_SAVE_ARENA → CanvasManager.save_arena() falls
            # back to save_manual_arena(edited_polygon_points) when no zone is
            # being edited; in the live auto-detect flow edited_polygon_points is
            # empty, so emitting it unconditionally would overwrite the freshly
            # detected polygon with an empty one. Gate on the same flag save_arena
            # itself reads (CanvasManager.current_editing_zone).
            canvas_manager = getattr(self.gui, "canvas_manager", None)
            editing_active = bool(
                getattr(canvas_manager, "current_editing_zone", None)
                or getattr(self.gui, "current_editing_zone", None)
            )
            has_edited_points = bool(getattr(self.gui, "edited_polygon_points", None))
            if editing_active and has_edited_points:
                self.gui.event_bus.publish(
                    Event(type=UIEvents.ZONE_SAVE_ARENA, data=payloads.EmptyPayload())
                )
                log.info("zone_control_builder.conclude_video.zone_saved_event_emitted")

            # 3. Resume any pending live-recording session.
            # When a live recording is deferred (LIVE_RECORDING_PENDING banner
            # visible), "✅ Concluir" must ask the user whether to start the
            # countdown now, then switch to the recording/analysis view and
            # resume. For pre-recorded projects (no pending session) we keep the
            # legacy behaviour: publish a resume that is a safe no-op.
            zone_controls = getattr(self.gui, "zone_controls", None)
            has_pending = bool(zone_controls and zone_controls.has_pending_live_session())

            if has_pending:
                from tkinter import messagebox

                start_now = messagebox.askyesno(
                    "Iniciar Gravação",
                    "Zonas concluídas.\n\nIniciar a contagem regressiva para a gravação agora?",
                )
                if start_now:
                    # Switch to the recording/analysis view, then resume → the
                    # countdown and recording start there.
                    self.gui.event_bus.publish(
                        Event(
                            type=UIEvents.UI_NAVIGATE_TO_ANALYSIS_VIEW,
                            data=payloads.EmptyPayload(),
                        )
                    )
                    self.gui.event_bus.publish(
                        Event(
                            type=UIEvents.LIVE_RECORDING_RESUME_REQUESTED,
                            data=payloads.LiveRecordingResumeRequestedPayload(experiment_id=None),
                        )
                    )
                    log.info("zone_control_builder.conclude_video.live_resume_confirmed")
                else:
                    # User declined — keep the pending banner so they can start
                    # later via "▶️ Iniciar Gravação".
                    log.info("zone_control_builder.conclude_video.live_resume_declined")
            else:
                # No pending live session: safe no-op resume (pre-recorded).
                self.gui.event_bus.publish(
                    Event(
                        type=UIEvents.LIVE_RECORDING_RESUME_REQUESTED,
                        data=payloads.LiveRecordingResumeRequestedPayload(experiment_id=None),
                    )
                )
                log.info("zone_control_builder.conclude_video.live_resume_requested")

        # 4. Optional: Feedback
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
        self.gui.widget_factory.create_zone_summary_cards_section()

        # --- Calibration Context Panel (Etapa 4) ---------------------------
        # Compact summary of: active source · aquarium model · polygon
        # provenance badge ("auto" / "manual" / "Não definido"). Listens for
        # LIVE_POLYGON_SOURCE_CHANGED so the badge updates the moment the
        # live calibration flow tags the polygon.
        # Local import: zebtrack.ui.components.__init__ pulls WidgetFactory,
        # which pulls ZoneWidgetsBuilder, which pulls back into this module —
        # so eager import at the top would deadlock the loader.
        from zebtrack.ui.components.zone_context_panel import ZoneContextPanel

        self.zone_context_panel = ZoneContextPanel(
            event_bus=self.event_bus_v2,
            project_manager=getattr(self.gui, "project_manager", None),
            weight_manager=getattr(getattr(self.gui, "controller", None), "weight_manager", None),
            root=getattr(self.gui, "root", None),
        )
        context_frame = self.zone_context_panel.build(self.gui.zone_controls_frame)
        context_frame.pack(fill="x", pady=(0, 5))

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
            command=self.gui.single_video_workflow.on_auto_detect_clicked,
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
            command=self.gui.analysis_view_controller.toggle_canvas_view,
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

        # Audit Erro 4 (2026-05-25): seed the existing template flag from
        # project_data so the checkbox reflects what was previously confirmed
        # (a project re-open should keep the user's last choice).
        try:
            initial_reuse = bool(
                getattr(self.gui, "controller", None)
                and self.gui.controller.project_manager.project_data.get("arena_template", {}).get(
                    "polygon"
                )
            )
        except (AttributeError, KeyError, TypeError):
            initial_reuse = False
        reuse_var = self._ensure_reuse_template_var()
        reuse_var.set(initial_reuse)

        ttk.Checkbutton(
            actions_frame,
            text="Reaproveitar este polígono em próximas autodetecções",
            variable=reuse_var,
        ).pack(fill="x", pady=(2, 4))

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
        # Update delete button state when template selection changes
        self.gui.roi_template_combobox.bind(
            "<<ComboboxSelected>>",
            lambda _e: self.gui.roi_template_manager._update_delete_button_state(),
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
            command=self.gui.roi_template_manager.save_template,
        ).pack(side="left", padx=(0, 4))

        ttk.Button(
            template_actions,
            text="📂 Importar e Aplicar Arquivo...",
            command=self.gui.dialog_manager.import_and_apply_roi_template,
        ).pack(side="left", padx=(0, 4))

        # Delete button - store reference to control state
        self.gui.delete_template_btn = ttk.Button(
            template_actions,
            text="🗑️ Deletar Template",
            command=self.gui.roi_template_manager.delete_template,
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

        self.gui.roi_template_manager.refresh_templates()

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
            lambda e: self.gui.canvas_manager.load_selected_video_frame(),
        )

        ttk.Button(
            video_selector_frame,
            text="📹 Carregar Frame do Vídeo Selecionado",
            command=self.gui.canvas_manager.load_selected_video_frame,
        ).pack(pady=(5, 0))

        # 3.2. Legend section
        legend_frame = ttk.Frame(video_selector_frame)
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
        self.gui.zone_listbox.bind("<Button-3>", self.gui.menu_manager.show_roi_context_menu)
        self.gui.zone_listbox.bind(
            "<Double-Button-1>",
            lambda e: self.gui.canvas_manager.edit_selected_zone_vertices(),
        )

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
            command=self.gui.canvas_manager.discard_arena,
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
        self.gui.roi_rule_combo.bind("<<ComboboxSelected>>", self._on_roi_rule_change)

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
        ttk.Label(self.gui.overlap_frame, text="Mín. fração de sobreposição (0-1):").pack(
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
            command=self._emit_apply_roi_settings,
        ).pack(side="right")

        # Initialize display based on current rule
        self._on_roi_rule_change()
