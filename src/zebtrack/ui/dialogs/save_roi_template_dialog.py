"""
SaveROITemplateDialog.

Extracted from gui.py for better modularity.
"""

import re
from pathlib import Path
from tkinter import (
    BooleanVar,
    StringVar,
    filedialog,
    messagebox,
    simpledialog,
    ttk,
)
from typing import Any


class SaveROITemplateDialog(simpledialog.Dialog):
    """Dialog that gathers options for saving ROI/Arena templates."""

    def __init__(
        self,
        parent,
        *,
        default_name: str,
        has_arena: bool,
        has_rois: bool,
        allow_project: bool,
    ) -> None:
        """Initialize the save ROI template dialog.

        Args:
            parent: Parent widget.
            project_service: Service for accessing project data.
            current_arena: Current arena polygon definition.
            current_rois: List of current ROI configurations.
            existing_templates: List of existing template names.
        """
        self.result: dict[str, Any] | None = None
        self._has_arena = has_arena
        self._has_rois = has_rois
        self._allow_project = allow_project
        self._default_name = default_name
        super().__init__(parent, "Salvar template de zonas")

    def body(self, master):
        """Create dialog body with ROI template save options.

        Args:
            master: Parent widget for dialog body.

        Returns:
            The initial focus widget.
        """
        master.columnconfigure(1, weight=1)

        ttk.Label(master, text="Nome do template:").grid(
            row=0, column=0, sticky="w", padx=(5, 5), pady=(5, 2)
        )
        self.name_var = StringVar(value=self._default_name)
        self.name_entry = ttk.Entry(master, textvariable=self.name_var, width=40)
        self.name_entry.grid(row=0, column=1, sticky="ew", padx=(0, 5), pady=(5, 2))

        ttk.Label(master, text="Incluir no template:").grid(
            row=1, column=0, sticky="nw", padx=(5, 5), pady=(8, 2)
        )
        options_frame = ttk.Frame(master)
        options_frame.grid(row=1, column=1, sticky="w", padx=(0, 5), pady=(5, 2))

        self.save_arena_var = BooleanVar(value=self._has_arena)
        arena_check = ttk.Checkbutton(
            options_frame,
            text="Arena principal",
            variable=self.save_arena_var,
        )
        arena_check.grid(row=0, column=0, sticky="w")
        if not self._has_arena:
            self.save_arena_var.set(False)
            arena_check.state(["disabled"])

        self.save_rois_var = BooleanVar(value=self._has_rois)
        rois_check = ttk.Checkbutton(
            options_frame,
            text="Regiões de Interesse (ROIs)",
            variable=self.save_rois_var,
        )
        rois_check.grid(row=1, column=0, sticky="w", pady=(3, 0))
        if not self._has_rois:
            self.save_rois_var.set(False)
            rois_check.state(["disabled"])

        ttk.Label(master, text="Salvar em:").grid(
            row=2, column=0, sticky="nw", padx=(5, 5), pady=(10, 2)
        )
        location_frame = ttk.Frame(master)
        location_frame.grid(row=2, column=1, sticky="w", padx=(0, 5), pady=(5, 2))

        default_location = "project" if self._allow_project else "global"
        self.location_var = StringVar(value=default_location)
        self.location_var.trace_add("write", lambda *_: self._update_custom_state())

        self._project_radio = ttk.Radiobutton(
            location_frame,
            text="Projeto atual",
            value="project",
            variable=self.location_var,
        )
        self._project_radio.grid(row=0, column=0, sticky="w")
        if not self._allow_project:
            self._project_radio.state(["disabled"])

        ttk.Radiobutton(
            location_frame,
            text="Configurações globais",
            value="global",
            variable=self.location_var,
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))

        ttk.Radiobutton(
            location_frame,
            text="Local personalizado",
            value="custom",
            variable=self.location_var,
        ).grid(row=2, column=0, sticky="w", pady=(3, 0))

        custom_frame = ttk.Frame(location_frame)
        custom_frame.grid(row=3, column=0, sticky="we", pady=(6, 0))
        custom_frame.columnconfigure(0, weight=1)

        self.custom_path_var = StringVar(value="")
        self.custom_path_entry = ttk.Entry(
            custom_frame,
            textvariable=self.custom_path_var,
            width=36,
        )
        self.custom_path_entry.grid(row=0, column=0, sticky="ew")

        self.browse_button = ttk.Button(
            custom_frame,
            text="Procurar…",
            command=self._browse_custom_path,
            width=12,
        )
        self.browse_button.grid(row=0, column=1, padx=(6, 0))

        ttk.Label(
            master,
            text=(
                "Templates globais ficam disponíveis para todos os projetos. "
                "Use um local personalizado para compartilhar manualmente."
            ),
            wraplength=360,
            foreground="#4a4a4a",
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=(12, 0))

        self._update_custom_state()
        return self.name_entry

    def validate(self) -> bool:
        """Validate template name and configuration.

        Returns:
            True if validation passes, False otherwise.
        """
        name = (self.name_var.get() or "").strip()
        save_arena = bool(self.save_arena_var.get())
        save_rois = bool(self.save_rois_var.get())
        location = self.location_var.get()

        if not name:
            messagebox.showwarning("Nome obrigatório", "Informe o nome do template.")
            return False

        if not save_arena and not save_rois:
            messagebox.showwarning(
                "Seleção incompleta",
                "Escolha ao menos a arena ou as ROIs para salvar no template.",
            )
            return False

        if location == "custom":
            path = (self.custom_path_var.get() or "").strip()
            if not path:
                messagebox.showwarning(
                    "Local não definido",
                    "Selecione o arquivo onde o template será salvo.",
                )
                return False

        return True

    def apply(self) -> None:
        """Apply and save the ROI template with entered name and settings."""
        location = self.location_var.get()
        custom_path = (self.custom_path_var.get() or "").strip()
        if location == "custom" and custom_path:
            candidate = Path(custom_path)
            if candidate.suffix.lower() != ".json":
                custom_path = str(candidate.with_suffix(".json"))

        self.result = {
            "name": (self.name_var.get() or "").strip(),
            "save_arena": bool(self.save_arena_var.get()),
            "save_rois": bool(self.save_rois_var.get()),
            "save_location": location,
            "custom_path": custom_path if location == "custom" else None,
        }

    def _update_custom_state(self) -> None:
        is_custom = self.location_var.get() == "custom"
        state = "normal" if is_custom else "disabled"
        self.custom_path_entry.config(state=state)
        self.browse_button.config(state=state)

    def _browse_custom_path(self) -> None:
        initial_slug = self._suggest_filename()
        chosen = filedialog.asksaveasfilename(
            title="Salvar template de zonas",
            defaultextension=".json",
            filetypes=[("Template de zonas", "*.json"), ("Todos os arquivos", "*.*")],
            initialfile=f"{initial_slug}.json" if initial_slug else "",
        )
        if chosen:
            self.custom_path_var.set(chosen)
            self.location_var.set("custom")

    def _suggest_filename(self) -> str:
        candidate = (self.name_var.get() or "").strip()
        if not candidate:
            return "template"
        normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", candidate).strip("-")
        return normalized.lower() or "template"
