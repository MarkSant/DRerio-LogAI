"""
Processing and Reports widget component - unified project processing and reporting interface.

This widget consolidates functionality from the old "Trajectories and Summaries" and
"Reports" tabs into a single, cohesive interface.
"""

from collections.abc import Callable
from tkinter import StringVar, ttk

import structlog

from zebtrack.ui.components.base import BaseWidget
from zebtrack.ui.event_bus import EventBus

log = structlog.get_logger()


class ProcessingReportsWidget(BaseWidget):
    """
    Unified processing and reports widget.

    Provides:
    - Project status summary cards (Total, Pending, Processing, etc.)
    - Hierarchical video tree with processing status columns
    - Action toolbar for trajectory generation, summary export, and report generation
    - Selection-aware button state management

    Events emitted:
    - processing.generate_trajectories: User clicked "Generate Trajectories" button
    - processing.export_summaries: User clicked "Export Summaries" button
    - reports.generate_partial: User clicked "Generate Report for Selected" button
    - reports.generate_unified: User clicked "Generate Unified Report" button
    - project.selection_changed: User changed selection in tree
    - project.item_double_click: User double-clicked an item
    - project.refresh_requested: User requested refresh
    """

    def __init__(
        self,
        parent,
        event_bus: EventBus | None = None,
        on_generate_trajectories: Callable | None = None,
        on_export_summaries: Callable | None = None,
        on_generate_partial_report: Callable | None = None,
        on_generate_unified_report: Callable | None = None,
        **kwargs,
    ):
        """
        Initialize the processing and reports widget.

        Args:
            parent: Parent Tkinter widget
            event_bus: Optional event bus for emitting events
            on_generate_trajectories: Callback for "Generate Trajectories" button
            on_export_summaries: Callback for "Export Summaries" button
            on_generate_partial_report: Callback for "Generate Partial Report" button
            on_generate_unified_report: Callback for "Generate Unified Report" button
            **kwargs: Additional arguments passed to BaseWidget
        """
        # Callback storage
        self._on_generate_trajectories = on_generate_trajectories
        self._on_export_summaries = on_export_summaries
        self._on_generate_partial_report = on_generate_partial_report
        self._on_generate_unified_report = on_generate_unified_report

        # Status tracking
        self.project_status_vars: dict[str, StringVar] = {}

        # Widget references
        self.tree: ttk.Treeview | None = None
        self.status_cards_frame: ttk.Frame | None = None
        self.selection_label: ttk.Label | None = None

        # Action buttons
        self.btn_generate_trajectories: ttk.Button | None = None
        self.btn_export_summaries: ttk.Button | None = None
        self.btn_generate_partial: ttk.Button | None = None
        self.btn_generate_unified: ttk.Button | None = None
        self.btn_expand_collapse: ttk.Button | None = None

        # Tree state
        self._tree_expanded = False

        super().__init__(parent, event_bus=event_bus, **kwargs)

    def _build_ui(self) -> None:
        """Build the processing and reports widget UI."""
        # Status cards at top
        self._build_status_cards()

        # Main tree view
        self._build_tree_view()

        # Selection info label
        self._build_selection_info()

        # Action toolbar at bottom
        self._build_action_toolbar()

    def _build_status_cards(self) -> None:
        """Build the status summary cards in a single horizontal row."""
        self.status_cards_frame = ttk.Frame(self)
        self.status_cards_frame.pack(fill="x", pady=(0, 10))

        # Create status cards in a single horizontal row (6 cards total)
        status_types = [
            ("total", "🧮", "Total"),
            ("pending", "⏳", "Pendentes"),
            ("processing", "🔁", "Processando"),
            ("processed", "📦", "Com Dados"),
            ("complete", "✅", "Concluídos"),
            ("failed", "⚠️", "Com Falha"),
        ]

        for idx, (status_key, icon, label) in enumerate(status_types):
            card = ttk.Frame(self.status_cards_frame, relief="raised", borderwidth=1, padding=5)
            card.grid(row=0, column=idx, padx=3, pady=5, sticky="ew")

            # Compact horizontal layout
            ttk.Label(card, text=icon, font=("TkDefaultFont", 12)).pack(side="left", padx=(0, 3))

            self.project_status_vars[status_key] = StringVar(value="0")
            ttk.Label(
                card,
                textvariable=self.project_status_vars[status_key],
                font=("TkDefaultFont", 11, "bold"),
            ).pack(side="left", padx=(0, 3))

            ttk.Label(card, text=label, font=("TkDefaultFont", 9)).pack(side="left")

        # Configure grid weights for even distribution across 6 columns
        for i in range(6):
            self.status_cards_frame.columnconfigure(i, weight=1)

    def _build_tree_view(self) -> None:
        """Build the hierarchical project tree view."""
        tree_frame = ttk.LabelFrame(self, text="Estrutura do Projeto", padding=10)
        tree_frame.pack(fill="both", expand=True)

        # Tree controls header
        controls_frame = ttk.Frame(tree_frame)
        controls_frame.pack(fill="x", pady=(0, 5))

        ttk.Label(
            controls_frame,
            text="Selecione vídeos para processar ou gerar relatórios:",
            font=("TkDefaultFont", 9),
        ).pack(side="left")

        ttk.Button(controls_frame, text="🔄 Atualizar", command=self._on_refresh_clicked).pack(
            side="right", padx=(5, 0)
        )

        self.btn_expand_collapse = ttk.Button(
            controls_frame, text="⊞ Expandir Tudo", command=self._on_expand_collapse_clicked
        )
        self.btn_expand_collapse.pack(side="right")

        # Treeview with columns
        tree_container = ttk.Frame(tree_frame)
        tree_container.pack(fill="both", expand=True)

        from zebtrack.ui.window_utils import create_scrollbar

        columns = ("arena", "rois", "trajectory", "summary", "status")
        self.tree = ttk.Treeview(
            tree_container,
            columns=columns,
            show="tree headings",
            height=14,
            selectmode="extended",  # Allow multiple selection
        )

        # Configure headings
        self.tree.heading("#0", text="Nome")
        self.tree.heading("arena", text="🏛️ Arena")
        self.tree.heading("rois", text="📍 ROIs")
        self.tree.heading("trajectory", text="📈 Trajetória")
        self.tree.heading("summary", text="Σ Sumário")
        self.tree.heading("status", text="Status")

        # Configure columns
        self.tree.column("#0", width=280, stretch=True)
        self.tree.column("arena", width=80, anchor="center")
        self.tree.column("rois", width=80, anchor="center")
        self.tree.column("trajectory", width=100, anchor="center")
        self.tree.column("summary", width=90, anchor="center")
        self.tree.column("status", width=140, anchor="center")

        # Scrollbar
        scrollbar = create_scrollbar(tree_container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Configure color tags for status indicators
        self.tree.tag_configure("status_complete", foreground="#166534")  # Dark green
        self.tree.tag_configure("status_partial", foreground="#b45309")  # Orange/yellow
        self.tree.tag_configure("status_missing", foreground="#b91c1c")  # Red
        self.tree.tag_configure("report-file", foreground="#0369a1")  # Blue for files

        # Bind events
        self.tree.bind("<<TreeviewSelect>>", self._on_selection_changed)
        self.tree.bind("<Double-Button-1>", self._on_item_double_click)

    def _build_selection_info(self) -> None:
        """Build the selection information label."""
        info_frame = ttk.Frame(self)
        info_frame.pack(fill="x", pady=(5, 0))

        self.selection_label = ttk.Label(
            info_frame,
            text="Nenhum vídeo selecionado",
            font=("TkDefaultFont", 8),
            foreground="#555555",
        )
        self.selection_label.pack(side="left")

    def _build_action_toolbar(self) -> None:
        """Build the action toolbar with processing and reporting buttons."""
        toolbar_frame = ttk.LabelFrame(self, text="Ações de Processamento e Relatórios", padding=10)
        toolbar_frame.pack(fill="x", pady=(10, 0))

        # Create buttons in a horizontal layout
        self.btn_generate_trajectories = ttk.Button(
            toolbar_frame,
            text="▶️ Gerar Trajetórias",
            command=self._on_generate_trajectories_clicked,
            state="disabled",
        )
        self.btn_generate_trajectories.pack(side="left", padx=5)

        self.btn_export_summaries = ttk.Button(
            toolbar_frame,
            text="Σ Exportar Sumários (Parquet)",
            command=self._on_export_summaries_clicked,
            state="disabled",
        )
        self.btn_export_summaries.pack(side="left", padx=5)

        # Separator
        ttk.Separator(toolbar_frame, orient="vertical").pack(side="left", fill="y", padx=10)

        self.btn_generate_partial = ttk.Button(
            toolbar_frame,
            text="📄 Relatório para Selecionados",
            command=self._on_generate_partial_clicked,
            state="disabled",
        )
        self.btn_generate_partial.pack(side="left", padx=5)

        self.btn_generate_unified = ttk.Button(
            toolbar_frame,
            text="📚 Relatório Unificado (Todos)",
            command=self._on_generate_unified_clicked,
            state="normal",  # Always enabled
        )
        self.btn_generate_unified.pack(side="left", padx=5)

    # Event handlers

    def _on_refresh_clicked(self) -> None:
        """Handle refresh button click."""
        log.debug("processing_reports.refresh_clicked")
        self.emit_event("project.refresh_requested", {})

    def _on_expand_collapse_clicked(self) -> None:
        """Handle expand/collapse all button click."""
        if not self.tree:
            return

        if self._tree_expanded:
            # Collapse all
            self._collapse_all_items()
            self._tree_expanded = False
            if self.btn_expand_collapse:
                self.btn_expand_collapse.config(text="⊞ Expandir Tudo")
            log.debug("processing_reports.tree_collapsed")
        else:
            # Expand all
            self._expand_all_items()
            self._tree_expanded = True
            if self.btn_expand_collapse:
                self.btn_expand_collapse.config(text="⊟ Colapsar Tudo")
            log.debug("processing_reports.tree_expanded")

    def _expand_all_items(self) -> None:
        """Recursively expand all items in the tree."""
        if not self.tree:
            return

        def expand_recursive(item_id: str) -> None:
            self.tree.item(item_id, open=True)
            for child in self.tree.get_children(item_id):
                expand_recursive(child)

        # Expand all root items and their children
        for item in self.tree.get_children():
            expand_recursive(item)

    def _collapse_all_items(self) -> None:
        """Recursively collapse all items in the tree."""
        if not self.tree:
            return

        def collapse_recursive(item_id: str) -> None:
            self.tree.item(item_id, open=False)
            for child in self.tree.get_children(item_id):
                collapse_recursive(child)

        # Collapse all root items and their children
        for item in self.tree.get_children():
            collapse_recursive(item)

    def _on_selection_changed(self, event) -> None:
        """Handle tree selection change."""
        selection = self.tree.selection() if self.tree else []
        log.debug("processing_reports.selection_changed", count=len(selection))
        self.emit_event("project.selection_changed", {"selection": selection})
        self._update_button_states()

    def _on_item_double_click(self, event) -> None:
        """Handle item double-click in tree."""
        if not self.tree:
            return

        # Get item at click position or from selection
        item_id = None
        if event is not None:
            item_id = self.tree.identify_row(event.y)
        if not item_id:
            selection = self.tree.selection()
            if selection:
                item_id = selection[0]

        if item_id:
            log.debug("processing_reports.item_double_clicked", item_id=item_id)
            self.emit_event("project.item_double_click", {"item_id": item_id, "event": event})

    def _on_generate_trajectories_clicked(self) -> None:
        """Handle Generate Trajectories button click."""
        log.info("processing_reports.generate_trajectories_clicked")
        selection = self.tree.selection() if self.tree else []
        self.emit_event("processing.generate_trajectories", {"selection": selection})
        if self._on_generate_trajectories:
            self._on_generate_trajectories(selection)

    def _on_export_summaries_clicked(self) -> None:
        """Handle Export Summaries button click."""
        log.info("processing_reports.export_summaries_clicked")
        selection = self.tree.selection() if self.tree else []
        self.emit_event("processing.export_summaries", {"selection": selection})
        if self._on_export_summaries:
            self._on_export_summaries()

    def _on_generate_partial_clicked(self) -> None:
        """Handle Generate Partial Report button click."""
        log.info("processing_reports.generate_partial_report_clicked")
        selection = self.tree.selection() if self.tree else []
        self.emit_event("reports.generate_partial", {"selection": selection})
        if self._on_generate_partial_report:
            self._on_generate_partial_report()

    def _on_generate_unified_clicked(self) -> None:
        """Handle Generate Unified Report button click."""
        log.info("processing_reports.generate_unified_report_clicked")
        self.emit_event("reports.generate_unified", {})
        if self._on_generate_unified_report:
            self._on_generate_unified_report()

    def _update_button_states(self) -> None:
        """Update button enabled/disabled states based on selection."""
        if not self.tree:
            return

        selection = self.tree.selection()
        has_selection = len(selection) > 0

        # Enable trajectory/summary buttons only if videos are selected
        if self.btn_generate_trajectories:
            self.btn_generate_trajectories.config(state="normal" if has_selection else "disabled")

        if self.btn_export_summaries:
            self.btn_export_summaries.config(state="normal" if has_selection else "disabled")

        if self.btn_generate_partial:
            self.btn_generate_partial.config(state="normal" if has_selection else "disabled")

        # Unified report is always enabled (operates on all videos)
        # Already set to normal in _build_action_toolbar

        # Update selection label
        if self.selection_label:
            if has_selection:
                self.selection_label.config(
                    text=f"{len(selection)} vídeo(s) selecionado(s)",
                    foreground="#0f5132",
                )
            else:
                self.selection_label.config(
                    text="Nenhum vídeo selecionado",
                    foreground="#555555",
                )

    # Public API for updating widget state

    def update_status_counts(self, counts: dict[str, int]) -> None:
        """
        Update the status card counts.

        Args:
            counts: Dictionary mapping status keys to counts
        """
        for status_key, count in counts.items():
            if status_key in self.project_status_vars:
                self.project_status_vars[status_key].set(str(count))

    def clear_tree(self) -> None:
        """Clear all items from the tree."""
        if self.tree:
            for item in self.tree.get_children():
                self.tree.delete(item)

        # Reset expand/collapse state when tree is cleared
        self._tree_expanded = False
        if self.btn_expand_collapse:
            self.btn_expand_collapse.config(text="⊞ Expandir Tudo")

    def add_tree_item(
        self,
        item_id: str,
        text: str,
        parent: str = "",
        values: tuple = (),
        tags: tuple = (),
    ) -> None:
        """
        Add an item to the tree.

        Args:
            item_id: Unique identifier for the item
            text: Display text for the item
            parent: Parent item ID (empty string for root items)
            values: Tuple of values for the columns (arena, rois, trajectory, summary, status)
            tags: Tags for styling
        """
        tree = self.tree
        if not tree:
            return

        if tree.exists(item_id):
            tree.item(item_id, text=text, values=values, tags=tags)
            tree.move(item_id, parent, "end")
            return

        tree.insert(parent, "end", iid=item_id, text=text, values=values, tags=tags)

    def expand_tree_item(self, item_id: str) -> None:
        """Expand a tree item to show its children."""
        if self.tree:
            self.tree.item(item_id, open=True)

    def collapse_tree_item(self, item_id: str) -> None:
        """Collapse a tree item to hide its children."""
        if self.tree:
            self.tree.item(item_id, open=False)

    def get_selection(self) -> tuple[str, ...]:
        """
        Get currently selected item IDs.

        Returns:
            Tuple of selected item IDs
        """
        if self.tree:
            return self.tree.selection()
        return ()

    def update_selection_info(self, text: str, foreground: str = "#555555") -> None:
        """
        Update the selection information label.

        Args:
            text: Text to display
            foreground: Text color
        """
        if self.selection_label:
            self.selection_label.config(text=text, foreground=foreground)
