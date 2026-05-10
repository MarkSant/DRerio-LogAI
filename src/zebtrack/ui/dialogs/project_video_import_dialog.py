"""Dialog for importing pre-recorded videos into an existing project."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tkinter import END, BooleanVar, IntVar, StringVar, messagebox, simpledialog, ttk
from typing import Any

import structlog

log = structlog.get_logger()


class SubjectEntriesDialog(simpledialog.Dialog):
    """Edit per-animal metadata for one imported video."""

    def __init__(
        self,
        parent: Any,
        *,
        available_groups: list[str],
        subject_entry_count: int,
        initial_entries: list[dict[str, Any]] | None = None,
        default_group: str | None = None,
        default_day: int | None = None,
    ) -> None:
        self.available_groups = available_groups
        self.subject_entry_count = max(1, subject_entry_count)
        self.initial_entries = deepcopy(initial_entries or [])
        self.default_group = default_group or ""
        self.default_day = default_day or 1
        self._rows: list[tuple[StringVar, IntVar, StringVar]] = []
        self.result: list[dict[str, Any]] | None = None
        super().__init__(parent, "Animais do Vídeo")

    def body(self, master):
        ttk.Label(
            master,
            text="Defina grupo, dia e sujeito para cada animal do vídeo.",
            wraplength=520,
            justify="left",
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 8), columnspan=4)

        header = ("Animal", "Grupo", "Dia", "Sujeito")
        for col, title in enumerate(header):
            ttk.Label(master, text=title).grid(row=1, column=col, sticky="w", padx=6, pady=(0, 4))

        for index in range(self.subject_entry_count):
            initial = self.initial_entries[index] if index < len(self.initial_entries) else {}
            group_var = StringVar(value=str(initial.get("group") or self.default_group or ""))
            day_var = IntVar(value=self._coerce_day(initial.get("day"), fallback=self.default_day))
            subject_var = StringVar(value=str(initial.get("subject") or ""))

            ttk.Label(master, text=f"{index + 1}").grid(
                row=index + 2, column=0, sticky="w", padx=6, pady=2
            )
            ttk.Combobox(
                master,
                textvariable=group_var,
                values=self.available_groups,
                state="normal",
                width=18,
            ).grid(row=index + 2, column=1, sticky="ew", padx=6, pady=2)
            ttk.Spinbox(
                master,
                from_=1,
                to=365,
                textvariable=day_var,
                width=8,
            ).grid(row=index + 2, column=2, sticky="w", padx=6, pady=2)
            ttk.Entry(master, textvariable=subject_var, width=18).grid(
                row=index + 2, column=3, sticky="ew", padx=6, pady=2
            )
            self._rows.append((group_var, day_var, subject_var))

        return None

    def validate(self):
        for index, (group_var, day_var, subject_var) in enumerate(self._rows, start=1):
            if not group_var.get().strip():
                messagebox.showerror(
                    "Validação",
                    f"Informe o grupo do animal {index}.",
                    parent=self,
                )
                return 0
            if not subject_var.get().strip():
                messagebox.showerror(
                    "Validação",
                    f"Informe o sujeito do animal {index}.",
                    parent=self,
                )
                return 0
            try:
                if int(day_var.get()) <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                messagebox.showerror(
                    "Validação",
                    f"Informe um dia válido para o animal {index}.",
                    parent=self,
                )
                return 0
        return 1

    def apply(self):
        self.result = [
            {
                "group": group_var.get().strip(),
                "day": int(day_var.get()),
                "subject": subject_var.get().strip(),
            }
            for group_var, day_var, subject_var in self._rows
        ]

    @staticmethod
    def _coerce_day(value: Any, *, fallback: int) -> int:
        try:
            day = int(value)
            return day if day > 0 else fallback
        except (TypeError, ValueError):
            return fallback


class VideoMetadataDialog(simpledialog.Dialog):
    """Edit group/day/subject metadata for an existing project video."""

    def __init__(
        self,
        parent: Any,
        *,
        video_path: str,
        available_groups: list[str],
        initial_metadata: dict[str, Any] | None = None,
        subject_entry_count: int = 1,
    ) -> None:
        self.video_path = video_path
        self.available_groups = available_groups
        self.subject_entry_count = max(1, subject_entry_count)
        self.initial_metadata = deepcopy(initial_metadata or {})
        self.group_var = StringVar(value=str(self.initial_metadata.get("group") or ""))
        self.day_var = IntVar(
            value=SubjectEntriesDialog._coerce_day(
                self.initial_metadata.get("day"),
                fallback=1,
            )
        )
        self.subject_var = StringVar(value=str(self.initial_metadata.get("subject") or ""))
        self.subject_entries = deepcopy(self.initial_metadata.get("subject_entries") or [])
        self.result: dict[str, Any] | None = None
        super().__init__(parent, "Editar Metadata do Vídeo")

    def body(self, master):
        master.columnconfigure(1, weight=1)
        filename = Path(self.video_path).name

        ttk.Label(
            master,
            text=f"Arquivo: {filename}",
            wraplength=460,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 8))

        ttk.Label(master, text="Grupo").grid(row=1, column=0, sticky="w", padx=10, pady=2)
        ttk.Combobox(
            master,
            textvariable=self.group_var,
            values=self.available_groups,
            state="normal",
        ).grid(row=1, column=1, sticky="ew", padx=10, pady=2)

        ttk.Label(master, text="Dia").grid(row=2, column=0, sticky="w", padx=10, pady=2)
        ttk.Spinbox(
            master,
            from_=1,
            to=365,
            textvariable=self.day_var,
            width=10,
        ).grid(row=2, column=1, sticky="w", padx=10, pady=2)

        ttk.Label(master, text="Sujeito").grid(row=3, column=0, sticky="w", padx=10, pady=2)
        ttk.Entry(master, textvariable=self.subject_var).grid(
            row=3, column=1, sticky="ew", padx=10, pady=2
        )

        ttk.Button(
            master,
            text="Editar Animais do Vídeo...",
            command=self._edit_subject_entries,
        ).grid(row=4, column=0, columnspan=2, sticky="ew", padx=10, pady=(8, 10))

        return None

    def validate(self):
        if not self.group_var.get().strip():
            messagebox.showerror("Validação", "Informe o grupo do vídeo.", parent=self)
            return 0
        try:
            if int(self.day_var.get()) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            messagebox.showerror("Validação", "Informe um dia válido.", parent=self)
            return 0
        if not self.subject_entries and not self.subject_var.get().strip():
            messagebox.showerror("Validação", "Informe o sujeito do vídeo.", parent=self)
            return 0
        return 1

    def apply(self):
        result = {
            "group": self.group_var.get().strip(),
            "day": int(self.day_var.get()),
        }
        if self.subject_entries:
            result["subject_entries"] = deepcopy(self.subject_entries)
            if len(self.subject_entries) == 1:
                result["subject"] = str(self.subject_entries[0].get("subject") or "").strip()
        else:
            result["subject"] = self.subject_var.get().strip()
        self.result = result

    def _edit_subject_entries(self) -> None:
        dialog = SubjectEntriesDialog(
            self,
            available_groups=self.available_groups,
            subject_entry_count=self.subject_entry_count,
            initial_entries=deepcopy(self.subject_entries),
            default_group=self.group_var.get().strip(),
            default_day=int(self.day_var.get()),
        )
        if not dialog.result:
            return

        self.subject_entries = deepcopy(dialog.result)
        first_entry = self.subject_entries[0]
        self.group_var.set(str(first_entry.get("group") or self.group_var.get() or ""))
        self.day_var.set(SubjectEntriesDialog._coerce_day(first_entry.get("day"), fallback=1))
        if len(self.subject_entries) == 1:
            self.subject_var.set(str(first_entry.get("subject") or ""))
        else:
            self.subject_var.set("")


class BatchVideoMetadataDialog(simpledialog.Dialog):
    """Apply metadata updates to multiple project videos at once."""

    def __init__(
        self,
        parent: Any,
        *,
        target_label: str,
        target_kind: str,
        affected_count: int,
        available_groups: list[str],
        initial_values: dict[str, Any] | None = None,
        allow_subject: bool = False,
    ) -> None:
        self.target_label = target_label
        self.target_kind = target_kind
        self.affected_count = max(1, affected_count)
        self.available_groups = available_groups
        self.initial_values = deepcopy(initial_values or {})
        self.allow_subject = allow_subject

        self.apply_group_var = BooleanVar(value="group" in self.initial_values)
        self.group_var = StringVar(value=str(self.initial_values.get("group") or ""))
        self.apply_day_var = BooleanVar(value="day" in self.initial_values)
        self.day_var = IntVar(
            value=SubjectEntriesDialog._coerce_day(
                self.initial_values.get("day"),
                fallback=1,
            )
        )
        self.apply_subject_var = BooleanVar(
            value=allow_subject and "subject" in self.initial_values
        )
        self.subject_var = StringVar(value=str(self.initial_values.get("subject") or ""))
        self.result: dict[str, Any] | None = None
        super().__init__(parent, "Editar Metadata em Lote")

    def body(self, master):
        master.columnconfigure(1, weight=1)
        ttk.Label(
            master,
            text=(
                f"Aplicar alterações de metadata ao {self.target_kind} '{self.target_label}' "
                f"em {self.affected_count} vídeo(s)."
            ),
            wraplength=520,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 10))

        ttk.Checkbutton(
            master,
            text="Atualizar grupo",
            variable=self.apply_group_var,
            command=self._update_field_states,
        ).grid(row=1, column=0, sticky="w", padx=10, pady=2)
        self.group_combo = ttk.Combobox(
            master,
            textvariable=self.group_var,
            values=self.available_groups,
            state="normal",
        )
        self.group_combo.grid(row=1, column=1, sticky="ew", padx=10, pady=2)

        ttk.Checkbutton(
            master,
            text="Atualizar dia",
            variable=self.apply_day_var,
            command=self._update_field_states,
        ).grid(row=2, column=0, sticky="w", padx=10, pady=2)
        self.day_spinbox = ttk.Spinbox(
            master,
            from_=1,
            to=365,
            textvariable=self.day_var,
            width=10,
        )
        self.day_spinbox.grid(row=2, column=1, sticky="w", padx=10, pady=2)

        self.subject_checkbutton = None
        self.subject_entry = None
        if self.allow_subject:
            self.subject_checkbutton = ttk.Checkbutton(
                master,
                text="Atualizar sujeito",
                variable=self.apply_subject_var,
                command=self._update_field_states,
            )
            self.subject_checkbutton.grid(row=3, column=0, sticky="w", padx=10, pady=2)
            self.subject_entry = ttk.Entry(master, textvariable=self.subject_var)
            self.subject_entry.grid(row=3, column=1, sticky="ew", padx=10, pady=2)

        self._update_field_states()
        return None

    def validate(self):
        if (
            not self.apply_group_var.get()
            and not self.apply_day_var.get()
            and not self.apply_subject_var.get()
        ):
            messagebox.showerror(
                "Validação",
                "Selecione pelo menos um campo para atualizar em lote.",
                parent=self,
            )
            return 0
        if self.apply_group_var.get() and not self.group_var.get().strip():
            messagebox.showerror("Validação", "Informe o grupo a aplicar.", parent=self)
            return 0
        if self.apply_day_var.get():
            try:
                if int(self.day_var.get()) <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                messagebox.showerror("Validação", "Informe um dia válido.", parent=self)
                return 0
        if self.apply_subject_var.get() and not self.subject_var.get().strip():
            messagebox.showerror("Validação", "Informe o sujeito a aplicar.", parent=self)
            return 0
        return 1

    def apply(self):
        result: dict[str, Any] = {}
        if self.apply_group_var.get():
            result["group"] = self.group_var.get().strip()
        if self.apply_day_var.get():
            result["day"] = int(self.day_var.get())
        if self.apply_subject_var.get():
            result["subject"] = self.subject_var.get().strip()
        self.result = result

    def _update_field_states(self) -> None:
        self.group_combo.configure(state="normal" if self.apply_group_var.get() else "disabled")
        self.day_spinbox.configure(state="normal" if self.apply_day_var.get() else "disabled")
        if self.subject_entry is not None:
            self.subject_entry.configure(
                state="normal" if self.apply_subject_var.get() else "disabled"
            )


class ProjectVideoImportDialog(simpledialog.Dialog):
    """Review imported videos, assign metadata, and choose post-import action."""

    def __init__(
        self,
        parent: Any,
        *,
        scanned_videos: list[dict[str, Any]],
        available_groups: list[str],
        default_group: str | None = None,
        default_day: int | None = None,
        default_process_mode: str = "add_only",
        subject_entry_count: int = 1,
    ) -> None:
        self.available_groups = available_groups
        self.subject_entry_count = max(1, subject_entry_count)
        self.default_group_var = StringVar(value=default_group or "")
        self.default_day_var = IntVar(value=self._coerce_day(default_day, fallback=1))
        self.default_subject_var = StringVar(value="")
        self.process_mode_var = StringVar(value=default_process_mode)
        self.group_var = StringVar(value="")
        self.day_var = IntVar(value=1)
        self.subject_var = StringVar(value="")
        self.status_var = StringVar(value="")
        self.summary_var = StringVar(value="")
        self.tree: ttk.Treeview | None = None
        self.result: dict[str, Any] | None = None
        self._rows = [self._normalize_video_row(video) for video in scanned_videos]
        self._selected_index = 0
        super().__init__(parent, "Importar Vídeos ao Projeto")
        if self.result is None:
            self.result = {"confirmed": False, "videos": [], "process_mode": "add_only"}

    def body(self, master):
        master.columnconfigure(0, weight=3)
        master.columnconfigure(1, weight=2)
        master.rowconfigure(1, weight=1)

        ttk.Label(
            master,
            text=(
                "Revise os vídeos encontrados, defina grupo, dia e sujeito, e escolha se "
                "o lote será apenas adicionado ou também processado."
            ),
            wraplength=760,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 8))

        tree_frame = ttk.LabelFrame(master, text="Vídeos Encontrados", padding=8)
        tree_frame.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=(0, 10))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("status", "metadata", "subjects"),
            show="tree headings",
            height=14,
        )
        self.tree.heading("#0", text="Arquivo")
        self.tree.heading("status", text="Dados")
        self.tree.heading("metadata", text="Metadata")
        self.tree.heading("subjects", text="Animais")
        self.tree.column("#0", width=260, stretch=True)
        self.tree.column("status", width=140, stretch=False, anchor="center")
        self.tree.column("metadata", width=210, stretch=True)
        self.tree.column("subjects", width=90, stretch=False, anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        side_frame = ttk.Frame(master)
        side_frame.grid(row=1, column=1, sticky="nsew", padx=(6, 12), pady=(0, 10))
        side_frame.columnconfigure(0, weight=1)

        defaults_frame = ttk.LabelFrame(side_frame, text="Padrões do Lote", padding=8)
        defaults_frame.grid(row=0, column=0, sticky="ew")
        defaults_frame.columnconfigure(1, weight=1)
        ttk.Label(defaults_frame, text="Grupo").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Combobox(
            defaults_frame,
            textvariable=self.default_group_var,
            values=self.available_groups,
            state="normal",
        ).grid(row=0, column=1, sticky="ew", pady=2)
        ttk.Label(defaults_frame, text="Dia").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Spinbox(
            defaults_frame,
            from_=1,
            to=365,
            textvariable=self.default_day_var,
            width=8,
        ).grid(row=1, column=1, sticky="w", pady=2)
        ttk.Label(defaults_frame, text="Sujeito").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Entry(defaults_frame, textvariable=self.default_subject_var).grid(
            row=2, column=1, sticky="ew", pady=2
        )
        ttk.Button(
            defaults_frame,
            text="Aplicar aos Selecionados",
            command=self._apply_defaults_to_selected,
        ).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 2))
        ttk.Button(
            defaults_frame,
            text="Preencher Vazios no Lote",
            command=self._apply_defaults_to_blank_fields,
        ).grid(row=4, column=0, columnspan=2, sticky="ew", pady=2)

        detail_frame = ttk.LabelFrame(side_frame, text="Vídeo Selecionado", padding=8)
        detail_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        detail_frame.columnconfigure(1, weight=1)
        ttk.Label(detail_frame, text="Grupo").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Combobox(
            detail_frame,
            textvariable=self.group_var,
            values=self.available_groups,
            state="normal",
        ).grid(row=0, column=1, sticky="ew", pady=2)
        ttk.Label(detail_frame, text="Dia").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Spinbox(
            detail_frame,
            from_=1,
            to=365,
            textvariable=self.day_var,
            width=8,
        ).grid(row=1, column=1, sticky="w", pady=2)
        ttk.Label(detail_frame, text="Sujeito").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Entry(detail_frame, textvariable=self.subject_var).grid(
            row=2, column=1, sticky="ew", pady=2
        )
        ttk.Label(
            detail_frame,
            textvariable=self.status_var,
            foreground="#555555",
            wraplength=260,
            justify="left",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 4))
        ttk.Button(
            detail_frame,
            text="Salvar Neste Vídeo",
            command=self._save_selected_video,
        ).grid(row=4, column=0, columnspan=2, sticky="ew", pady=2)
        if self.subject_entry_count > 1:
            ttk.Button(
                detail_frame,
                text="Configurar Animais do Vídeo...",
                command=self._configure_subject_entries,
            ).grid(row=5, column=0, columnspan=2, sticky="ew", pady=2)

        processing_frame = ttk.LabelFrame(side_frame, text="Após Importar", padding=8)
        processing_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        options = [
            ("Apenas adicionar ao projeto", "add_only"),
            ("Adicionar e processar pendências", "process_pending"),
            ("Adicionar e reprocessar todos", "reprocess_all"),
        ]
        for index, (label, value) in enumerate(options):
            ttk.Radiobutton(
                processing_frame,
                text=label,
                value=value,
                variable=self.process_mode_var,
            ).grid(row=index, column=0, sticky="w", pady=1)

        ttk.Label(
            side_frame,
            textvariable=self.summary_var,
            foreground="#555555",
            wraplength=280,
            justify="left",
        ).grid(row=3, column=0, sticky="ew", pady=(10, 0))

        self._refresh_tree()
        self._load_selected_video(0)
        return self.tree

    def buttonbox(self):
        box = ttk.Frame(self)
        box.pack(pady=(0, 12))
        ttk.Button(box, text="Cancelar", command=self.cancel).pack(side="right", padx=6)
        ttk.Button(box, text="Importar", command=self.ok, default="active").pack(
            side="right", padx=6
        )
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)

    def validate(self):
        self._save_selected_video()
        if not self._rows:
            messagebox.showerror(
                "Validação",
                "Nenhum vídeo disponível para importação.",
                parent=self,
            )
            return 0

        for row in self._rows:
            if not str(row.get("group") or "").strip():
                messagebox.showerror(
                    "Validação",
                    f"Informe o grupo do vídeo {Path(str(row.get('path', ''))).name}.",
                    parent=self,
                )
                return 0

            day = self._coerce_day(row.get("day"), fallback=0)
            if day <= 0:
                messagebox.showerror(
                    "Validação",
                    f"Informe um dia válido para o vídeo {Path(str(row.get('path', ''))).name}.",
                    parent=self,
                )
                return 0

            has_subject_entries = bool(row.get("subject_entries"))
            has_subject = bool(str(row.get("subject") or "").strip())
            if not has_subject and not has_subject_entries:
                messagebox.showerror(
                    "Validação",
                    f"Informe o sujeito do vídeo {Path(str(row.get('path', ''))).name}.",
                    parent=self,
                )
                return 0

        return 1

    def apply(self):
        self._save_selected_video()
        videos = [self._build_output_row(row) for row in self._rows]
        self.result = {
            "confirmed": True,
            "videos": videos,
            "process_mode": self.process_mode_var.get(),
            "last_group": self.default_group_var.get().strip(),
            "last_day": int(self.default_day_var.get()),
        }

    def cancel(self, event=None):
        self.result = {"confirmed": False, "videos": [], "process_mode": "add_only"}
        super().cancel(event)

    def _refresh_tree(self) -> None:
        if not self.tree:
            return

        current_selection = self.tree.selection()
        selected_iid = current_selection[0] if current_selection else str(self._selected_index)
        for item in self.tree.get_children():
            self.tree.delete(item)

        for index, row in enumerate(self._rows):
            filename = Path(str(row.get("path", ""))).name
            self.tree.insert(
                "",
                END,
                iid=str(index),
                text=filename,
                values=(
                    self._format_status(row),
                    self._format_metadata(row),
                    self._format_subject_summary(row),
                ),
            )

        if self._rows:
            selection = selected_iid if selected_iid in self.tree.get_children() else "0"
            self.tree.selection_set(selection)
            self.tree.see(selection)
        self._update_summary()

    def _on_tree_select(self, _event=None) -> None:
        if not self.tree:
            return
        selection = self.tree.selection()
        if not selection:
            return
        self._load_selected_video(int(selection[0]))

    def _load_selected_video(self, index: int) -> None:
        if not self._rows:
            return
        index = max(0, min(index, len(self._rows) - 1))
        row = self._rows[index]
        self._selected_index = index
        self.group_var.set(str(row.get("group") or ""))
        self.day_var.set(self._coerce_day(row.get("day"), fallback=self.default_day_var.get()))
        self.subject_var.set(str(row.get("subject") or ""))
        self.status_var.set(
            f"{self._format_status(row)}. {self._format_subject_summary(row)} configurado(s)."
        )

    def _save_selected_video(self) -> None:
        if not self._rows:
            return
        row = self._rows[self._selected_index]
        row["group"] = self.group_var.get().strip()
        row["day"] = int(self.day_var.get())
        subject_text = self.subject_var.get().strip()
        if not row.get("subject_entries"):
            row["subject"] = subject_text
        elif len(row.get("subject_entries") or []) == 1:
            row["subject"] = subject_text or str(row["subject_entries"][0].get("subject") or "")
        self._refresh_tree()

    def _apply_defaults_to_selected(self) -> None:
        self._apply_defaults(selected_only=True)

    def _apply_defaults_to_blank_fields(self) -> None:
        self._apply_defaults(selected_only=False)

    def _apply_defaults(self, *, selected_only: bool) -> None:
        target_indexes = [self._selected_index] if selected_only else list(range(len(self._rows)))
        default_group = self.default_group_var.get().strip()
        default_day = int(self.default_day_var.get())
        default_subject = self.default_subject_var.get().strip()

        for index in target_indexes:
            row = self._rows[index]
            if selected_only or not str(row.get("group") or "").strip():
                row["group"] = default_group
            if selected_only or not self._coerce_day(row.get("day"), fallback=0):
                row["day"] = default_day
            if default_subject and (selected_only or not str(row.get("subject") or "").strip()):
                row["subject"] = default_subject
            if row.get("subject_entries"):
                for entry in row["subject_entries"]:
                    entry.setdefault("group", default_group)
                    entry.setdefault("day", default_day)

        self._load_selected_video(self._selected_index)
        self._refresh_tree()

    def _configure_subject_entries(self) -> None:
        if not self._rows:
            return
        row = self._rows[self._selected_index]
        dialog = SubjectEntriesDialog(
            self,
            available_groups=self.available_groups,
            subject_entry_count=self.subject_entry_count,
            initial_entries=deepcopy(row.get("subject_entries") or []),
            default_group=str(row.get("group") or self.default_group_var.get() or ""),
            default_day=self._coerce_day(row.get("day"), fallback=self.default_day_var.get()),
        )
        if not dialog.result:
            return

        row["subject_entries"] = deepcopy(dialog.result)
        row["is_multi_subject"] = len(dialog.result) > 1
        first_entry = dialog.result[0]
        row["group"] = first_entry.get("group") or row.get("group")
        row["day"] = self._coerce_day(
            first_entry.get("day"),
            fallback=self.default_day_var.get(),
        )
        row["subject"] = "" if len(dialog.result) > 1 else str(first_entry.get("subject") or "")
        self._load_selected_video(self._selected_index)
        self._refresh_tree()

    def _update_summary(self) -> None:
        total = len(self._rows)
        with_trajectory = sum(1 for row in self._rows if row.get("has_trajectory"))
        with_zones = sum(
            1
            for row in self._rows
            if row.get("has_arena") and row.get("has_rois") and not row.get("has_trajectory")
        )
        arena_only = sum(
            1 for row in self._rows if row.get("has_arena") and not row.get("has_rois")
        )
        without_arena = sum(1 for row in self._rows if not row.get("has_arena"))
        self.summary_var.set(
            f"Total: {total}\n"
            f"Trajetória pronta: {with_trajectory}\n"
            f"Zonas prontas: {with_zones}\n"
            f"Só arena: {arena_only}\n"
            f"Sem arena: {without_arena}"
        )

    def _normalize_video_row(self, video: dict[str, Any]) -> dict[str, Any]:
        metadata = deepcopy(video.get("metadata") or {})
        group = metadata.get("group") or video.get("group") or self.default_group_var.get().strip()
        day = self._coerce_day(
            metadata.get("day") or video.get("day"),
            fallback=self.default_day_var.get(),
        )
        subject_entries = deepcopy(
            metadata.get("subject_entries") or video.get("subject_entries") or []
        )
        subject = metadata.get("subject") or video.get("subject") or ""
        if subject_entries and len(subject_entries) > 1:
            subject = ""

        return {
            **deepcopy(video),
            "group": group,
            "day": day,
            "subject": str(subject or ""),
            "subject_entries": subject_entries,
            "is_multi_subject": bool(subject_entries and len(subject_entries) > 1),
        }

    def _build_output_row(self, row: dict[str, Any]) -> dict[str, Any]:
        metadata: dict[str, Any] = dict(row.get("metadata") or {})
        metadata["group"] = str(row.get("group") or "").strip()
        metadata["day"] = int(row.get("day") or 1)
        subject = str(row.get("subject") or "").strip()
        subject_entries = deepcopy(row.get("subject_entries") or [])

        if subject_entries:
            metadata["subject_entries"] = subject_entries
            metadata["is_multi_subject"] = len(subject_entries) > 1
            if len(subject_entries) == 1:
                metadata["subject"] = str(subject_entries[0].get("subject") or subject)
            else:
                metadata.pop("subject", None)
        else:
            metadata.pop("subject_entries", None)
            metadata.pop("is_multi_subject", None)
            metadata["subject"] = subject

        output = deepcopy(row)
        output["group"] = metadata["group"]
        output["day"] = metadata["day"]
        output["subject"] = metadata.get("subject")
        output["subject_entries"] = subject_entries
        output["is_multi_subject"] = bool(metadata.get("is_multi_subject", False))
        output["metadata"] = metadata
        output["has_data"] = bool(output.get("has_data", output.get("has_complete_data", False)))
        return output

    @staticmethod
    def _coerce_day(value: Any, fallback: int) -> int:
        try:
            day = int(value)
            return day if day > 0 else fallback
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _format_status(row: dict[str, Any]) -> str:
        if row.get("has_trajectory"):
            return "Trajetória pronta"
        if row.get("has_arena") and row.get("has_rois"):
            return "Zonas prontas"
        if row.get("has_arena"):
            return "Só arena"
        return "Sem arena"

    @staticmethod
    def _format_metadata(row: dict[str, Any]) -> str:
        group = str(row.get("group") or "").strip() or "?"
        day = row.get("day") or "?"
        subject = str(row.get("subject") or "").strip()
        if row.get("subject_entries") and len(row.get("subject_entries") or []) > 1:
            subject = "multi"
        elif not subject:
            subject = "?"
        return f"G:{group} D:{day} S:{subject}"

    @staticmethod
    def _format_subject_summary(row: dict[str, Any]) -> str:
        subject_entries = row.get("subject_entries") or []
        if subject_entries:
            return f"{len(subject_entries)} animal(is)"
        subject = str(row.get("subject") or "").strip()
        return subject or "Sem sujeito"
