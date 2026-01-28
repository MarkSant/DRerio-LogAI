"""Zone controls widget component - zone drawing and management UI."""

import tkinter as tk
from tkinter import Menu, StringVar, ttk

import structlog

from zebtrack.ui.components.base import BaseWidget
from zebtrack.ui.event_bus import EventBus
from zebtrack.ui.events import Events

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

    def __init__(
        self,
        parent,
        event_bus: EventBus | None = None,
        drawing_actions_parent: ttk.Frame | None = None,
        template_actions_parent: ttk.Frame | None = None,
        **kwargs,
    ):
        """
        Initialize the zone controls widget.

        Args:
            parent: Parent Tkinter widget
            event_bus: Optional event bus for emitting events
            drawing_actions_parent: Optional parent frame for drawing actions (default: self)
            template_actions_parent: Optional parent frame for template actions (default: self)
            **kwargs: Additional arguments passed to BaseWidget
        """
        self.drawing_actions_parent = drawing_actions_parent
        self.template_actions_parent = template_actions_parent

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

        # Multi-aquarium state variables
        self.aquarium_count_var = tk.IntVar(value=1)
        self.active_aquarium_var = tk.IntVar(value=0)  # 0 = Aquarium 1, 1 = Aquarium 2
        # False = parallel (1 pass), True = sequential (2 passes) - default True for better accuracy
        self.sequential_processing_var = tk.BooleanVar(value=True)
        # Apply processing mode to all videos (default True)
        self.apply_to_all_var = tk.BooleanVar(value=True)

        # Widget references
        self.draw_roi_button: ttk.Button | None = None
        self.toggle_view_btn: ttk.Button | None = None
        self.video_tree_toggle_btn: ttk.Button | None = None
        self.roi_template_combobox: ttk.Combobox | None = None
        self.video_selector_tree: ttk.Treeview | None = None
        self.zone_listbox: ttk.Treeview | None = None
        self.save_arena_btn: ttk.Button | None = None
        self.discard_arena_btn: ttk.Button | None = None
        self.interactive_buttons_frame: ttk.Frame | None = None
        self.controls_canvas_window: int | None = None
        self.roi_rule_combo: ttk.Combobox | None = None
        self.radius_frame: ttk.Frame | None = None
        self.overlap_frame: ttk.Frame | None = None
        self.rule_help_label: ttk.Label | None = None
        self._video_tree_expanded = True

        # Multi-aquarium widget references
        self.aquarium_selector_frame: ttk.LabelFrame | None = None
        self.aquarium_radio_1: ttk.Radiobutton | None = None
        self.aquarium_radio_2: ttk.Radiobutton | None = None
        self.processing_mode_frame: ttk.Frame | None = None
        self.parallel_radio: ttk.Radiobutton | None = None
        self.sequential_radio: ttk.Radiobutton | None = None

        super().__init__(parent, event_bus=event_bus, **kwargs)

    def _build_ui(self) -> None:
        """Build the zone controls widget UI."""
        # Create a scrollable frame for all controls
        from tkinter import Canvas

        from zebtrack.ui.window_utils import create_scrollbar

        # Create a frame for fixed buttons at the bottom (not scrollable)
        self.fixed_button_frame = ttk.Frame(self)
        self.fixed_button_frame.pack(side="bottom", fill="x", padx=5, pady=5)

        # Container for scrollable content
        self.controls_canvas = Canvas(self, highlightthickness=0)
        scrollbar = create_scrollbar(self, orient="vertical", command=self.controls_canvas.yview)

        self.zone_controls_frame = ttk.Frame(self.controls_canvas)

        # Configure canvas scrolling
        self.controls_canvas.configure(yscrollcommand=scrollbar.set)
        self.controls_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Create window in canvas for the scrollable frame
        self.controls_canvas_window = self.controls_canvas.create_window(
            (0, 0), window=self.zone_controls_frame, anchor="nw"
        )

        # Bind to configure event to update scrollregion
        self.zone_controls_frame.bind(
            "<Configure>",
            lambda e: self.controls_canvas.configure(scrollregion=self.controls_canvas.bbox("all")),
        )

        # Build individual sections
        # Note: Order matters for the side panel, but external parents are handled independently.

        # 1. Top of Viz Frame (if parent provided) OR Top of Left Panel
        self._build_drawing_actions()
        self._build_aquarium_selector()  # Multi-aquarium support
        self._build_interactive_buttons()

        # 2. Left Panel Components (Always in zone_controls_frame)
        self._build_zone_list()
        self._build_roi_inclusion_panel()
        self._build_video_selector()

        # 3. Bottom of Viz Frame (if parent provided) OR Left Panel
        self._build_template_section()

        # Removed unwanted section: self._build_single_analysis_options()

    def _build_drawing_actions(self) -> None:
        """Build the drawing actions section."""
        # Use external parent if provided, else default to side panel
        parent = (
            self.drawing_actions_parent if self.drawing_actions_parent else self.zone_controls_frame
        )

        actions_frame = ttk.LabelFrame(parent, text="Ações de Desenho", padding=5)
        # If in side panel, pack vertically. If in top bar, maybe horizontal?
        # For now, let's keep packing simple.
        actions_frame.pack(fill="x", pady=5, padx=5)

        # Container for buttons to allow grid or side-by-side layout if needed
        btn_container = ttk.Frame(actions_frame)
        btn_container.pack(fill="x")

        # Auto-detect button
        self.auto_detect_button = ttk.Button(
            btn_container,
            text="Detectar Aquário (Auto)",
            command=self._on_auto_detect_clicked,
        )
        self.auto_detect_button.pack(side="left", fill="x", expand=True, padx=2, pady=2)

        # Manual polygon button
        self.draw_arena_button = ttk.Button(
            btn_container,
            text="Polígono Principal",
            command=self._on_draw_main_polygon_clicked,
        )
        self.draw_arena_button.pack(side="left", fill="x", expand=True, padx=2, pady=2)

        # ROI button (initially disabled)
        self.draw_roi_button = ttk.Button(
            btn_container,
            text="Área de Interesse (ROI)",
            command=self._on_draw_roi_clicked,
            state="disabled",
        )
        self.draw_roi_button.pack(side="left", fill="x", expand=True, padx=2, pady=2)

        # Conclude Video Button (Next to ROI button)
        self.conclude_video_btn = ttk.Button(
            btn_container,
            text="✅ Concluir",
            command=self._on_conclude_video_clicked,
            state="disabled",
            style="Accent.TButton",
        )
        self.conclude_video_btn.pack(side="left", fill="x", expand=True, padx=2, pady=2)

        # Stabilization frames entry - compact version
        stabilization_frame = ttk.Frame(actions_frame)
        stabilization_frame.pack(fill="x", pady=2, anchor="w")

        ttk.Label(stabilization_frame, text="Suavização (frames):").pack(side="left", padx=(0, 5))
        ttk.Entry(stabilization_frame, textvariable=self.stabilization_frames_var, width=5).pack(
            side="left"
        )
        ttk.Label(
            stabilization_frame,
            text="(reduz ruído na detecção auto)",
            font=("TkDefaultFont", 8),
            foreground="gray",
        ).pack(side="left", padx=(5, 0))

    def _build_aquarium_selector(self) -> None:
        """Build the multi-aquarium selector section.

        This section allows selecting which aquarium to work with when
        the video has 2 aquariums configured.

        Layout:
        ┌─ Aquário Ativo ─────────────────────────┐
        │  ○ Aquário 1 (Esquerda)                 │
        │  ○ Aquário 2 (Direita)                  │
        │  ────────────────────────────────────── │
        │  Modo de Processamento:                 │
        │  ○ Simultâneo (1 passagem)              │
        │  ○ Sequencial (2 passagens)             │
        └─────────────────────────────────────────┘
        """
        parent = (
            self.drawing_actions_parent if self.drawing_actions_parent else self.zone_controls_frame
        )

        self.aquarium_selector_frame = ttk.LabelFrame(parent, text="🐟 Aquário Ativo", padding=5)
        # Initially hidden - shown only when 2 aquariums are detected
        # self.aquarium_selector_frame.pack(fill="x", pady=5, padx=5)

        # Radio buttons for aquarium selection
        radio_container = ttk.Frame(self.aquarium_selector_frame)
        radio_container.pack(fill="x")

        self.aquarium_radio_1 = ttk.Radiobutton(
            radio_container,
            text="Aquário 1 (Esquerda)",
            variable=self.active_aquarium_var,
            value=0,
            command=self._on_aquarium_selected,
        )
        self.aquarium_radio_1.pack(side="left", padx=(0, 15))

        self.aquarium_radio_2 = ttk.Radiobutton(
            radio_container,
            text="Aquário 2 (Direita)",
            variable=self.active_aquarium_var,
            value=1,
            command=self._on_aquarium_selected,
        )
        self.aquarium_radio_2.pack(side="left")

        # Separator between aquarium selection and processing mode
        ttk.Separator(self.aquarium_selector_frame, orient="horizontal").pack(
            fill="x", pady=(10, 5)
        )

        # Processing mode section
        self.processing_mode_frame = ttk.Frame(self.aquarium_selector_frame)
        self.processing_mode_frame.pack(fill="x")

        ttk.Label(
            self.processing_mode_frame,
            text="Modo de Processamento:",
            font=("TkDefaultFont", 9, "bold"),
        ).pack(anchor="w")

        self.parallel_radio = ttk.Radiobutton(
            self.processing_mode_frame,
            text="Simultâneo (1 passagem, mais rápido)",
            variable=self.sequential_processing_var,
            value=False,
            command=self._on_processing_mode_changed,
        )
        self.parallel_radio.pack(anchor="w", padx=(10, 0))

        self.sequential_radio = ttk.Radiobutton(
            self.processing_mode_frame,
            text="Sequencial (2 passagens, 1 aquário por vez)",
            variable=self.sequential_processing_var,
            value=True,
            command=self._on_processing_mode_changed,
        )
        self.sequential_radio.pack(anchor="w", padx=(10, 0))

        # Apply to all checkbox
        self.apply_to_all_checkbox = ttk.Checkbutton(
            self.processing_mode_frame,
            text="Aplicar a todos os vídeos",
            variable=self.apply_to_all_var,
        )
        self.apply_to_all_checkbox.pack(anchor="w", padx=(10, 0), pady=(5, 0))

        # Help text
        ttk.Label(
            self.processing_mode_frame,
            text="Sequencial: processa o vídeo completo para cada aquário separadamente",
            font=("TkDefaultFont", 8),
            foreground="gray",
        ).pack(anchor="w", padx=(10, 0), pady=(2, 0))

    def _build_interactive_buttons(self) -> None:
        """Build the interactive editing buttons (initially hidden)."""
        # If drawing_actions_parent is provided, these buttons likely go there too
        parent = (
            self.drawing_actions_parent if self.drawing_actions_parent else self.zone_controls_frame
        )

        self.interactive_buttons_frame = ttk.Frame(parent)

        self.save_arena_btn = ttk.Button(
            self.interactive_buttons_frame,
            text="✅ Salvar Edição",
            command=self._on_save_arena_clicked,
        )
        self.save_arena_btn.pack(side="left", fill="x", expand=True, padx=5, pady=5)

        self.discard_arena_btn = ttk.Button(
            self.interactive_buttons_frame,
            text="❌ Descartar",
            command=self._on_discard_arena_clicked,
        )
        self.discard_arena_btn.pack(side="left", fill="x", expand=True, padx=5, pady=5)

        # Finish Drawing button - for completing polygon without double-click
        self.finish_drawing_btn = ttk.Button(
            self.interactive_buttons_frame,
            text="✓ Finalizar Desenho",
            command=self._on_finish_drawing_clicked,
        )
        self.finish_drawing_btn.pack(side="left", fill="x", expand=True, padx=5, pady=5)
        self.discard_arena_btn.pack(side="left", fill="x", expand=True, padx=5, pady=5)

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
        # Use external parent if provided, else default to side panel
        parent = (
            self.template_actions_parent
            if self.template_actions_parent
            else self.zone_controls_frame
        )
        is_horizontal = self.template_actions_parent is not None

        template_frame = ttk.LabelFrame(parent, text="Templates de ROI", padding=5)
        template_frame.pack(fill="x", pady=5, padx=5)

        # Container for layout
        container = ttk.Frame(template_frame)
        container.pack(fill="x")

        if is_horizontal:
            # Compact Horizontal Layout for Bottom Panel
            ttk.Label(container, text="Template:").pack(side="left", padx=(0, 5))
            self.roi_template_combobox = ttk.Combobox(
                container,
                state="readonly",
                textvariable=self.roi_template_var,
                values=[],
                width=20,
            )
            self.roi_template_combobox.pack(side="left", padx=(0, 5))

            ttk.Button(container, text="Aplicar", command=self._on_apply_template_clicked).pack(
                side="left", padx=(0, 10)
            )

            ttk.Button(
                container,
                text="💾 Salvar",
                command=self._on_save_template_clicked,
            ).pack(side="left", padx=(0, 5))

            ttk.Button(
                container,
                text="📂 Importar",
                command=self._on_import_template_clicked,
            ).pack(side="left")

            # Help icon/tooltip could go here instead of full text
        else:
            # Vertical Layout for Side Panel
            template_selector = ttk.Frame(container)
            template_selector.pack(fill="x", pady=(0, 6))

            ttk.Label(template_selector, text="Template:").pack(side="left", padx=(0, 5))
            self.roi_template_combobox = ttk.Combobox(
                template_selector,
                state="readonly",
                textvariable=self.roi_template_var,
                values=[],
                width=15,
            )
            self.roi_template_combobox.pack(side="left", fill="x", expand=True)

            ttk.Button(
                template_selector, text="Aplicar", command=self._on_apply_template_clicked
            ).pack(side="left", padx=4)

            # Template actions
            template_actions = ttk.Frame(container)
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
                wraplength=200,
                style="Small.TLabel",
            ).pack(anchor="w", pady=(6, 0))

    def _build_video_selector(self) -> None:
        """Build the video selector section."""
        # ALWAYS use side panel for video selector, regardless of other parents
        parent = self.zone_controls_frame

        video_selector_frame = ttk.LabelFrame(
            parent,
            text="📹 Selecionar Vídeo para Desenho",
            padding=5,
        )
        # Allow this frame to expand vertically to fill space
        video_selector_frame.pack(fill="both", expand=True, pady=5, padx=5)

        # Search bar
        search_frame = ttk.Frame(video_selector_frame)
        search_frame.pack(fill="x", pady=(0, 5))

        ttk.Label(search_frame, text="🔍 Buscar:").pack(side="left", padx=(0, 5))
        self.video_search_var.trace_add("write", lambda *_: self._on_video_search_changed())
        ttk.Entry(search_frame, textvariable=self.video_search_var, width=25).pack(
            side="left", fill="x", expand=True, padx=(0, 5)
        )
        self.video_tree_toggle_btn = ttk.Button(
            search_frame,
            text="Recolher tudo",
            width=14,
            command=self._toggle_video_tree_nodes,
        )
        self.video_tree_toggle_btn.pack(side="left", padx=(5, 0))

        # Treeview
        tree_container = ttk.Frame(video_selector_frame)
        tree_container.pack(fill="both", expand=True)

        from zebtrack.ui.window_utils import create_scrollbar

        self.video_selector_tree = ttk.Treeview(
            tree_container,
            columns=("status", "filename"),
            show="tree headings",
            height=15,  # Increased height for better vertical distribution
            selectmode="browse",
        )
        self.video_selector_tree.heading("#0", text="Hierarquia")
        self.video_selector_tree.heading("status", text="Dados")
        self.video_selector_tree.heading("filename", text="Arquivo")

        self.video_selector_tree.column("#0", width=180, minwidth=140, stretch=True)
        self.video_selector_tree.column("status", width=60, anchor="center", stretch=False)
        self.video_selector_tree.column("filename", width=120, stretch=True)

        scrollbar = create_scrollbar(
            tree_container, orient="vertical", command=self.video_selector_tree.yview
        )
        self.video_selector_tree.configure(yscrollcommand=scrollbar.set)
        self.video_selector_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Configure tag styles
        TAG_STYLES = {
            "ready_full": {"background": "#d4edda", "foreground": "#1e4620"},
            "ready_partial": {"background": "#fff3cd", "foreground": "#5c470b"},
            "ready_missing": {"background": "#f8d7da", "foreground": "#842029"},
        }
        for tag, style in TAG_STYLES.items():
            self.video_selector_tree.tag_configure(tag, **style)

        # Bind events
        self.video_selector_tree.bind("<Double-Button-1>", self._on_video_tree_double_click)
        self.video_selector_tree.bind("<Button-3>", self._on_video_tree_right_click)

        # Create context menu for video tree
        self._create_video_tree_context_menu()

        # Load frame button
        ttk.Button(
            video_selector_frame,
            text="📹 Carregar Frame do Vídeo Selecionado",
            command=self._on_load_video_frame_clicked,
        ).pack(pady=(5, 0))

        self._update_video_tree_toggle_label()

    def _toggle_video_tree_nodes(self) -> None:
        """Alterna entre expandir ou recolher todos os grupos do seletor de vídeos."""
        if not self.video_selector_tree:
            return

        self._video_tree_expanded = not self._video_tree_expanded
        self._set_video_tree_open_state(self._video_tree_expanded)
        self._update_video_tree_toggle_label()

    def apply_video_tree_expand_state(self) -> None:
        """Reaplica o estado atual de expansão após repovoar a árvore."""
        self._set_video_tree_open_state(self._video_tree_expanded)
        self._update_video_tree_toggle_label()

    def _set_video_tree_open_state(self, expanded: bool) -> None:
        """Define a abertura dos nós de nível superior."""
        if not self.video_selector_tree:
            return

        for group_id in self.video_selector_tree.get_children(""):
            self.video_selector_tree.item(group_id, open=expanded)
            for day_id in self.video_selector_tree.get_children(group_id):
                self.video_selector_tree.item(day_id, open=expanded)

    def _update_video_tree_toggle_label(self) -> None:
        """Atualiza o texto do botão de expandir/recolher conforme o estado."""
        if not self.video_tree_toggle_btn:
            return

        if self._video_tree_expanded:
            self.video_tree_toggle_btn.config(text="Recolher tudo")
        else:
            self.video_tree_toggle_btn.config(text="Expandir tudo")

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

        # Configure column widths - Name takes ~60%, Type ~20%, Color ~20%
        self.zone_listbox.column("name", width=200, minwidth=100, stretch=True)
        self.zone_listbox.column("type", width=70, minwidth=50, stretch=True)
        self.zone_listbox.column("color", width=70, minwidth=35, stretch=True)

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
            width=18,
        )
        self.roi_rule_combo.pack(side="left", fill="x", expand=True)
        self.roi_rule_combo.bind("<<ComboboxSelected>>", self._on_roi_rule_changed)

        # Buffer radius parameter (Initially hidden)
        self.radius_frame = ttk.Frame(self.roi_inclusion_frame)
        # self.radius_frame.pack(fill="x", pady=2) # Logic handles visibility
        ttk.Label(self.radius_frame, text="Raio de buffer (r):").pack(side="left", padx=(0, 5))
        ttk.Entry(self.radius_frame, textvariable=self.roi_buffer_radius_var, width=10).pack(
            side="left", padx=(0, 10)
        )
        # Help text below input for compact width
        ttk.Label(
            self.radius_frame,
            text="Dilatação da ROI (cm se calibrado, senão px).",
            font=("TkDefaultFont", 8),
            foreground="gray",
        ).pack(side="left")

        # Overlap ratio parameter (Initially hidden)
        self.overlap_frame = ttk.Frame(self.roi_inclusion_frame)
        # self.overlap_frame.pack(fill="x", pady=2) # Logic handles visibility
        ttk.Label(self.overlap_frame, text="Sobreposição mín (0–1):").pack(side="left", padx=(0, 5))
        ttk.Entry(self.overlap_frame, textvariable=self.roi_overlap_ratio_var, width=10).pack(
            side="left", padx=(0, 10)
        )

        # Help text
        self.rule_help_label = ttk.Label(
            self.roi_inclusion_frame,
            text="",
            font=("TkDefaultFont", 8),
            wraplength=200,  # Adjusted for narrower panel
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

        # Force update visibility based on default value
        self._on_roi_rule_changed(None)

    # Event handlers that emit events to the event bus

    def _on_conclude_video_clicked(self) -> None:
        """Handle conclude video button click."""
        self.emit_event("zone.conclude_video", {})

    def _on_auto_detect_clicked(self) -> None:
        """Handle auto-detect button click."""
        self.emit_event(
            "zone.auto_detect_clicked",
            {"stabilization_frames": self.stabilization_frames_var.get()},
        )

    def _on_aquarium_selected(self) -> None:
        """Handle aquarium selection change."""
        aquarium_id = self.active_aquarium_var.get()
        log.debug("zone_controls.aquarium_selected", aquarium_id=aquarium_id)
        self.emit_event(
            Events.ZONE_AQUARIUM_SELECTED,
            {"aquarium_id": aquarium_id},
        )

    def _on_processing_mode_changed(self) -> None:
        """Handle processing mode change (parallel vs sequential).

        Emits ZONE_PROCESSING_MODE_CHANGED event with the new mode.
        Sequential mode processes each aquarium separately (2 video passes).
        Parallel mode processes both aquariums simultaneously (1 video pass).

        If "apply_to_all" is checked, the mode is applied to all videos in the project.
        """
        sequential = self.sequential_processing_var.get()
        apply_to_all = self.apply_to_all_var.get()
        log.info(
            "zone_controls.processing_mode_changed",
            sequential=sequential,
            apply_to_all=apply_to_all,
            mode="sequential" if sequential else "parallel",
        )
        self.emit_event(
            Events.ZONE_PROCESSING_MODE_CHANGED,
            {"sequential": sequential, "apply_to_all": apply_to_all},
        )

    def _on_draw_main_polygon_clicked(self) -> None:
        """Handle draw main polygon button click."""
        self.emit_event("zone.draw_arena", {})

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
        if not self.video_selector_tree:
            return

        selection = self.video_selector_tree.selection()
        if selection:
            item_id = selection[0]
            self.emit_event("zone.video_double_click", {"item_id": item_id})

    def _on_video_tree_right_click(self, event) -> None:
        """Handle video tree right-click to show context menu."""
        if not self.video_selector_tree or not hasattr(self, "_video_context_menu"):
            return

        # Identify the item under cursor
        item_id = self.video_selector_tree.identify_row(event.y)
        if not item_id:
            return

        # Select the item
        self.video_selector_tree.selection_set(item_id)

        # Check if this is a video item (has a video_path stored)
        video_path = self._get_video_path_from_item(item_id)
        if not video_path:
            return

        # Store the video path for menu commands
        self._context_menu_video_path = video_path

        # Show context menu
        self._video_context_menu.post(event.x_root, event.y_root)

    def _create_video_tree_context_menu(self) -> None:
        """Create context menu for video tree with copy/paste/delete options."""
        self._video_context_menu = Menu(
            self.video_selector_tree, tearoff=0, font=("TkDefaultFont", 9)
        )
        self._video_context_menu.add_command(
            label="📋 Copiar Zonas", command=self._on_copy_zones_clicked
        )
        self._video_context_menu.add_command(
            label="📥 Colar Zonas", command=self._on_paste_zones_clicked
        )
        self._video_context_menu.add_separator()
        self._video_context_menu.add_command(
            label="🗑️ Excluir Zonas", command=self._on_delete_zones_clicked
        )
        self._video_context_menu.add_separator()
        self._video_context_menu.add_command(
            label="🔄 Reconfigurar Sujeitos",
            command=self._on_reconfigure_subjects_clicked,
        )
        self._context_menu_video_path = None

    def _get_video_path_from_item(self, item_id: str) -> str | None:
        """Get video path from a tree item ID.

        The video path is stored in the item's tags, not values.
        Only leaf nodes (video items) have tags with the path.
        """
        if not self.video_selector_tree:
            return None

        # Get item data
        item = self.video_selector_tree.item(item_id)

        # Video path is stored in tags (first tag is the path)
        # Note: tags can be a tuple, list, or string depending on Tk version
        tags = item.get("tags", ())

        if not tags:
            return None

        # Handle case where tags is a string (single tag)
        if isinstance(tags, str):
            return tags if tags else None

        # Handle case where tags is a tuple/list
        if len(tags) > 0:
            tag = tags[0]
            # Return the tag if it looks like a path (contains path separator or file extension)
            if tag and (
                "/" in str(tag)
                or "\\" in str(tag)
                or any(str(tag).lower().endswith(ext) for ext in (".mp4", ".avi", ".mov", ".mkv"))
            ):
                return str(tag)

        return None

    def _on_copy_zones_clicked(self) -> None:
        """Handle copy zones from context menu."""
        if hasattr(self, "_context_menu_video_path") and self._context_menu_video_path:
            self.emit_event("zone.copy_zones", {"video_path": self._context_menu_video_path})

    def _on_paste_zones_clicked(self) -> None:
        """Handle paste zones from context menu."""
        if hasattr(self, "_context_menu_video_path") and self._context_menu_video_path:
            self.emit_event("zone.paste_zones", {"video_path": self._context_menu_video_path})

    def _on_delete_zones_clicked(self) -> None:
        """Handle delete zones from context menu."""
        if hasattr(self, "_context_menu_video_path") and self._context_menu_video_path:
            self.emit_event("zone.delete_zones", {"video_path": self._context_menu_video_path})

    def _on_reconfigure_subjects_clicked(self) -> None:
        """Handle reconfigure subjects from context menu.

        This opens a dialog to allow users to manually edit subject assignments
        for multi-subject videos. Emits 'video.reconfigure_subjects' event.
        """
        if not hasattr(self, "_context_menu_video_path") or not self._context_menu_video_path:
            return

        video_path = self._context_menu_video_path

        # Get current video metadata from project manager
        pm = getattr(self.gui.controller, "project_manager", None)
        if not pm:
            self.gui.show_warning("Aviso", "Gerenciador de projetos não disponível.")
            return

        video_entry = pm.find_video_entry(video_path)
        if not video_entry:
            self.gui.show_warning("Aviso", f"Vídeo não encontrado no projeto: {video_path}")
            return

        metadata = video_entry.get("metadata", {})
        subject_entries = metadata.get("subject_entries", [])

        if not subject_entries:
            # Single subject - show simple edit dialog
            from tkinter import simpledialog

            current_subject = metadata.get("subject", "")
            new_subject = simpledialog.askstring(
                "Reconfigurar Sujeito",
                f"ID do sujeito para {video_path.split('/')[-1].split('\\\\')[-1]}:",
                initialvalue=current_subject or "",
                parent=self.gui.root,
            )

            if new_subject is not None:
                # Update metadata
                video_entry["metadata"]["subject"] = new_subject
                video_entry["subject"] = new_subject
                pm.save_project()
                self.gui.show_info("Sucesso", f"Sujeito atualizado para: {new_subject}")
                self.emit_event("video.metadata_updated", {"video_path": video_path})
        else:
            # Multi-subject - emit event for external dialog
            self.emit_event(
                "video.reconfigure_subjects",
                {
                    "video_path": video_path,
                    "current_entries": subject_entries,
                },
            )

    def _on_load_video_frame_clicked(self) -> None:
        """Handle load video frame button click."""
        if not self.video_selector_tree:
            return

        selection = self.video_selector_tree.selection()
        if selection:
            item_id = selection[0]
            self.emit_event("zone.video_frame_load", {"item_id": item_id})

    def _on_zone_right_click(self, event) -> None:
        """Handle zone list right-click."""
        if not self.zone_listbox:
            return

        selection = self.zone_listbox.selection()
        if selection:
            item_id = selection[0]
            self.emit_event(
                "zone.list_item_right_click",
                {"item_id": item_id, "x": event.x_root, "y": event.y_root},
            )

    def _on_zone_double_click(self, event) -> None:
        """Handle zone list double-click."""
        if not self.zone_listbox:
            return

        selection = self.zone_listbox.selection()
        if selection:
            item_id = selection[0]
            self.emit_event("zone.list_item_double_click", {"item_id": item_id})

    def _on_save_arena_clicked(self) -> None:
        """Handle save arena button click."""
        self.emit_event("zone.save_arena", {})

    def _on_discard_arena_clicked(self) -> None:
        """Handle discard arena button click."""
        self.emit_event("zone.discard_arena", {})

    def _on_finish_drawing_clicked(self) -> None:
        """Handle finish drawing button click - completes polygon without double-click."""
        self.emit_event("zone.finish_drawing", {})

    def _on_roi_rule_changed(self, event) -> None:
        """Handle ROI rule change."""
        rule = self.roi_inclusion_rule_var.get()

        # Update visibility based on rule
        if rule == "centroid_in_on_buffered_roi":
            if self.radius_frame:
                self.radius_frame.pack(fill="x", pady=2, after=self.roi_rule_combo.master)
            if self.overlap_frame:
                self.overlap_frame.pack_forget()
            help_text = (
                "Considera dentro se o centroide estiver na ROI expandida pelo raio de buffer."
            )
        elif rule in ("bbox_intersects", "seg_overlap"):
            if self.radius_frame:
                self.radius_frame.pack_forget()
            if self.overlap_frame:
                self.overlap_frame.pack(fill="x", pady=2, after=self.roi_rule_combo.master)
            help_text = (
                "Considera dentro se a caixa/segmentação sobrepuser a ROI acima da fração mínima."
            )
        else:
            # centroid_in or others
            if self.radius_frame:
                self.radius_frame.pack_forget()
            if self.overlap_frame:
                self.overlap_frame.pack_forget()
            help_text = (
                "Considera dentro se o centroide geométrico estiver estritamente dentro da ROI."
            )

        if self.rule_help_label:
            self.rule_help_label.config(text=help_text)

        if not self.event_bus:
            return

        self.event_bus.publish_event(Events.DETECTOR_UPDATE_PARAMETERS, {"rule": rule})

    def _on_apply_roi_settings_clicked(self) -> None:
        """Handle apply ROI settings button click."""
        if not self.event_bus:
            return

        self.event_bus.publish_event(
            Events.DETECTOR_UPDATE_PARAMETERS,
            {
                "rule": self.roi_inclusion_rule_var.get(),
                "buffer_radius": float(self.roi_buffer_radius_var.get() or 0.5),
                "overlap_ratio": float(self.roi_overlap_ratio_var.get() or 0.10),
            },
        )

    # Public API for controlling widget state

    def set_draw_roi_enabled(self, enabled: bool) -> None:
        """Enable or disable the draw ROI button."""
        state = "normal" if enabled else "disabled"
        if self.draw_roi_button:
            self.draw_roi_button.config(state=state)
        if hasattr(self, "conclude_video_btn") and self.conclude_video_btn:
            self.conclude_video_btn.config(state=state)

    def show_single_analysis_options(self) -> None:
        """Show the single analysis options frame."""
        if hasattr(self, "single_analysis_options_frame"):
            try:
                if self.zone_controls_frame.winfo_exists():
                    children = self.zone_controls_frame.winfo_children()
                    if len(children) > 1:
                        self.single_analysis_options_frame.pack(
                            fill="x", pady=5, before=children[1]
                        )
                    else:
                        self.single_analysis_options_frame.pack(fill="x", pady=5)
            except (tk.TclError, IndexError):
                # Frame destroyed or invalid state
                pass

    def hide_single_analysis_options(self) -> None:
        """Hide the single analysis options frame."""
        if hasattr(self, "single_analysis_options_frame"):
            self.single_analysis_options_frame.pack_forget()

    def show_interactive_buttons(self) -> None:
        """Show the interactive editing buttons."""
        if self.interactive_buttons_frame:
            try:
                if self.interactive_buttons_frame.master == self.roi_inclusion_frame.master:
                    # Pack before ROI inclusion frame if in same container (side panel)
                    self.interactive_buttons_frame.pack(
                        fill="x", pady=5, before=self.roi_inclusion_frame
                    )
                else:
                    # Pack normally if in different container (top toolbar)
                    self.interactive_buttons_frame.pack(fill="x", pady=5)
            except Exception:
                # Fallback to simple pack
                self.interactive_buttons_frame.pack(fill="x", pady=5)

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
        if not self.zone_listbox:
            return

        try:
            if hasattr(self.zone_listbox, "winfo_exists") and self.zone_listbox.winfo_exists():
                for item in self.zone_listbox.get_children():
                    self.zone_listbox.delete(item)
        except Exception:
            # Widget might have been destroyed during teardown
            pass

    def add_zone_to_list(
        self, zone_id: str, name: str, zone_type: str, color: str, color_hex: str | None = None
    ) -> None:
        """Add a zone to the zone list with optional colored text.

        Args:
            zone_id: Unique identifier for the zone
            name: Display name for the zone
            zone_type: Type of zone (e.g., "Polígono", "ROI")
            color: Color name to display
            color_hex: Optional hex color code for text styling (e.g., "#FF0000")
        """
        if self.zone_listbox:
            self.zone_listbox.insert("", "end", iid=zone_id, values=(name, zone_type, color))
            # Apply colored text styling if hex color is provided
            if color_hex:
                tag_name = f"color_{zone_id}"
                self.zone_listbox.tag_configure(tag_name, foreground=color_hex)
                self.zone_listbox.item(zone_id, tags=(tag_name,))

    # Multi-aquarium public API

    def set_aquarium_count(self, count: int) -> None:
        """Set the number of aquariums and show/hide the selector.

        Args:
            count: Number of aquariums (1 or 2).
        """
        count = max(1, min(2, count))  # Clamp to 1-2
        self.aquarium_count_var.set(count)

        if count == 2:
            self.show_aquarium_selector()
        else:
            self.hide_aquarium_selector()
            self.active_aquarium_var.set(0)  # Reset to aquarium 1

        log.debug("zone_controls.aquarium_count_set", count=count)

    def get_aquarium_count(self) -> int:
        """Get the current aquarium count.

        Returns:
            Number of aquariums (1 or 2).
        """
        return self.aquarium_count_var.get()

    def show_aquarium_selector(self) -> None:
        """Show the aquarium selector frame."""
        if self.aquarium_selector_frame:
            try:
                # Pack after drawing actions frame
                parent = self.aquarium_selector_frame.master
                # Find drawing actions frame to pack after it
                for child in parent.winfo_children():
                    if isinstance(child, ttk.LabelFrame) and "Desenho" in str(child.cget("text")):
                        self.aquarium_selector_frame.pack(fill="x", pady=5, padx=5, after=child)
                        return
                # Fallback - just pack
                self.aquarium_selector_frame.pack(fill="x", pady=5, padx=5)
            except Exception:
                self.aquarium_selector_frame.pack(fill="x", pady=5, padx=5)

    def hide_aquarium_selector(self) -> None:
        """Hide the aquarium selector frame."""
        if self.aquarium_selector_frame:
            self.aquarium_selector_frame.pack_forget()

    def get_active_aquarium_id(self) -> int:
        """Get the currently selected aquarium ID.

        Returns:
            Aquarium ID (0 for aquarium 1, 1 for aquarium 2).
        """
        return self.active_aquarium_var.get()

    def set_active_aquarium(self, aquarium_id: int) -> None:
        """Set the active aquarium programmatically.

        Args:
            aquarium_id: Aquarium ID (0 or 1).
        """
        aquarium_id = max(0, min(1, aquarium_id))  # Clamp to 0-1
        self.active_aquarium_var.set(aquarium_id)
        log.debug("zone_controls.active_aquarium_set", aquarium_id=aquarium_id)

    def update_aquarium_count(self, count: int) -> None:
        """Update UI based on the number of aquariums."""
        log.info("zone_controls.update_aquarium_count", count=count)
        self.aquarium_count_var.set(count)

        if count >= 2:
            self.aquarium_selector_frame.pack(
                fill="x",
                pady=5,
                padx=5,
                after=self.drawing_actions_parent.winfo_children()[0]
                if self.drawing_actions_parent
                else None,
            )
        else:
            self.aquarium_selector_frame.pack_forget()
