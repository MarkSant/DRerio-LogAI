"""
Step 4: Import Configuration Dialog.

Allows user to configure per-video import strategy with smart defaults.
Shows table of videos with checkboxes for arena/ROIs/trajectory import.
"""

from pathlib import Path
from tkinter import Label, LabelFrame, Radiobutton, StringVar, ttk
from tkinter import font as tkfont

import structlog

from zebtrack.ui.window_utils import create_scrollbar
from zebtrack.ui.wizard.base import WizardStep
from zebtrack.ui.wizard.enums import (
    ImportAction,
    ROIMergeStrategy,
    WizardStepID,
    derive_import_action,
)
from zebtrack.ui.wizard.templates import format_template_banner
from zebtrack.ui.wizard.tooltip import ToolTip

STATUS_SYMBOLS = {
    "arena": "\U0001f3df",  # 🏟
    "rois": "\U0001f3af",  # 🎯
    "trajectory": "\U0001f9ed",  # 🧭
}

log = structlog.get_logger()


class ImportConfigStep(WizardStep):
    """
    Import Configuration step - configure per-video import strategy.

    Processing:
        1. Load scanned videos from Step 3
        2. Apply smart defaults based on Step 1 choices
        3. Show table with checkboxes for each video
        4. Compute ImportAction for each video
        5. Allow ROI merge strategy selection

    Output:
        {
            "import_config": [
                {
                    "video": str,  # Video path
                    "import_arena": bool,
                    "import_rois": bool,
                    "import_trajectory": bool,
                    "action": str,  # ImportAction.value
                },
                ...
            ],
            "roi_merge_strategy": str,  # ROIMergeStrategy.value
        }
    """

    def __init__(self, parent, wizard_data: dict):
        """Initialize import config step."""
        super().__init__(parent, wizard_data)
        self.step_id: WizardStepID = WizardStepID.IMPORT_CONFIG

        # State
        # State
        self.video_configs: list[dict] = []  # List of per-video config dicts
        self.roi_merge_strategy_var = StringVar(value=ROIMergeStrategy.REPLACE.value)
        self.summary_var = StringVar(value="")
        self.template_info_var = StringVar(value="")
        self.template_info_label: Label | None = None
        self.video_tree: ttk.Treeview | None = None

    def build_ui(self):
        """Build import configuration UI with a wider horizontal layout."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        title_font = tkfont.Font(size=14, weight="bold")
        title = Label(self, text="Configuração de Importação", font=title_font)
        title.grid(row=0, column=0, sticky="w", pady=(0, 5))

        subtitle = Label(
            self,
            text="Configure o que importar para cada vídeo.",
            fg="gray",
            wraplength=920,
            justify="left",
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(0, 6))

        self.template_info_label = Label(
            self,
            textvariable=self.template_info_var,
            fg="#555555",
            wraplength=920,
            justify="left",
        )
        self.template_info_label.grid(row=2, column=0, sticky="w", pady=(0, 10))
        self.template_info_label.grid_remove()

        main_container = ttk.Frame(self)
        main_container.grid(row=3, column=0, sticky="nsew", pady=(0, 5))
        main_container.grid_columnconfigure(0, weight=3)
        main_container.grid_columnconfigure(1, weight=2)
        main_container.grid_rowconfigure(0, weight=1)

        left_column = ttk.Frame(main_container)
        left_column.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left_column.grid_columnconfigure(0, weight=1)
        left_column.grid_rowconfigure(1, weight=1)

        bulk_buttons_frame = ttk.Frame(left_column)
        bulk_buttons_frame.grid(row=0, column=0, sticky="w", pady=(0, 6))

        ttk.Button(
            bulk_buttons_frame,
            text="Importar Todas Arenas",
            command=self._bulk_import_arenas,
        ).pack(side="left", padx=2)
        ttk.Button(
            bulk_buttons_frame,
            text="Importar Todos ROIs",
            command=self._bulk_import_rois,
        ).pack(side="left", padx=2)
        ttk.Button(
            bulk_buttons_frame,
            text="Importar Todas Trajetórias",
            command=self._bulk_import_trajectories,
        ).pack(side="left", padx=2)
        ttk.Button(
            bulk_buttons_frame,
            text="Importar Tudo",
            command=self._bulk_import_all,
        ).pack(side="left", padx=2)

        table_frame = LabelFrame(left_column, text="Vídeos e Estratégias", padx=8, pady=5)
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        tree_scroll = create_scrollbar(table_frame)
        tree_scroll.grid(row=0, column=1, sticky="ns")

        self.video_tree = ttk.Treeview(
            table_frame,
            columns=("video", "arena", "rois", "trajectory", "action"),
            show="headings",
            yscrollcommand=tree_scroll.set,
            height=11,
        )
        self.video_tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll.config(command=self.video_tree.yview)

        self.video_tree.heading("video", text="Vídeo")
        self.video_tree.heading("arena", text="Arena")
        self.video_tree.heading("rois", text="ROIs")
        self.video_tree.heading("trajectory", text="Trajetória")
        self.video_tree.heading("action", text="Ação")

        self.video_tree.column("video", width=220, anchor="w")
        self.video_tree.column("arena", width=65, anchor="center")
        self.video_tree.column("rois", width=65, anchor="center")
        self.video_tree.column("trajectory", width=80, anchor="center")
        self.video_tree.column("action", width=100, anchor="center")

        self.video_tree.bind("<Double-1>", self._on_tree_double_click)

        right_panel = ttk.Frame(main_container)
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.grid_columnconfigure(0, weight=1)
        right_panel.grid_columnconfigure(1, weight=1)
        right_panel.grid_rowconfigure(1, weight=1)

        self.roi_frame = LabelFrame(
            right_panel,
            text="Estratégia ROIs",
            padx=8,
            pady=5,
        )
        self.roi_frame.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 8))

        rb_replace = Radiobutton(
            self.roi_frame,
            text="Replace (substituir)",
            variable=self.roi_merge_strategy_var,
            value=ROIMergeStrategy.REPLACE.value,
            font=("TkDefaultFont", 9),
        )
        rb_replace.grid(row=0, column=0, sticky="w", pady=1)
        ToolTip(rb_replace, "ROIs importados substituem completamente as existentes.")

        rb_merge = Radiobutton(
            self.roi_frame,
            text="Merge (manter ambos)",
            variable=self.roi_merge_strategy_var,
            value=ROIMergeStrategy.MERGE.value,
            font=("TkDefaultFont", 9),
        )
        rb_merge.grid(row=1, column=0, sticky="w", pady=1)
        ToolTip(rb_merge, "Manter ambos. Conflitos serão renomeados.")

        rb_manual = Radiobutton(
            self.roi_frame,
            text="Manual (perguntar)",
            variable=self.roi_merge_strategy_var,
            value=ROIMergeStrategy.MANUAL.value,
            font=("TkDefaultFont", 9),
        )
        rb_manual.grid(row=2, column=0, sticky="w", pady=1)
        ToolTip(rb_manual, "Perguntar para cada conflito.")

        self.summary_frame = LabelFrame(right_panel, text="Resumo", padx=8, pady=5)
        self.summary_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 8))

        summary_label = Label(
            self.summary_frame,
            textvariable=self.summary_var,
            justify="left",
            fg="blue",
            font=("TkDefaultFont", 9),
        )
        summary_label.grid(row=0, column=0, sticky="w")

        legend_frame = LabelFrame(right_panel, text="Legenda", padx=8, pady=5)
        legend_frame.grid(row=1, column=1, sticky="nsew")

        self.legend_label = Label(
            legend_frame,
            text=(
                "🏟 Arena | 🎯 ROIs | 🧭 Trajetória\n✓ Importar | ⏸ Não importar\n✗ Não disponível"
            ),
            fg="gray",
            font=("TkDefaultFont", 8),
            justify="left",
        )
        self.legend_label.grid(row=0, column=0, sticky="w")

        info_box = Label(
            right_panel,
            text=(
                "💡 Dica: ajuste rapidamente clicando 2x na coluna desejada. "
                "Use os botões de importação em lote para aplicar o mesmo padrão a todos os vídeos."
            ),
            fg="#555555",
            wraplength=340,
            justify="left",
        )
        info_box.grid(row=2, column=0, columnspan=2, sticky="we", pady=(8, 0))

        self._update_template_banner()

    def on_show(self):
        """Execute actions when step becomes visible - compute smart defaults."""
        self._compute_smart_defaults()
        self._populate_table()
        self._update_summary()
        self._update_roi_frame_visibility()
        self._update_template_banner()

    def _compute_smart_defaults(self):
        """Compute initial checkbox state based on Step 1 choices and parquet availability."""
        scanned_videos = self.wizard_data.get("scanned_videos", [])
        parquet_import_scope = self.wizard_data.get("parquet_import_scope")

        self.video_configs = []

        for video_info in scanned_videos:
            has_arena = video_info.get("has_arena", False)
            has_rois = video_info.get("has_rois", False)
            has_trajectory = video_info.get("has_trajectory", False)

            # Apply smart default rules
            if parquet_import_scope == "all":
                # User wants everything
                import_arena = has_arena
                import_rois = has_rois
                import_trajectory = has_trajectory
            elif parquet_import_scope == "zones":
                # User wants zones only
                import_arena = has_arena
                import_rois = has_rois
                import_trajectory = False  # Never import trajectory
            elif parquet_import_scope == "arena":
                # User wants arena only
                import_arena = has_arena
                import_rois = False  # Never import ROIs
                import_trajectory = False  # Never import trajectory
            else:  # None or not specified
                # User wants to start fresh
                import_arena = False
                import_rois = False
                import_trajectory = False

            # Derive action
            action = derive_import_action(import_arena, import_rois, import_trajectory)

            config = {
                "video": video_info["path"],
                "has_arena": has_arena,
                "has_rois": has_rois,
                "has_trajectory": has_trajectory,
                "import_arena": import_arena,
                "import_rois": import_rois,
                "import_trajectory": import_trajectory,
                "action": action.value,
            }

            self.video_configs.append(config)

        log.info(
            "wizard.import_config.defaults_computed",
            video_count=len(self.video_configs),
        )

    def _populate_table(self):
        """Populate Treeview with video configurations."""
        if not self.video_tree:
            return

        # Clear existing items
        for item in self.video_tree.get_children():
            self.video_tree.delete(item)

        # Add videos
        for idx, config in enumerate(self.video_configs):
            video_name = Path(config["video"]).name

            # Format glyphs with availability indicators
            def format_status(has_parquet: bool, importing: bool, symbol_key: str) -> str:
                symbol = STATUS_SYMBOLS[symbol_key]
                if not has_parquet:
                    return f"{symbol} ✗"

                suffix = "✓" if importing else "⏸"
                return f"{symbol} {suffix}"

            arena_str = format_status(config["has_arena"], config["import_arena"], "arena")
            rois_str = format_status(config["has_rois"], config["import_rois"], "rois")
            traj_str = format_status(
                config["has_trajectory"], config["import_trajectory"], "trajectory"
            )

            # Action name (user-friendly)
            action_map = {
                ImportAction.SKIP.value: "Skip",
                ImportAction.IMPORT_ZONES.value: "Import Zones",
                ImportAction.PARTIAL.value: "Partial",
                ImportAction.FULL.value: "Full",
            }
            action_str = action_map.get(config["action"], config["action"])

            # Insert row
            item_id = self.video_tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(video_name, arena_str, rois_str, traj_str, action_str),
            )

            # Color code by action
            if config["action"] == ImportAction.SKIP.value:
                self.video_tree.item(item_id, tags=("skip",))
            elif config["action"] == ImportAction.FULL.value:
                self.video_tree.item(item_id, tags=("full",))

        # Apply tag colors
        self.video_tree.tag_configure("skip", background="#e8f5e9")  # Light green
        self.video_tree.tag_configure("full", background="#fff3e0")  # Light orange

    def _on_tree_double_click(self, event):
        """Handle double-click on tree item to toggle import options."""
        if not self.video_tree:
            return

        region = self.video_tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        # Get clicked item and column
        item = self.video_tree.identify_row(event.y)
        column = self.video_tree.identify_column(event.x)

        if not item:
            return

        idx = int(item)
        config = self.video_configs[idx]

        # Toggle based on column
        if column == "#2":  # Arena column
            if config["has_arena"]:
                config["import_arena"] = not config["import_arena"]
        elif column == "#3":  # ROIs column
            if config["has_rois"]:
                config["import_rois"] = not config["import_rois"]
        elif column == "#4":  # Trajectory column
            if config["has_trajectory"]:
                config["import_trajectory"] = not config["import_trajectory"]

        # Re-derive action
        action = derive_import_action(
            config["import_arena"], config["import_rois"], config["import_trajectory"]
        )
        config["action"] = action.value

        # Refresh table and summary
        self._populate_table()
        self._update_summary()

        log.info(
            "wizard.import_config.toggled",
            video=Path(config["video"]).name,
            action=config["action"],
        )

    def _update_summary(self):
        """Update summary text with action counts."""
        action_counts: dict[str, int] = {}

        for config in self.video_configs:
            action = config["action"]
            action_counts[action] = action_counts.get(action, 0) + 1

        # Format summary
        action_names = {
            ImportAction.SKIP.value: "Skip (dados completos)",
            ImportAction.IMPORT_ZONES.value: "Import Zones + rastrear",
            ImportAction.PARTIAL.value: "Partial (arena apenas)",
            ImportAction.FULL.value: "Full (do zero)",
        }

        lines = []
        for action, count in sorted(action_counts.items()):
            name = action_names.get(action, action)
            lines.append(f"• {count} vídeo(s): {name}")

        self.summary_var.set("\n".join(lines) if lines else "Nenhum vídeo configurado")

    def _update_template_banner(self):
        banner_text = format_template_banner(self.wizard_data.get("template_metadata"))

        if banner_text:
            self.template_info_var.set(banner_text)
            if self.template_info_label and not self.template_info_label.winfo_ismapped():
                self.template_info_label.grid()
        else:
            self.template_info_var.set("")
            if self.template_info_label and self.template_info_label.winfo_ismapped():
                self.template_info_label.grid_remove()

    def _update_roi_frame_visibility(self):
        """Hide ROI merge strategy frame if no ROIs are being imported."""
        # Check if any video is configured to import ROIs
        importing_rois = any(config.get("import_rois", False) for config in self.video_configs)

        if importing_rois:
            # Show ROI frame if importing ROIs
            if not self.roi_frame.winfo_ismapped():
                self.roi_frame.grid()
        else:
            # Hide ROI frame if not importing any ROIs
            self.roi_frame.grid_remove()
            log.debug("import_config.roi_frame_hidden", reason="No ROIs being imported")

    def _bulk_import_arenas(self):
        """Enable import_arena for all videos that have arena data."""
        count = 0
        for config in self.video_configs:
            if config.get("has_arena", False):
                config["import_arena"] = True
                count += 1

        self._recalculate_all_actions()
        log.info("wizard.import_config.bulk_import_arenas", count=count)

    def _bulk_import_rois(self):
        """Enable import_rois for all videos that have ROI data."""
        count = 0
        for config in self.video_configs:
            if config.get("has_rois", False):
                config["import_rois"] = True
                count += 1

        self._recalculate_all_actions()
        log.info("wizard.import_config.bulk_import_rois", count=count)

    def _bulk_import_trajectories(self):
        """Enable import_trajectory for all videos that have trajectory data."""
        count = 0
        for config in self.video_configs:
            if config.get("has_trajectory", False):
                config["import_trajectory"] = True
                count += 1

        self._recalculate_all_actions()
        log.info("wizard.import_config.bulk_import_trajectories", count=count)

    def _bulk_import_all(self):
        """Enable all imports for videos that have the respective data."""
        count_arena = 0
        count_rois = 0
        count_traj = 0

        for config in self.video_configs:
            if config.get("has_arena", False):
                config["import_arena"] = True
                count_arena += 1
            if config.get("has_rois", False):
                config["import_rois"] = True
                count_rois += 1
            if config.get("has_trajectory", False):
                config["import_trajectory"] = True
                count_traj += 1

        self._recalculate_all_actions()
        log.info(
            "wizard.import_config.bulk_import_all",
            arenas=count_arena,
            rois=count_rois,
            trajectories=count_traj,
        )

    def _recalculate_all_actions(self):
        """Recalculate actions for all videos and refresh UI."""
        for config in self.video_configs:
            action = derive_import_action(
                config.get("import_arena", False),
                config.get("import_rois", False),
                config.get("import_trajectory", False),
            )
            config["action"] = action.value

        self._populate_table()
        self._update_summary()
        self._update_roi_frame_visibility()

    def validate(self) -> tuple[bool, str]:
        """
        Validate import configuration.

        Returns:
            tuple[bool, str]: (True, "") if all videos have valid actions
        """
        if not self.video_configs:
            return (False, "Nenhum vídeo para configurar. Volte e selecione vídeos.")

        # Check that all videos have valid actions
        for config in self.video_configs:
            if "action" not in config or not config["action"]:
                video_name = Path(config["video"]).name
                return (False, f"Vídeo {video_name} não possui ação definida.")

        return (True, "")

    def get_data(self) -> dict:
        """
        Extract import config data.

        Returns:
            dict: Import configuration with keys:
                - import_config (list): Per-video configurations
                - roi_merge_strategy (str): ROI merge strategy
        """
        # Clean configs (remove internal fields)
        clean_configs = []
        for config in self.video_configs:
            clean_configs.append(
                {
                    "video": config["video"],
                    "import_arena": config["import_arena"],
                    "import_rois": config["import_rois"],
                    "import_trajectory": config["import_trajectory"],
                    "action": config["action"],
                }
            )

        return {
            "import_config": clean_configs,
            "roi_merge_strategy": self.roi_merge_strategy_var.get(),
        }

    def set_data(self, data: dict):
        """
        Restore UI from data (for back navigation).

        Args:
            data: Previously collected import config data
        """
        if "import_config" in data:
            # Restore configs (merge with has_* flags from scanned videos)
            scanned_videos = self.wizard_data.get("scanned_videos", [])
            video_lookup = {v["path"]: v for v in scanned_videos}

            self.video_configs = []
            for config in data["import_config"]:
                video_info = video_lookup.get(config["video"], {})
                full_config = {
                    **config,
                    "has_arena": video_info.get("has_arena", False),
                    "has_rois": video_info.get("has_rois", False),
                    "has_trajectory": video_info.get("has_trajectory", False),
                }
                self.video_configs.append(full_config)

        if "roi_merge_strategy" in data:
            self.roi_merge_strategy_var.set(data["roi_merge_strategy"])

        # Refresh UI
        self._populate_table()
        self._update_summary()
        self._update_template_banner()
