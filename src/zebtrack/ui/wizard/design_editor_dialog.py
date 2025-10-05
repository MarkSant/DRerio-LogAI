"""
Design Editor Dialog

Allows manual editing of detected experimental design (groups, days, subjects).
"""

from tkinter import (
    Button,
    Entry,
    Frame,
    Label,
    Listbox,
    Scrollbar,
    StringVar,
    messagebox,
)
from tkinter import (
    font as tkfont,
)
from tkinter.simpledialog import Dialog

import structlog

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

    def __init__(self, parent, design: dict):
        """
        Initialize design editor dialog.

        Args:
            parent: Parent window
            design: Design dict with keys:
                - groups: list[str]
                - days: list[str] | None
                - subjects_per_group: dict[str, list[str]]
                - pattern_used: str
                - confidence: float
        """
        self.input_design = design.copy() if design else {}
        self.edited_design = None

        # Initialize working copies
        self.groups = list(design.get("groups", []))
        self.days = list(design.get("days", [])) if design.get("days") else []
        self.subjects_per_group = {
            group: list(subjects)
            for group, subjects in design.get("subjects_per_group", {}).items()
        }

        # UI state
        self.selected_group_index = None
        self.selected_day_index = None

        super().__init__(parent, title="Editar Design Experimental")

    def body(self, master):
        """Build dialog UI."""
        # Title
        title_font = tkfont.Font(size=12, weight="bold")
        Label(
            master,
            text="Edição Manual do Design Experimental",
            font=title_font,
        ).pack(pady=(0, 15))

        # Groups section
        groups_frame = Frame(master)
        groups_frame.pack(fill="both", expand=True, padx=10, pady=5)

        Label(
            groups_frame, text="Grupos:", font=("TkDefaultFont", 10, "bold")
        ).pack(anchor="w")

        # Groups listbox with scrollbar
        groups_list_frame = Frame(groups_frame)
        groups_list_frame.pack(fill="both", expand=True, pady=5)

        groups_scrollbar = Scrollbar(groups_list_frame)
        groups_scrollbar.pack(side="right", fill="y")

        self.groups_listbox = Listbox(
            groups_list_frame,
            yscrollcommand=groups_scrollbar.set,
            height=5,
        )
        self.groups_listbox.pack(side="left", fill="both", expand=True)
        groups_scrollbar.config(command=self.groups_listbox.yview)

        # Groups buttons
        groups_btn_frame = Frame(groups_frame)
        groups_btn_frame.pack(fill="x", pady=5)

        self.group_entry_var = StringVar()
        Entry(
            groups_btn_frame, textvariable=self.group_entry_var, width=20
        ).pack(side="left", padx=(0, 5))

        Button(
            groups_btn_frame, text="Adicionar Grupo", command=self._add_group
        ).pack(side="left", padx=2)
        Button(
            groups_btn_frame, text="Remover Selecionado", command=self._remove_group
        ).pack(side="left", padx=2)

        # Days section
        days_frame = Frame(master)
        days_frame.pack(fill="both", expand=True, padx=10, pady=5)

        Label(days_frame, text="Dias:", font=("TkDefaultFont", 10, "bold")).pack(
            anchor="w"
        )

        # Days listbox with scrollbar
        days_list_frame = Frame(days_frame)
        days_list_frame.pack(fill="both", expand=True, pady=5)

        days_scrollbar = Scrollbar(days_list_frame)
        days_scrollbar.pack(side="right", fill="y")

        self.days_listbox = Listbox(
            days_list_frame,
            yscrollcommand=days_scrollbar.set,
            height=5,
        )
        self.days_listbox.pack(side="left", fill="both", expand=True)
        days_scrollbar.config(command=self.days_listbox.yview)

        # Days buttons
        days_btn_frame = Frame(days_frame)
        days_btn_frame.pack(fill="x", pady=5)

        self.day_entry_var = StringVar()
        Entry(
            days_btn_frame, textvariable=self.day_entry_var, width=20
        ).pack(side="left", padx=(0, 5))

        Button(
            days_btn_frame, text="Adicionar Dia", command=self._add_day
        ).pack(side="left", padx=2)
        Button(
            days_btn_frame, text="Remover Selecionado", command=self._remove_day
        ).pack(side="left", padx=2)

        # Help text
        help_text = Label(
            master,
            text=(
                "💡 Dica: Edite os grupos e dias conforme necessário. "
                "Os sujeitos são auto-detectados dos nomes dos arquivos."
            ),
            fg="gray",
            wraplength=450,
            justify="left",
        )
        help_text.pack(pady=10, padx=10)

        # Populate lists
        self._refresh_groups_list()
        self._refresh_days_list()

        return self.groups_listbox  # Initial focus

    def buttonbox(self):
        """Override to add OK and Cancel buttons."""
        box = Frame(self)

        Button(
            box, text="Salvar", width=10, command=self.ok, default="active"
        ).pack(side="left", padx=5, pady=5)
        Button(box, text="Cancelar", width=10, command=self.cancel).pack(
            side="left", padx=5, pady=5
        )

        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)

        box.pack()

    def _refresh_groups_list(self):
        """Refresh groups listbox."""
        self.groups_listbox.delete(0, "end")
        for group in self.groups:
            subject_count = len(self.subjects_per_group.get(group, []))
            self.groups_listbox.insert("end", f"{group} ({subject_count} sujeitos)")

    def _refresh_days_list(self):
        """Refresh days listbox."""
        self.days_listbox.delete(0, "end")
        for day in self.days:
            self.days_listbox.insert("end", day)

    def _add_group(self):
        """Add new group."""
        group_name = self.group_entry_var.get().strip()

        if not group_name:
            messagebox.showwarning(
                "Grupo Vazio", "Por favor, digite um nome para o grupo."
            )
            return

        if group_name in self.groups:
            messagebox.showwarning(
                "Grupo Duplicado", f"O grupo '{group_name}' já existe."
            )
            return

        self.groups.append(group_name)
        self.subjects_per_group[group_name] = []  # Empty subject list for new group
        self.group_entry_var.set("")
        self._refresh_groups_list()

        log.info("design_editor.group_added", group=group_name)

    def _remove_group(self):
        """Remove selected group."""
        selection = self.groups_listbox.curselection()
        if not selection:
            messagebox.showwarning(
                "Nenhum Grupo Selecionado", "Selecione um grupo para remover."
            )
            return

        index = selection[0]
        group_name = self.groups[index]

        if not messagebox.askyesno(
            "Confirmar Remoção",
            f"Tem certeza que deseja remover o grupo '{group_name}'?"
        ):
            return

        del self.groups[index]
        if group_name in self.subjects_per_group:
            del self.subjects_per_group[group_name]

        self._refresh_groups_list()

        log.info("design_editor.group_removed", group=group_name)

    def _add_day(self):
        """Add new day."""
        day_name = self.day_entry_var.get().strip()

        if not day_name:
            messagebox.showwarning("Dia Vazio", "Por favor, digite um nome para o dia.")
            return

        if day_name in self.days:
            messagebox.showwarning("Dia Duplicado", f"O dia '{day_name}' já existe.")
            return

        self.days.append(day_name)
        self.day_entry_var.set("")
        self._refresh_days_list()

        log.info("design_editor.day_added", day=day_name)

    def _remove_day(self):
        """Remove selected day."""
        selection = self.days_listbox.curselection()
        if not selection:
            messagebox.showwarning(
                "Nenhum Dia Selecionado", "Selecione um dia para remover."
            )
            return

        index = selection[0]
        day_name = self.days[index]

        if not messagebox.askyesno(
            "Confirmar Remoção",
            f"Tem certeza que deseja remover o dia '{day_name}'?"
        ):
            return

        del self.days[index]
        self._refresh_days_list()

        log.info("design_editor.day_removed", day=day_name)

    def apply(self):
        """Apply changes (called when OK is clicked)."""
        if not self.groups:
            messagebox.showerror(
                "Erro de Validação",
                "É necessário ter pelo menos um grupo."
            )
            return

        # Build edited design
        self.edited_design = {
            "groups": self.groups,
            "days": self.days if self.days else None,
            "subjects_per_group": self.subjects_per_group,
            "pattern_used": "manual_edit",  # Mark as manually edited
            "confidence": 1.0,  # Manual edit = 100% confidence
        }

        log.info(
            "design_editor.saved",
            groups=len(self.groups),
            days=len(self.days) if self.days else 0,
        )

    def get_result(self):
        """Get edited design (call after dialog closes)."""
        return self.edited_design
