"""
Design Editor Dialog.

Allows manual editing of detected experimental design (groups, days, subjects).
"""

from collections.abc import Callable
from tkinter import (
    Button,
    Canvas,
    Entry,
    Frame,
    Label,
    Listbox,
    StringVar,
    messagebox,
)
from tkinter import (
    font as tkfont,
)
from tkinter.simpledialog import Dialog

import structlog

from zebtrack.ui.window_utils import create_scrollbar
from zebtrack.ui.wizard.custom_regex_dialog import CustomRegexDialog

log = structlog.get_logger()


class DesignEditorDialog(Dialog):
    """
    Dialog for manual editing of experimental design.

    Allows user to:
    - Edit group names
    - Edit day names
    - Edit subject IDs
    - Add/remove groups, days, or subjects

    Args:
        parent: Parent window
        design: Current detected design dict

    Returns:
        Modified design dict or None if cancelled
    """

    def __init__(
        self,
        parent,
        design: dict | None,
        *,
        custom_regex_patterns: dict | None = None,
        on_custom_regex_configured: Callable[[dict], dict | None] | None = None,
        sample_paths: list[str] | None = None,
    ):
        """Prepare working copies before showing the dialog."""
        design = design or {}

        self.input_design = design.copy()
        self.edited_design: dict | None = None
        self.custom_regex_patterns = custom_regex_patterns.copy() if custom_regex_patterns else None
        self.on_custom_regex_configured = on_custom_regex_configured
        self.sample_paths = sample_paths or []

        self.groups = list(design.get("groups", []))
        self.days = list(design.get("days", []) or [])
        self.subjects_per_group = {
            group: list(subjects)
            for group, subjects in (design.get("subjects_per_group") or {}).items()
        }

        self.group_display_names = dict(design.get("group_display_names") or {})
        for group in self.groups:
            self.group_display_names.setdefault(group, group)

        super().__init__(parent, title="Editar Design Experimental")

    def body(self, master):
        """Build dialog UI with friendly name controls."""
        title_font = tkfont.Font(size=12, weight="bold")
        Label(
            master,
            text="Edição Manual do Design Experimental",
            font=title_font,
        ).pack(pady=(0, 15))

        # --- Groups section -------------------------------------------------
        groups_frame = Frame(master)
        groups_frame.pack(fill="both", expand=True, padx=10, pady=5)

        Label(
            groups_frame,
            text="Grupos Experimentais:",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w")

        Label(
            groups_frame,
            text="Configure o ID original e o nome descritivo para cada grupo.",
            font=("TkDefaultFont", 8),
            foreground="gray",
        ).pack(anchor="w", pady=(0, 5))

        action_frame = Frame(groups_frame)
        action_frame.pack(fill="x", pady=(0, 5))

        Button(
            action_frame,
            text="🔧 Regex Customizado",
            command=self._open_custom_regex_dialog,
            width=20,
        ).pack(side="right")

        header_frame = Frame(groups_frame, relief="solid", borderwidth=1)
        header_frame.pack(fill="x")
        self._configure_group_columns(header_frame)

        Label(
            header_frame,
            text="ID Original",
            font=("TkDefaultFont", 9, "bold"),
            relief="ridge",
        ).grid(row=0, column=0, sticky="nsew", padx=(0, 1))
        Label(
            header_frame,
            text="Nome para Exibição",
            font=("TkDefaultFont", 9, "bold"),
            relief="ridge",
        ).grid(row=0, column=1, sticky="nsew", padx=(0, 1))
        Label(
            header_frame,
            text="Ações",
            font=("TkDefaultFont", 9, "bold"),
            relief="ridge",
        ).grid(row=0, column=2, sticky="nsew")

        table_container = Frame(groups_frame)
        table_container.pack(fill="both", expand=True)

        self.groups_canvas = Canvas(
            table_container,
            height=160,
            borderwidth=0,
            highlightthickness=0,
        )
        groups_scrollbar = create_scrollbar(
            table_container,
            orient="vertical",
            command=self.groups_canvas.yview,
        )
        self.groups_canvas.configure(yscrollcommand=groups_scrollbar.set)

        self.groups_rows_frame = Frame(self.groups_canvas)
        self._configure_group_columns(self.groups_rows_frame)
        self.groups_rows_window = self.groups_canvas.create_window(
            (0, 0), window=self.groups_rows_frame, anchor="nw"
        )

        self.groups_canvas.pack(side="left", fill="both", expand=True)
        groups_scrollbar.pack(side="right", fill="y")

        self.groups_canvas.bind("<Configure>", self._on_groups_canvas_configure)

        self.groups_rows_frame.bind(
            "<Configure>",
            lambda _event: self.groups_canvas.configure(
                scrollregion=self.groups_canvas.bbox("all")
            ),
        )

        self.group_id_labels: list[Label] = []
        self.group_name_entries: list[Entry] = []
        self.group_name_vars: list[StringVar] = []

        add_group_frame = Frame(groups_frame)
        add_group_frame.pack(fill="x", pady=(5, 0))

        Label(add_group_frame, text="Novo Grupo ID:").pack(side="left")
        self.new_group_id_var = StringVar()
        self.new_group_id_entry = Entry(
            add_group_frame,
            textvariable=self.new_group_id_var,
            width=15,
        )
        self.new_group_id_entry.pack(side="left", padx=5)

        Label(add_group_frame, text="Nome:").pack(side="left")
        self.new_group_name_var = StringVar()
        self.new_group_name_entry = Entry(
            add_group_frame,
            textvariable=self.new_group_name_var,
            width=25,
        )
        self.new_group_name_entry.pack(side="left", padx=5)

        Button(
            add_group_frame,
            text="➕ Adicionar Grupo",
            command=self._add_group,
        ).pack(side="left", padx=5)

        # --- Days section ---------------------------------------------------
        days_frame = Frame(master)
        days_frame.pack(fill="both", expand=True, padx=10, pady=5)

        Label(
            days_frame,
            text="Dias:",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w")

        days_list_frame = Frame(days_frame)
        days_list_frame.pack(fill="both", expand=True, pady=5)

        days_scrollbar = create_scrollbar(days_list_frame)
        days_scrollbar.pack(side="right", fill="y")

        self.days_listbox = Listbox(
            days_list_frame,
            yscrollcommand=days_scrollbar.set,
            height=5,
        )
        self.days_listbox.pack(side="left", fill="both", expand=True)
        days_scrollbar.config(command=self.days_listbox.yview)

        days_btn_frame = Frame(days_frame)
        days_btn_frame.pack(fill="x", pady=5)

        self.day_entry_var = StringVar()
        Entry(days_btn_frame, textvariable=self.day_entry_var, width=20).pack(
            side="left", padx=(0, 5)
        )
        Button(days_btn_frame, text="Adicionar Dia", command=self._add_day).pack(
            side="left", padx=2
        )
        Button(
            days_btn_frame,
            text="Remover Selecionado",
            command=self._remove_day,
        ).pack(side="left", padx=2)

        help_text = Label(
            master,
            text=(
                "💡 Dica: Configure os grupos com nomes amigáveis. "
                "Os sujeitos são derivados automaticamente dos arquivos."
            ),
            fg="gray",
            wraplength=450,
            justify="left",
        )
        help_text.pack(pady=10, padx=10)

        self._refresh_groups_table()
        self._refresh_days_list()

        return self.new_group_id_entry

    def buttonbox(self):
        """Override to add OK and Cancel buttons."""
        box = Frame(self)

        Button(box, text="Salvar", width=10, command=self.ok, default="active").pack(
            side="left", padx=5, pady=5
        )
        Button(box, text="Cancelar", width=10, command=self.cancel).pack(
            side="left", padx=5, pady=5
        )

        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)

        box.pack()

    def _configure_group_columns(self, container: Frame) -> None:
        container.grid_columnconfigure(0, weight=2, uniform="group_table")
        container.grid_columnconfigure(1, weight=3, uniform="group_table")
        container.grid_columnconfigure(2, weight=0, minsize=90)

    def _on_groups_canvas_configure(self, event) -> None:
        if hasattr(self, "groups_rows_window"):
            self.groups_canvas.itemconfig(self.groups_rows_window, width=event.width)

    def _refresh_groups_table(self) -> None:
        for widget in self.groups_rows_frame.winfo_children():
            widget.destroy()

        self.group_id_labels.clear()
        self.group_name_entries.clear()
        self.group_name_vars.clear()

        for index, group_id in enumerate(self.groups):
            id_label = Label(
                self.groups_rows_frame,
                text=group_id,
                anchor="w",
                relief="groove",
                bg="lightgray",
            )
            id_label.grid(row=index, column=0, sticky="nsew", padx=(0, 1), pady=(0, 1))
            self.group_id_labels.append(id_label)

            name_var = StringVar(value=self.group_display_names.get(group_id, group_id))
            name_entry = Entry(
                self.groups_rows_frame,
                textvariable=name_var,
                relief="groove",
            )
            name_entry.grid(
                row=index,
                column=1,
                sticky="nsew",
                padx=(0, 1),
                pady=(0, 1),
            )
            self.group_name_vars.append(name_var)
            self.group_name_entries.append(name_entry)

            Button(
                self.groups_rows_frame,
                text="🗑️",
                width=6,
                command=lambda idx=index: self._remove_group(idx),
            ).grid(row=index, column=2, sticky="nsew", pady=(0, 1))

        self.groups_rows_frame.update_idletasks()
        self.groups_canvas.configure(scrollregion=self.groups_canvas.bbox("all"))

    def _refresh_days_list(self) -> None:
        self.days_listbox.delete(0, "end")
        for day in self.days:
            self.days_listbox.insert("end", day)

    def _load_design(self, design: dict | None) -> None:
        design = design or {}

        self.input_design = design.copy()
        self.edited_design = None

        self.groups = list(design.get("groups", []))
        self.days = list(design.get("days") or [])
        self.subjects_per_group = {
            group: list(subjects)
            for group, subjects in (design.get("subjects_per_group") or {}).items()
        }

        self.group_display_names = dict(design.get("group_display_names") or {})
        for group in self.groups:
            self.group_display_names.setdefault(group, group)

        if hasattr(self, "group_id_labels"):
            self._refresh_groups_table()
        if hasattr(self, "days_listbox"):
            self._refresh_days_list()
        if hasattr(self, "new_group_id_var"):
            self.new_group_id_var.set("")
        if hasattr(self, "new_group_name_var"):
            self.new_group_name_var.set("")
        if hasattr(self, "day_entry_var"):
            self.day_entry_var.set("")

        if hasattr(self, "groups_canvas"):
            try:
                self.groups_canvas.yview_moveto(0)
            except Exception:  # pragma: no cover - depends on widget state
                pass

    def _open_custom_regex_dialog(self) -> None:
        dialog = CustomRegexDialog(
            self,
            self.custom_regex_patterns or {},
            sample_paths=self.sample_paths,
        )
        result_patterns = dialog.get_result()

        if result_patterns is None:
            return

        active_patterns = {key: value for key, value in result_patterns.items() if value}
        self.custom_regex_patterns = result_patterns.copy() if active_patterns else None

        new_design: dict | None = None
        if self.on_custom_regex_configured:
            try:
                new_design = self.on_custom_regex_configured(result_patterns)
            except Exception:  # pragma: no cover - defensive logging only
                log.exception("design_editor.custom_regex_callback_failed")

        self._load_design(new_design)

        if new_design is None and active_patterns:
            messagebox.showwarning(
                "Regex sem resultados",
                (
                    "Os padrões regex personalizados não identificaram automaticamente "
                    "o design. Ajuste os padrões ou edite manualmente."
                ),
                parent=self,
            )

    def _add_group(self) -> None:
        group_id = self.new_group_id_var.get().strip()
        display_name = self.new_group_name_var.get().strip()

        if not group_id:
            messagebox.showwarning("ID Vazio", "Digite um ID para o novo grupo.", parent=self)
            return

        if group_id in self.groups:
            messagebox.showwarning("ID Duplicado", f"O grupo '{group_id}' já existe.", parent=self)
            return

        self.groups.append(group_id)
        self.subjects_per_group[group_id] = []
        self.group_display_names[group_id] = display_name or group_id

        self.new_group_id_var.set("")
        self.new_group_name_var.set("")

        self._refresh_groups_table()

        log.info(
            "design_editor.group_added",
            group=group_id,
            display_name=self.group_display_names[group_id],
        )

    def _remove_group(self, index: int) -> None:
        if index < 0 or index >= len(self.groups):
            return

        group_id = self.groups[index]
        if not messagebox.askyesno(
            "Confirmar Remoção",
            f"Remover grupo '{group_id}'?",
            parent=self,
        ):
            return

        self.groups.pop(index)
        self.group_display_names.pop(group_id, None)
        self.subjects_per_group.pop(group_id, None)

        self._refresh_groups_table()

        log.info("design_editor.group_removed", group=group_id)

    def _add_day(self) -> None:
        day_name = self.day_entry_var.get().strip()

        if not day_name:
            messagebox.showwarning(
                "Dia Vazio",
                "Por favor, digite um nome para o dia.",
                parent=self,
            )
            return

        if day_name in self.days:
            messagebox.showwarning("Dia Duplicado", f"O dia '{day_name}' já existe.", parent=self)
            return

        self.days.append(day_name)
        self.day_entry_var.set("")
        self._refresh_days_list()

        log.info("design_editor.day_added", day=day_name)

    def _remove_day(self) -> None:
        selection = self.days_listbox.curselection()
        if not selection:
            messagebox.showwarning(
                "Nenhum Dia Selecionado",
                "Selecione um dia para remover.",
                parent=self,
            )
            return

        index = selection[0]
        day_name = self.days[index]

        if not messagebox.askyesno(
            "Confirmar Remoção",
            f"Tem certeza que deseja remover o dia '{day_name}'?",
            parent=self,
        ):
            return

        self.days.pop(index)
        self._refresh_days_list()

        log.info("design_editor.day_removed", day=day_name)

    def apply(self):
        """Validate and persist friendly names before closing."""
        if not self.groups:
            messagebox.showerror(
                "Erro de Validação",
                "É necessário ter pelo menos um grupo.",
                parent=self,
            )
            return

        for index, group_id in enumerate(self.groups):
            if index < len(self.group_name_vars):
                display_name = self.group_name_vars[index].get().strip()
                self.group_display_names[group_id] = display_name or group_id

        self.edited_design = {
            "groups": list(self.groups),
            "days": list(self.days) or None,
            "subjects_per_group": self.subjects_per_group,
            "pattern_used": "manual_edit",
            "confidence": 1.0,
            "group_display_names": self.group_display_names.copy(),
        }

        # Preserve subject_mappings from input_design if it exists (for multi-subject files)
        if self.input_design.get("subject_mappings"):
            self.edited_design["subject_mappings"] = self.input_design["subject_mappings"]

        log.info(
            "design_editor.saved",
            groups=len(self.groups),
            days=len(self.days),
            display_names=list(self.group_display_names.values()),
        )

    def get_result(self) -> dict | None:
        """Get the design editor result data.

        Returns:
            Dictionary with ROI and arena configuration, or None if cancelled.
        """
        return self.edited_design
