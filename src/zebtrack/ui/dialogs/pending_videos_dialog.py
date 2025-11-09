"""
PendingVideosDialog

Extracted from gui.py for better modularity.
"""

from tkinter import (
    BooleanVar,
    Frame,
    simpledialog,
    ttk,
)
from typing import ClassVar


class PendingVideosDialog(simpledialog.Dialog):
    """Dialog para revisar vídeos pendentes em formato hierárquico."""

    TAG_STYLES: ClassVar[dict[str, dict[str, str]]] = {
        "ready_full": {"background": "#d4edda", "foreground": "#1e4620"},
        "ready_partial": {"background": "#fff3cd", "foreground": "#5c470b"},
        "ready_missing": {"background": "#f8d7da", "foreground": "#842029"},
    }

    def __init__(
        self,
        parent,
        hierarchy_builder,
        ready_with_trajectory: list[dict],
        ready_with_zones: list[dict],
        arena_only: list[dict],
        without_arena: list[dict],
    ):
        self.hierarchy_builder = hierarchy_builder
        self.ready_with_trajectory = ready_with_trajectory or []
        self.ready_with_zones = ready_with_zones or []
        self.arena_only = arena_only or []
        self.without_arena = without_arena or []
        self.include_arena_only_var = BooleanVar(value=False)
        # Must call super().__init__ before setting result, as Dialog base sets it to None
        super().__init__(parent, "Processar Vídeos Pendentes")
        # Set default result after Dialog initialization
        if self.result is None:
            self.result = {"confirmed": False, "include_arena_only": False}

    def body(self, master):
        master.columnconfigure(0, weight=1)
        master.rowconfigure(1, weight=1)

        ttk.Label(
            master,
            text=("Revise a lista hierárquica e confirme os itens que deseja processar."),
            wraplength=560,
            justify="left",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 6))

        container = ttk.Frame(master)
        container.grid(row=1, column=0, sticky="nsew", padx=12)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)

        columns = ("status", "arquivo")
        self.tree = ttk.Treeview(
            container,
            columns=columns,
            show="tree headings",
            height=15,
            selectmode="none",
        )
        self.tree.heading("#0", text="Hierarquia")
        self.tree.heading("status", text="Dados")
        self.tree.heading("arquivo", text="Arquivo")
        self.tree.column("#0", width=260, stretch=True)
        self.tree.column("status", width=180, anchor="center", stretch=False)
        self.tree.column("arquivo", width=220, stretch=True)

        vsb = ttk.Scrollbar(container, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(container, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        for tag, style in self.TAG_STYLES.items():
            self.tree.tag_configure(tag, **style)
        self.tree.tag_configure("ready_optional", foreground="#5f4b00")

        self._populate_tree()

        legend = ttk.Frame(master)
        legend.grid(row=2, column=0, sticky="w", padx=12, pady=(8, 4))
        ttk.Label(legend, text="Legenda:").pack(side="left", padx=(0, 6))
        self._add_legend_chip(legend, "#d4edda", "#1e4620", "Pronto")
        self._add_legend_chip(legend, "#fff3cd", "#5c470b", "Parcial")
        self._add_legend_chip(legend, "#f8d7da", "#842029", "Ignorado")

        if self.arena_only:
            ttk.Checkbutton(
                master,
                text=(
                    f"Incluir {len(self.arena_only)} vídeo(s) com apenas arena no processamento."
                ),
                variable=self.include_arena_only_var,
            ).grid(row=3, column=0, sticky="w", padx=12, pady=(0, 12))
        else:
            ttk.Frame(master).grid(row=3, column=0, pady=(0, 12))

        return self.tree

    def buttonbox(self):
        box = ttk.Frame(self)
        box.pack(pady=(0, 12))
        ttk.Button(box, text="Cancelar", command=self.cancel).pack(side="right", padx=6)
        ttk.Button(box, text="Processar", command=self.ok, default="active").pack(
            side="right", padx=6
        )
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)

    def apply(self):
        self.result = {
            "confirmed": True,
            "include_arena_only": bool(self.include_arena_only_var.get())
            if self.arena_only
            else False,
        }

    def cancel(self, event=None):
        self.result = {"confirmed": False, "include_arena_only": False}
        super().cancel(event)

    def _populate_tree(self) -> None:
        hierarchy = self.hierarchy_builder() if callable(self.hierarchy_builder) else []

        readiness_map: dict[str, tuple[str, ...]] = {}

        def _assign(entries: list[dict], *tags: str):
            for info in entries or []:
                path = info.get("path")
                if path:
                    readiness_map[path] = tuple(tags)

        _assign(self.ready_with_trajectory, "ready_full")
        _assign(self.ready_with_zones, "ready_partial")
        _assign(self.arena_only, "ready_partial", "ready_optional")
        _assign(self.without_arena, "ready_missing")

        for group in hierarchy:
            group_node = self.tree.insert(
                "",
                "end",
                text=group.get("label", ""),
                values=(
                    group.get("status_label", ""),
                    group.get("filename_display", ""),
                ),
                open=True,
            )
            for day in group.get("children", []):
                day_node = self.tree.insert(
                    group_node,
                    "end",
                    text=day.get("label", ""),
                    values=(day.get("status_label", ""), ""),
                    open=False,
                )
                for video in day.get("children", []):
                    path = video.get("path")
                    tags = readiness_map.get(path, ()) if path else ()
                    self.tree.insert(
                        day_node,
                        "end",
                        text=video.get("label", ""),
                        values=(
                            video.get("status_label", ""),
                            video.get("filename", ""),
                        ),
                        tags=tags,
                    )

    @staticmethod
    def _add_legend_chip(parent, background: str, foreground: str, text: str) -> None:
        chip = ttk.Frame(parent)
        chip.pack(side="left", padx=4)
        swatch = Frame(
            chip,
            width=14,
            height=14,
            bg=background,
            highlightbackground="#c0c0c0",
            highlightthickness=1,
        )
        swatch.pack(side="left", padx=(0, 4))
        swatch.pack_propagate(False)
        ttk.Label(chip, text=text, foreground=foreground).pack(side="left")
