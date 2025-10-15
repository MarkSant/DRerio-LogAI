"""
Zone controls widget component - zone drawing and management UI.
"""

from tkinter import StringVar, ttk

import structlog

from zebtrack.ui.components.base import BaseWidget
from zebtrack.ui.event_bus import EventBus

log = structlog.get_logger()


class ZoneControlsWidget(BaseWidget):
    """
    Reusable zone control widget for drawing and managing zones/ROIs.

    Provides:
    - Drawing action buttons (auto-detect, manual polygon, ROI)
    - Zone list display (Treeview)
    - ROI template management
    - ROI inclusion rule configuration
    - Video selector for loading frames

    Events emitted:
    - zone.auto_detect_clicked: User clicked auto-detect button
    - zone.draw_main_polygon: User wants to draw main arena polygon
    - zone.draw_roi: User wants to draw an ROI
    - zone.template_apply: User wants to apply a template
    - zone.template_save: User wants to save current zones as template
    - zone.template_import: User wants to import a template file
    - zone.video_selected: User selected a video from the tree
    - zone.video_frame_load: User wants to load a frame from selected video
    - zone.list_item_selected: User selected a zone from the list
    - zone.list_item_double_click: User double-clicked a zone
    - zone.list_item_right_click: User right-clicked a zone
    - zone.roi_rule_changed: User changed the ROI inclusion rule
    - zone.roi_settings_apply: User clicked apply ROI settings
    """

    def __init__(self, parent, event_bus: EventBus | None = None, **kwargs):
        """
        Initialize the zone controls widget.

        Args:
            parent: Parent Tkinter widget
            event_bus: Optional event bus for emitting events
            **kwargs: Additional arguments passed to BaseWidget
        """
        # State variables
        self.roi_choice_var = StringVar(value="none")
        self.analysis_interval_var = StringVar(value="10")
        self.display_interval_var = StringVar(value="10")
        self.stabilization_frames_var = StringVar(value="10")
        self.roi_template_var = StringVar(value="")
        self.video_search_var = StringVar()
        self.roi_inclusion_rule_var = StringVar(value="bbox_intersects")
        self.roi_buffer_radius_var = StringVar(value="0.5")
        self.roi_overlap_ratio_var = StringVar(value="0.10")

        # Widget references
        self.draw_roi_button: ttk.Button | None = None
        self.toggle_view_btn: ttk.Button | None = None
        self.roi_template_combobox: ttk.Combobox | None = None
        self.video_selector_tree: ttk.Treeview | None = None
        self.zone_listbox: ttk.Treeview | None = None
        self.save_arena_btn: ttk.Button | None = None
        self.discard_arena_btn: ttk.Button | None = None
        self.interactive_buttons_frame: ttk.Frame | None = None
        self.roi_rule_combo: ttk.Combobox | None = None
        self.radius_frame: ttk.Frame | None = None
        self.overlap_frame: ttk.Frame | None = None
        self.rule_help_label: ttk.Label | None = None

        super().__init__(parent, event_bus=event_bus, **kwargs)

    def _build_ui(self) -> None:
        """Build the zone controls widget UI."""
        # Create a scrollable frame for all controls
        from tkinter import Canvas

        from zebtrack.ui.window_utils import create_scrollbar

        # Container for scrollable content
        self.controls_canvas = Canvas(self, highlightthickness=0)
        scrollbar = create_scrollbar(self, orient="vertical", command=self.controls_canvas.yview)

        self.zone_controls_frame = ttk.Frame(self.controls_canvas)

        # Configure canvas scrolling
        self.controls_canvas.configure(yscrollcommand=scrollbar.set)
        self.controls_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Create window in canvas for the scrollable frame
        self.controls_canvas.create_window((0, 0), window=self.zone_controls_frame, anchor="nw")

        # Bind to configure event to update scrollregion
        self.zone_controls_frame.bind(
            "<Configure>",
            lambda e: self.controls_canvas.configure(scrollregion=self.controls_canvas.bbox("all")),
        )

        # Build individual sections
        self._build_drawing_actions()
        self._build_single_analysis_options()
        self._build_template_section()
        self._build_video_selector()
        self._build_zone_list()
        self._build_interactive_buttons()
        self._build_roi_inclusion_panel()

    def _build_drawing_actions(self) -> None:
        """Build the drawing actions section."""
        actions_frame = ttk.LabelFrame(
            self.zone_controls_frame, text="Ações de Desenho", padding=10
        )
        actions_frame.pack(fill="x", pady=5)

        # Auto-detect button
        ttk.Button(
            actions_frame,
            text="Detectar Aquário (Auto)",
            command=self._on_auto_detect_clicked,
        ).pack(fill="x", pady=2)

        # Stabilization frames entry
        stabilization_frame = ttk.Frame(actions_frame)
        ttk.Label(stabilization_frame, text="Frames para Análise:").pack(side="left", padx=(0, 5))
        ttk.Entry(stabilization_frame, textvariable=self.stabilization_frames_var, width=5).pack(
            side="left"
        )
        stabilization_frame.pack(fill="x", pady=2, anchor="w")

        # Manual polygon button
        ttk.Button(
            actions_frame,
            text="Desenhar Polígono Principal",
            command=self._on_draw_main_polygon_clicked,
        ).pack(fill="x", pady=2)

        # ROI button (initially disabled)
        self.draw_roi_button = ttk.Button(
            actions_frame,
            text="Desenhar Área de Interesse",
            command=self._on_draw_roi_clicked,
            state="disabled",
        )
        self.draw_roi_button.pack(fill="x", pady=2)

        # View toggle button (initially disabled)
        self.toggle_view_btn = ttk.Button(
            actions_frame,
            text="Ver Análise em Progresso",
            command=self._on_toggle_view_clicked,
            state="disabled",
        )
        self.toggle_view_btn.pack(fill="x", pady=2)

    def _build_single_analysis_options(self) -> None:
        """Build the single analysis options section."""
        self.single_analysis_options_frame = ttk.LabelFrame(
            self.zone_controls_frame,
            text="Opções de Análise de Vídeo Único",
            padding=10,
        )
        # Initially hidden - packed on demand

        # ROI options
        ttk.Label(self.single_analysis_options_frame, text="Opções de ROI:").pack(anchor="w")
        ttk.Radiobutton(
            self.single_analysis_options_frame,
            text="Não usar ROIs",
            variable=self.roi_choice_var,
            value="none",
        ).pack(anchor="w", padx=10)
        ttk.Radiobutton(
            self.single_analysis_options_frame,
            text="Desenhar ROIs manualmente",
            variable=self.roi_choice_var,
            value="manual",
        ).pack(anchor="w", padx=10)
        ttk.Radiobutton(
            self.single_analysis_options_frame,
            text="Usar ROIs de template",
            variable=self.roi_choice_var,
            value="template",
        ).pack(anchor="w", padx=10)

        # Frame intervals
        ttk.Label(self.single_analysis_options_frame, text="Intervalo de Análise (frames):").pack(
            anchor="w", pady=(10, 0)
        )
        ttk.Entry(
            self.single_analysis_options_frame,
            textvariable=self.analysis_interval_var,
            width=10,
        ).pack(anchor="w", padx=10)

        ttk.Label(self.single_analysis_options_frame, text="Intervalo de Exibição (frames):").pack(
            anchor="w", pady=(5, 0)
        )
        ttk.Entry(
            self.single_analysis_options_frame,
            textvariable=self.display_interval_var,
            width=10,
        ).pack(anchor="w", padx=10)

    def _build_template_section(self) -> None:
        """Build the ROI template section."""
        template_frame = ttk.LabelFrame(
            self.zone_controls_frame, text="Templates de ROI", padding=10
        )
        template_frame.pack(fill="x", pady=5)

        # Template selector
        template_selector = ttk.Frame(template_frame)
        template_selector.pack(fill="x", pady=(0, 6))

        ttk.Label(template_selector, text="Templates salvos:").pack(side="left", padx=(0, 5))
        self.roi_template_combobox = ttk.Combobox(
            template_selector,
            state="readonly",
            textvariable=self.roi_template_var,
            values=[],
            width=25,
        )
        self.roi_template_combobox.pack(side="left", fill="x", expand=True)

        ttk.Button(template_selector, text="Aplicar", command=self._on_apply_template_clicked).pack(
            side="left", padx=4
        )

        # Template actions
        template_actions = ttk.Frame(template_frame)
        template_actions.pack(fill="x")

        ttk.Button(
            template_actions,
            text="💾 Salvar Zonas Atuais",
            command=self._on_save_template_clicked,
        ).pack(side="left", padx=(0, 4))
        ttk.Button(
            template_actions,
            text="📂 Importar e Aplicar Arquivo...",
            command=self._on_import_template_clicked,
        ).pack(side="left")

        # Help text
        ttk.Label(
            template_frame,
            text=(
                "Templates armazenam o polígono principal e todas as ROIs "
                "para reutilizar em outros vídeos do projeto."
            ),
            wraplength=280,
            style="Small.TLabel",
        ).pack(anchor="w", pady=(6, 0))

    def _build_video_selector(self) -> None:
        """Build the video selector section."""
        video_selector_frame = ttk.LabelFrame(
            self.zone_controls_frame,
            text="📹 Selecionar Vídeo para Desenho",
            padding=10,
        )
        video_selector_frame.pack(fill="both", pady=5)

        # Search bar
        search_frame = ttk.Frame(video_selector_frame)
        search_frame.pack(fill="x", pady=(0, 5))

        ttk.Label(search_frame, text="🔍 Buscar:").pack(side="left", padx=(0, 5))
        self.video_search_var.trace_add("write", lambda *_: self._on_video_search_changed())
        ttk.Entry(search_frame, textvariable=self.video_search_var, width=25).pack(
            side="left", fill="x", expand=True, padx=(0, 5)
        )
        ttk.Button(search_frame, text="🔄", width=3, command=self._on_video_refresh_clicked).pack(
            side="left"
        )

        # Treeview
        tree_container = ttk.Frame(video_selector_frame)
        tree_container.pack(fill="both", expand=True)

        from zebtrack.ui.window_utils import create_scrollbar

        self.video_selector_tree = ttk.Treeview(
            tree_container,
            columns=("status", "filename"),
            show="tree headings",
            height=10,
            selectmode="browse",
        )
        self.video_selector_tree.heading("#0", text="Hierarquia")
        self.video_selector_tree.heading("status", text="Dados")
        self.video_selector_tree.heading("filename", text="Arquivo")

        self.video_selector_tree.column("#0", width=220, stretch=True)
        self.video_selector_tree.column("status", width=120, anchor="center", stretch=False)
        self.video_selector_tree.column("filename", width=180, stretch=True)

        scrollbar = create_scrollbar(
            tree_container, orient="vertical", command=self.video_selector_tree.yview
        )
        self.video_selector_tree.configure(yscrollcommand=scrollbar.set)
        self.video_selector_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Bind events
        self.video_selector_tree.bind("<Double-Button-1>", self._on_video_tree_double_click)

        # Load frame button
        ttk.Button(
            video_selector_frame,
            text="📹 Carregar Frame do Vídeo Selecionado",
            command=self._on_load_video_frame_clicked,
        ).pack(pady=(5, 0))

    def _build_zone_list(self) -> None:
        """Build the zone list section."""
        zone_list_frame = ttk.LabelFrame(
            self.zone_controls_frame, text="Zonas Definidas", padding=10
        )
        zone_list_frame.pack(fill="x", pady=5)

        from zebtrack.ui.window_utils import create_scrollbar

        self.zone_listbox = ttk.Treeview(
            zone_list_frame,
            columns=("name", "type", "color"),
            show="headings",
            height=6,
        )
        self.zone_listbox.heading("name", text="Nome")
        self.zone_listbox.heading("type", text="Tipo")
        self.zone_listbox.heading("color", text="Cor")

        # Configure column widths
        self.zone_listbox.column("name", width=240, minwidth=160, stretch=True)
        self.zone_listbox.column("type", width=90, minwidth=80, stretch=False)
        self.zone_listbox.column("color", width=70, minwidth=60, stretch=False)

        self.zone_listbox.pack(side="left", fill="both", expand=True)

        # Scrollbar
        scrollbar = create_scrollbar(
            zone_list_frame, orient="vertical", command=self.zone_listbox.yview
        )
        self.zone_listbox.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        # Bind events
        self.zone_listbox.bind("<Button-3>", self._on_zone_right_click)
        self.zone_listbox.bind("<Double-Button-1>", self._on_zone_double_click)

    def _build_interactive_buttons(self) -> None:
        """Build the interactive editing buttons (initially hidden)."""
        self.interactive_buttons_frame = ttk.Frame(self.zone_controls_frame)

        self.save_arena_btn = ttk.Button(
            self.interactive_buttons_frame,
            text="✅ Salvar Edição",
            command=self._on_save_arena_clicked,
        )
        self.save_arena_btn.pack(side="left", fill="x", expand=True, padx=2)

        self.discard_arena_btn = ttk.Button(
            self.interactive_buttons_frame,
            text="❌ Descartar",
            command=self._on_discard_arena_clicked,
        )
        self.discard_arena_btn.pack(side="left", fill="x", expand=True, padx=2)

        # Frame is packed later when needed

    def _build_roi_inclusion_panel(self) -> None:
        """Build the ROI inclusion rule configuration panel."""
        self.roi_inclusion_frame = ttk.LabelFrame(
            self.zone_controls_frame, text="Regra de Inclusão em ROI", padding=10
        )
        self.roi_inclusion_frame.pack(fill="x", pady=5)

        # Rule selection
        rule_frame = ttk.Frame(self.roi_inclusion_frame)
        rule_frame.pack(fill="x", pady=2)

        ttk.Label(rule_frame, text="Regra:").pack(side="left", padx=(0, 5))
        self.roi_rule_combo = ttk.Combobox(
            rule_frame,
            textvariable=self.roi_inclusion_rule_var,
            values=[
                "centroid_in",
                "centroid_in_on_buffered_roi",
                "bbox_intersects",
                "seg_overlap",
            ],
            state="readonly",
            width=30,
        )
        self.roi_rule_combo.pack(side="left", fill="x", expand=True)
        self.roi_rule_combo.bind("<<ComboboxSelected>>", self._on_roi_rule_changed)

        # Buffer radius parameter
        self.radius_frame = ttk.Frame(self.roi_inclusion_frame)
        ttk.Label(self.radius_frame, text="Raio de buffer (r):").pack(side="left", padx=(0, 5))
        ttk.Entry(self.radius_frame, textvariable=self.roi_buffer_radius_var, width=10).pack(
            side="left", padx=(0, 10)
        )
        ttk.Label(
            self.radius_frame,
            text="Usado para dilatar a ROI. Interpretado em cm quando houver "
            "calibração (px/cm); caso contrário, em pixels.",
            font=("TkDefaultFont", 8),
        ).pack(side="left")

        # Overlap ratio parameter
        self.overlap_frame = ttk.Frame(self.roi_inclusion_frame)
        ttk.Label(self.overlap_frame, text="Mín. fração de sobreposição (0–1):").pack(
            side="left", padx=(0, 5)
        )
        ttk.Entry(self.overlap_frame, textvariable=self.roi_overlap_ratio_var, width=10).pack(
            side="left", padx=(0, 10)
        )
        ttk.Label(
            self.overlap_frame,
            text="A detecção é considerada dentro da ROI quando a fração de "
            "área do bbox contida na ROI atinge este valor.",
            font=("TkDefaultFont", 8),
        ).pack(side="left")

        # Help text
        self.rule_help_label = ttk.Label(
            self.roi_inclusion_frame,
            text="",
            font=("TkDefaultFont", 8),
            wraplength=400,
            justify="left",
        )
        self.rule_help_label.pack(fill="x", pady=(5, 0))

        # Apply button
        save_settings_frame = ttk.Frame(self.roi_inclusion_frame)
        save_settings_frame.pack(fill="x", pady=(5, 0))
        ttk.Button(
            save_settings_frame,
            text="Aplicar Configurações",
            command=self._on_apply_roi_settings_clicked,
        ).pack(side="right")

    # Event handlers that emit events to the event bus

    def _on_auto_detect_clicked(self) -> None:
        """Handle auto-detect button click."""
        self.emit_event(
            "zone.auto_detect_clicked",
            {"stabilization_frames": int(self.stabilization_frames_var.get() or 10)},
        )

    def _on_draw_main_polygon_clicked(self) -> None:
        """Handle draw main polygon button click."""
        self.emit_event("zone.draw_main_polygon", {})

    def _on_draw_roi_clicked(self) -> None:
        """Handle draw ROI button click."""
        self.emit_event("zone.draw_roi", {})

    def _on_toggle_view_clicked(self) -> None:
        """Handle toggle view button click."""
        self.emit_event("zone.toggle_view", {})

    def _on_apply_template_clicked(self) -> None:
        """Handle apply template button click."""
        self.emit_event("zone.template_apply", {"template_name": self.roi_template_var.get()})

    def _on_save_template_clicked(self) -> None:
        """Handle save template button click."""
        self.emit_event("zone.template_save", {})

    def _on_import_template_clicked(self) -> None:
        """Handle import template button click."""
        self.emit_event("zone.template_import", {})

    def _on_video_search_changed(self) -> None:
        """Handle video search text change."""
        self.emit_event("zone.video_search_changed", {"search_text": self.video_search_var.get()})

    def _on_video_refresh_clicked(self) -> None:
        """Handle video refresh button click."""
        self.emit_event("zone.video_refresh", {})

    def _on_video_tree_double_click(self, event) -> None:
        """Handle video tree double-click."""
        selection = self.video_selector_tree.selection()
        if selection:
            item_id = selection[0]
            self.emit_event("zone.video_double_click", {"item_id": item_id})

    def _on_load_video_frame_clicked(self) -> None:
        """Handle load video frame button click."""
        selection = self.video_selector_tree.selection()
        if selection:
            item_id = selection[0]
            self.emit_event("zone.video_frame_load", {"item_id": item_id})

    def _on_zone_right_click(self, event) -> None:
        """Handle zone list right-click."""
        selection = self.zone_listbox.selection()
        if selection:
            item_id = selection[0]
            self.emit_event(
                "zone.list_item_right_click",
                {"item_id": item_id, "x": event.x_root, "y": event.y_root},
            )

    def _on_zone_double_click(self, event) -> None:
        """Handle zone list double-click."""
        selection = self.zone_listbox.selection()
        if selection:
            item_id = selection[0]
            self.emit_event("zone.list_item_double_click", {"item_id": item_id})

    def _on_save_arena_clicked(self) -> None:
        """Handle save arena button click."""
        self.emit_event("zone.arena_save", {})

    def _on_discard_arena_clicked(self) -> None:
        """Handle discard arena button click."""
        self.emit_event("zone.arena_discard", {})

    def _on_roi_rule_changed(self, event) -> None:
        """Handle ROI rule change."""
        self.emit_event("zone.roi_rule_changed", {"rule": self.roi_inclusion_rule_var.get()})

    def _on_apply_roi_settings_clicked(self) -> None:
        """Handle apply ROI settings button click."""
        self.emit_event(
            "zone.roi_settings_apply",
            {
                "rule": self.roi_inclusion_rule_var.get(),
                "buffer_radius": float(self.roi_buffer_radius_var.get() or 0.5),
                "overlap_ratio": float(self.roi_overlap_ratio_var.get() or 0.10),
            },
        )

    # Public API for controlling widget state

    def set_draw_roi_enabled(self, enabled: bool) -> None:
        """Enable or disable the draw ROI button."""
        if self.draw_roi_button:
            self.draw_roi_button.config(state="normal" if enabled else "disabled")

    def set_toggle_view_enabled(self, enabled: bool) -> None:
        """Enable or disable the toggle view button."""
        if self.toggle_view_btn:
            self.toggle_view_btn.config(state="normal" if enabled else "disabled")

    def show_single_analysis_options(self) -> None:
        """Show the single analysis options frame."""
        if hasattr(self, "single_analysis_options_frame"):
            self.single_analysis_options_frame.pack(
                fill="x", pady=5, before=self.zone_controls_frame.winfo_children()[1]
            )

    def hide_single_analysis_options(self) -> None:
        """Hide the single analysis options frame."""
        if hasattr(self, "single_analysis_options_frame"):
            self.single_analysis_options_frame.pack_forget()

    def show_interactive_buttons(self) -> None:
        """Show the interactive editing buttons."""
        if self.interactive_buttons_frame:
            # Pack before ROI inclusion frame
            self.interactive_buttons_frame.pack(fill="x", pady=5, before=self.roi_inclusion_frame)

    def hide_interactive_buttons(self) -> None:
        """Hide the interactive editing buttons."""
        if self.interactive_buttons_frame:
            self.interactive_buttons_frame.pack_forget()

    def update_template_list(self, templates: list[str]) -> None:
        """Update the template combobox with available templates."""
        if self.roi_template_combobox:
            self.roi_template_combobox.config(values=templates)

    def clear_zone_list(self) -> None:
        """Clear all items from the zone list."""
        if self.zone_listbox:
            for item in self.zone_listbox.get_children():
                self.zone_listbox.delete(item)

    def add_zone_to_list(self, zone_id: str, name: str, zone_type: str, color: str) -> None:
        """Add a zone to the zone list."""
        if self.zone_listbox:
            self.zone_listbox.insert("", "end", iid=zone_id, values=(name, zone_type, color))
