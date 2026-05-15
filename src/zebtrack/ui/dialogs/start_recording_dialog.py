"""
StartRecordingDialog.

Extracted from gui.py for better modularity.
"""

from collections.abc import Callable
from tkinter import (
    BooleanVar,
    Button,
    Checkbutton,
    Label,
    OptionMenu,
    StringVar,
    Toplevel,
    messagebox,
    simpledialog,
    ttk,
)
from typing import Any


class StartRecordingDialog(simpledialog.Dialog):
    """Dialog for initiating a new recording session.

    Allows users to select day, group, and subject for starting a new
    live camera recording session with smart state retention.

    Also exposes the camera saved in the project and lets the user override
    it for the current session — optionally persisting the choice as the
    new project default.
    """

    def __init__(
        self,
        parent,
        project_manager,
        camera_provider: Callable[[], list[dict[str, Any]]] | None = None,
    ):
        """Initialize the start recording dialog.

        Args:
            parent: Parent widget.
            project_manager: Project manager instance for accessing project data.
            camera_provider: Callable returning the current list of detected
                cameras (each dict has at least ``index``, ``friendly_name``,
                ``description``). Injected so the dialog stays decoupled from
                ``WizardService``. ``None`` disables the "Trocar câmera" button.
        """
        self.pm = project_manager
        self.camera_provider = camera_provider
        self.result: dict[str, Any] | None = None

        # Camera override state (None = use project default).
        self._camera_index_override: int | None = None
        self._camera_friendly_name_override: str | None = None
        self._persist_camera_var: BooleanVar | None = None
        self._camera_label: Label | None = None

        super().__init__(parent, "Iniciar Nova Sessão de Gravação")

    def body(self, master):
        """Create dialog body with recording session selection options.

        Args:
            master: Parent widget for dialog body.

        Returns:
            The initial focus widget.
        """
        # Get data from project manager
        days = self.pm.project_data.get("experiment_days", 1)
        groups = self.pm.project_data.get("groups", [])
        subjects = self.pm.project_data.get("subjects_per_group", 1)
        last_day, last_group = self.pm.get_last_session_details()

        # Create variables
        self.day_var = StringVar()
        self.group_var = StringVar()
        self.subject_var = StringVar()

        # Set initial values for smart state retention
        day_opts = [str(d) for d in range(1, days + 1)]
        if last_day and str(last_day) in day_opts:
            self.day_var.set(str(last_day))
        elif day_opts:
            self.day_var.set(day_opts[0])

        if last_group and last_group in groups:
            self.group_var.set(last_group)
        elif groups:
            self.group_var.set(groups[0])

        # --- Layout ---
        # Day Dropdown
        Label(master, text="Selecione o Dia:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        day_menu = OptionMenu(master, self.day_var, *day_opts)
        day_menu.grid(row=0, column=1, sticky="ew", padx=5)

        # Group Dropdown
        Label(master, text="Selecione o Grupo:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        group_menu = OptionMenu(master, self.group_var, *groups)
        group_menu.grid(row=1, column=1, sticky="ew", padx=5)

        # Subject Dropdown
        Label(master, text="Selecione a Cobaia:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        subject_opts = [str(s) for s in range(1, subjects + 1)]
        subject_menu = OptionMenu(master, self.subject_var, *subject_opts)
        subject_menu.grid(row=2, column=1, sticky="ew", padx=5)
        if subject_opts:
            self.subject_var.set(subject_opts[0])

        # Camera section (shows project default + optional per-session override).
        Label(master, text="Câmera:").grid(row=3, column=0, sticky="w", padx=5, pady=(10, 5))
        self._camera_label = Label(master, text=self._format_current_camera(), anchor="w")
        self._camera_label.grid(row=3, column=1, sticky="ew", padx=5, pady=(10, 5))

        if self.camera_provider is not None:
            Button(master, text="Trocar...", command=self._open_camera_chooser).grid(
                row=3, column=2, padx=5, pady=(10, 5)
            )

        return subject_menu  # Initial focus

    def _format_current_camera(self) -> str:
        """Render the camera label: override (if set) or project default."""
        if self._camera_index_override is not None:
            name = self._camera_friendly_name_override or ""
            suffix = f" — {name}" if name else ""
            return f"[Sessão] Índice {self._camera_index_override}{suffix}"

        saved_index = self.pm.project_data.get("camera_index", 0)
        saved_name = self.pm.project_data.get("camera_friendly_name", "") or ""
        if saved_name:
            return f"{saved_name} (índice {saved_index})"
        return f"Índice {saved_index}"

    def _open_camera_chooser(self) -> None:
        """Modal sub-dialog: detect + pick a camera, with optional persistence."""
        if self.camera_provider is None:
            return

        try:
            cameras = self.camera_provider()
        # except Exception justified: hardware probe — camera enumeration is I/O
        except Exception as exc:
            messagebox.showerror(
                "Falha na detecção",
                f"Não foi possível detectar câmeras:\n\n{exc}",
                parent=self,
            )
            return

        if not cameras:
            messagebox.showwarning(
                "Nenhuma câmera",
                "Nenhuma câmera foi detectada no sistema.",
                parent=self,
            )
            return

        chooser = Toplevel(self)
        chooser.title("Trocar câmera para esta sessão")
        chooser.transient(self)
        chooser.grab_set()

        Label(chooser, text="Selecione a câmera:").grid(
            row=0, column=0, sticky="w", padx=10, pady=(10, 0)
        )

        descriptions = [c.get("description", f"Câmera {c['index']}") for c in cameras]
        index_map = {desc: int(cameras[i]["index"]) for i, desc in enumerate(descriptions)}
        name_map = {
            desc: cameras[i].get("friendly_name", "") for i, desc in enumerate(descriptions)
        }

        selection_var = StringVar(value=descriptions[0])
        combo = ttk.Combobox(
            chooser,
            values=descriptions,
            textvariable=selection_var,
            state="readonly",
            width=60,
        )
        combo.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=5)

        persist_var = BooleanVar(value=False)
        Checkbutton(
            chooser,
            text="Salvar como câmera padrão deste projeto",
            variable=persist_var,
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=5)

        confirmed = {"ok": False}

        def _on_ok() -> None:
            confirmed["ok"] = True
            chooser.destroy()

        def _on_cancel() -> None:
            chooser.destroy()

        button_row = ttk.Frame(chooser)
        button_row.grid(row=3, column=0, columnspan=2, pady=(5, 10))
        Button(button_row, text="OK", command=_on_ok, width=10).pack(side="left", padx=5)
        Button(button_row, text="Cancelar", command=_on_cancel, width=10).pack(side="left", padx=5)

        chooser.wait_window()

        if not confirmed["ok"]:
            return

        chosen = selection_var.get()
        self._camera_index_override = index_map.get(chosen, 0)
        self._camera_friendly_name_override = name_map.get(chosen, "")
        self._persist_camera_var = persist_var
        if self._camera_label is not None:
            self._camera_label.config(text=self._format_current_camera())

    def validate(self):
        """Validate that day, group, and subject are selected.

        Returns:
            True if all selections are valid, False otherwise.
        """
        if not all([self.day_var.get(), self.group_var.get(), self.subject_var.get()]):
            messagebox.showerror("Erro", "Todos os campos são obrigatórios.")
            return False
        return True

    def apply(self):
        """Apply the selected recording session parameters to result."""
        persist = bool(self._persist_camera_var.get()) if self._persist_camera_var else False
        self.result = {
            "day": int(self.day_var.get()),
            "group": self.group_var.get(),
            "cobaia": self.subject_var.get(),
            "camera_index_override": self._camera_index_override,
            "camera_friendly_name_override": self._camera_friendly_name_override,
            "persist_camera": persist,
        }
