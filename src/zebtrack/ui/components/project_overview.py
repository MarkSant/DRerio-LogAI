"""Project overview widget component - project status and video tree display."""

from tkinter import StringVar, ttk

import structlog

from zebtrack.ui import payloads
from zebtrack.ui.components.base import BaseWidget
from zebtrack.ui.event_bus_v2 import EventBusV2, UIEvents

log = structlog.get_logger()


class ProjectOverviewWidget(BaseWidget):
    """
    Reusable project overview widget displaying project status and video tree.

    Provides:
    - Project status summary cards
    - Video tree with hierarchy (group > day > subject)
    - Video status indicators
    - Context menu for video actions

    Events emitted:
    - project.video_selected: User selected a video from tree
    - project.video_double_click: User double-clicked a video
    - project.video_right_click: User right-clicked a video
    - project.refresh_requested: User requested overview refresh
    """

    def __init__(self, parent, event_bus: EventBusV2 | None = None, **kwargs):
        """
        Initialize the project overview widget.

        Args:
            parent: Parent Tkinter widget
            event_bus: Optional event bus for emitting events
            **kwargs: Additional arguments passed to BaseWidget
        """
        # Status tracking
        self.project_status_vars: dict[str, StringVar] = {}

        # Widget references
        self.project_overview_tree: ttk.Treeview | None = None
        self.status_cards_frame: ttk.Frame | None = None

        # Reverse mapping: treeview iid → video_path
        self._iid_to_path: dict[str, str] = {}

        super().__init__(parent, event_bus=event_bus, **kwargs)

    def _build_ui(self) -> None:
        """Build the project overview widget UI."""
        # Title
        title_label = ttk.Label(
            self, text="Visão Geral do Projeto", font=("TkDefaultFont", 12, "bold")
        )
        title_label.pack(pady=(0, 10))

        # Status cards
        self._build_status_cards()

        # Video tree
        self._build_video_tree()

    def _build_status_cards(self) -> None:
        """Build the status summary cards."""
        self.status_cards_frame = ttk.Frame(self)
        self.status_cards_frame.pack(fill="x", pady=(0, 10))

        # Create status cards in a grid
        status_types = [
            ("total", "📊", "Total"),
            ("pending", "⏳", "Pendentes"),
            ("processing", "🔁", "Processando"),
            ("processed", "📦", "Com Dados"),
            ("complete", "✅", "Concluídos"),
            ("failed", "⚠️", "Com Falha"),
        ]

        for idx, (status_key, icon, label) in enumerate(status_types):
            card = ttk.Frame(self.status_cards_frame, relief="raised", borderwidth=1)
            card.grid(row=idx // 3, column=idx % 3, padx=2, pady=2, sticky="ew")

            # Compact horizontal layout: icon + number + label
            ttk.Label(card, text=icon, font=("TkDefaultFont", 10)).pack(side="left", padx=(5, 2))

            self.project_status_vars[status_key] = StringVar(value="0")
            ttk.Label(
                card,
                textvariable=self.project_status_vars[status_key],
                font=("TkDefaultFont", 10, "bold"),
            ).pack(side="left", padx=2)

            ttk.Label(card, text=label, font=("TkDefaultFont", 9)).pack(side="left", padx=(2, 5))

        # Configure grid weights
        for i in range(3):
            self.status_cards_frame.columnconfigure(i, weight=1)

    def _build_video_tree(self) -> None:
        """Build the video tree view."""
        tree_frame = ttk.LabelFrame(self, text="Vídeos do Projeto", padding=10)
        tree_frame.pack(fill="both", expand=True)

        # Tree controls
        controls_frame = ttk.Frame(tree_frame)
        controls_frame.pack(fill="x", pady=(0, 5))

        ttk.Button(controls_frame, text="🔄 Atualizar", command=self._on_refresh_clicked).pack(
            side="right"
        )

        # Treeview
        tree_container = ttk.Frame(tree_frame)
        tree_container.pack(fill="both", expand=True)

        from zebtrack.ui.window_utils import create_scrollbar

        self.project_overview_tree = ttk.Treeview(
            tree_container,
            columns=("status", "metadata"),
            show="tree headings",
            height=12,
            selectmode="browse",
        )
        self.project_overview_tree.heading("#0", text="Vídeos")
        self.project_overview_tree.heading("status", text="Status")
        self.project_overview_tree.heading("metadata", text="Metadados")

        self.project_overview_tree.column("#0", width=250, minwidth=150, stretch=True)
        self.project_overview_tree.column("status", width=80, minwidth=60, anchor="center")
        self.project_overview_tree.column("metadata", width=350, minwidth=200, stretch=True)

        scrollbar = create_scrollbar(
            tree_container, orient="vertical", command=self.project_overview_tree.yview
        )
        self.project_overview_tree.configure(yscrollcommand=scrollbar.set)
        self.project_overview_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Bind events
        self.project_overview_tree.bind("<<TreeviewSelect>>", self._on_video_selected)
        self.project_overview_tree.bind("<Double-Button-1>", self._on_video_double_click)
        self.project_overview_tree.bind("<Button-3>", self._on_video_right_click)

        # Legend
        self._build_legend(tree_frame)

    def _build_legend(self, parent) -> None:
        """Build the status legend."""
        legend_frame = ttk.Frame(parent)
        legend_frame.pack(fill="x", pady=(5, 0))

        # Define symbols locally to avoid circular imports
        symbols = {
            "arena": "\U0001f3df",
            "rois": "\U0001f3af",
            "trajectory": "\U0001f9ed",
            "summary": "\u03a3",
        }

        legend_text = (
            f"Legenda: {symbols['arena']} Arena | "
            f"{symbols['rois']} ROIs | "
            f"{symbols['trajectory']} Trajetória | "
            f"{symbols['summary']} Sumário"
        )

        ttk.Label(
            legend_frame, text=legend_text, font=("TkDefaultFont", 8), foreground="#555555"
        ).pack(anchor="w")

    # Event handlers

    def _on_refresh_clicked(self) -> None:
        """Handle refresh button click."""
        self.emit_event(
            UIEvents.PROJECT_REFRESH_REQUESTED, payloads.ProjectRefreshRequestedPayload()
        )

    def _on_video_selected(self, event) -> None:
        """Handle video selection in tree."""
        if self.project_overview_tree:
            selection = self.project_overview_tree.selection()
            if selection:
                item_id = selection[0]
                video_path = self._iid_to_path.get(item_id)
                if video_path:
                    self.emit_event(
                        UIEvents.PROJECT_VIDEO_SELECTED,
                        payloads.ProjectVideoSelectedPayload(video_path=video_path),
                    )
                else:
                    log.debug(
                        "project_overview.video_selected.no_path",
                        item_id=item_id,
                    )

    def _on_video_double_click(self, event) -> None:
        """Handle video double-click in tree."""
        if self.project_overview_tree:
            selection = self.project_overview_tree.selection()
            if selection:
                item_id = selection[0]
                self.emit_event(
                    UIEvents.PROJECT_VIDEO_DOUBLE_CLICK_WIDGET,
                    payloads.ItemIdPayload(item_id=item_id),
                )

    def _on_video_right_click(self, event) -> None:
        """Handle video right-click in tree."""
        # Get item at click position
        if self.project_overview_tree:
            item_id = self.project_overview_tree.identify_row(event.y)
            if item_id:
                self.project_overview_tree.selection_set(item_id)
                self.emit_event(
                    UIEvents.PROJECT_VIDEO_RIGHT_CLICK_WIDGET,
                    payloads.ProjectContextMenuClickPayload(
                        item_id=item_id, x=event.x_root, y=event.y_root
                    ),
                )

    # Public API for updating widget state

    def update_summary(self, status_counts: dict[str, int]) -> None:
        """
        Update summary cards (alias for update_status_counts).

        Args:
            status_counts: Dictionary mapping status keys to counts
        """
        self.update_status_counts(status_counts)

    def update_legend(self) -> None:
        """Update the legend display (placeholder)."""
        pass

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
        """Clear all items from the video tree."""
        if self.project_overview_tree:
            for item in self.project_overview_tree.get_children():
                self.project_overview_tree.delete(item)

    def add_tree_item(self, item_id: str, text: str, parent: str = "", values: tuple = ()) -> None:
        """
        Add an item to the video tree.

        Args:
            item_id: Unique identifier for the item
            text: Display text for the item
            parent: Parent item ID (empty string for root items)
            values: Tuple of values for the columns
        """
        if self.project_overview_tree:
            self.project_overview_tree.insert(parent, "end", iid=item_id, text=text, values=values)

    def expand_tree_item(self, item_id: str) -> None:
        """Expand a tree item to show its children."""
        if self.project_overview_tree:
            self.project_overview_tree.item(item_id, open=True)

    def collapse_tree_item(self, item_id: str) -> None:
        """Collapse a tree item to hide its children."""
        if self.project_overview_tree:
            self.project_overview_tree.item(item_id, open=False)

    def update_tree(self, snapshot: list[dict]) -> None:
        """Update tree with new snapshot data."""
        hierarchy_data = {"groups": snapshot}
        # Build simplified video index for context menus
        video_index = {}
        for group in snapshot:
            for day in group.get("days", []):
                for subject in day.get("subjects", []):
                    for video in subject.get("videos", []):
                        if "path" in video:
                            video_index[video["path"]] = video

        self.populate_tree_with_hierarchy(hierarchy_data, video_index)

    def populate_tree_with_hierarchy(self, hierarchy_data: dict, video_index: dict) -> None:
        """
        Populate the tree with pre-formatted hierarchy data.

        Args:
            hierarchy_data: Dictionary with structure:
                {
                    'groups': [
                        {
                            'id': str,
                            'display': str,
                            'status_summary': str,
                            'data_summary': str,
                            'days': [
                                {
                                    'id': str,
                                    'title': str,
                                    'status': str,
                                    'data': str,
                                    'subjects': [
                                        {
                                            'id': str,
                                            'label': str,
                                            'status': str,
                                            'data': str,
                                            'videos': [
                                                {
                                                    'id': str,
                                                    'display_name': str,
                                                    'status': str,
                                                    'data_badges': str,
                                                    'path': str (optional)
                                                }
                                            ]
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            video_index: Dictionary mapping video paths to video metadata
        """
        # Clear existing tree
        self.clear_tree()

        # Reset reverse mapping
        self._iid_to_path = {}

        # Store video index reference (for context menus, etc.)
        self._video_index = video_index

        # Build tree from hierarchy data
        for group in hierarchy_data.get("groups", []):
            group_id = f"group_{group['id']}"

            # Add group node
            self.add_tree_item(
                item_id=group_id,
                text=group.get("label", f"🏷️ {group.get('display', 'Grupo')}"),
                values=(group.get("status_summary", ""), group.get("data_summary", "")),
            )
            self.expand_tree_item(group_id)

            # Add days
            for day in group.get("days", []):
                day_id = f"day_{group['id']}_{day['id']}"

                self.add_tree_item(
                    item_id=day_id,
                    parent=group_id,
                    text=f"📅 {day['title']}",
                    values=(day["status"], day["data"]),
                )

                # Add subjects
                for subject in day.get("subjects", []):
                    subject_id = f"subject_{group['id']}_{day['id']}_{subject['id']}"

                    self.add_tree_item(
                        item_id=subject_id,
                        parent=day_id,
                        text=subject.get("label", f"🐟 Sujeito {subject['id']}"),
                        values=(subject.get("status", ""), subject.get("data", "")),
                    )

                    # Add videos
                    for video in subject.get("videos", []):
                        video_id = video["id"]
                        video_path = video.get("path", "")
                        if video_path:
                            self._iid_to_path[video_id] = video_path

                        self.add_tree_item(
                            item_id=video_id,
                            parent=subject_id,
                            text=video["display_name"],
                            values=(video["status"], video["data_badges"]),
                        )
