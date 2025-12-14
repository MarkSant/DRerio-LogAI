"""
AquariumAssignmentDialog - Dialog for assigning groups to each aquarium.

Displayed when:
- Auto-detection finds 2 aquariums
- User draws the 2nd aquarium manually

Allows assigning group, subject_id, and day to each aquarium.
"""

import tkinter as tk
from tkinter import simpledialog, ttk
from typing import Callable

import structlog

from zebtrack.ui.wizard.models import AquariumConfig

log = structlog.get_logger()


class AquariumAssignmentDialog(simpledialog.Dialog):
    """Dialog for assigning experimental groups to each aquarium.

    Layout:
    ┌──────────────────────────────────────────────┐
    │  Configuração dos Aquários                   │
    ├──────────────────────────────────────────────┤
    │  ┌─ Aquário 1 (Esquerda) ─────────────────┐  │
    │  │ Grupo:    [Combobox: Controle     ▼]  │  │
    │  │ Sujeito:  [Entry: S01              ]  │  │
    │  │ Dia:      [Spinbox: 1        ▲▼   ]  │  │
    │  └───────────────────────────────────────┘  │
    │                                              │
    │  ┌─ Aquário 2 (Direita) ──────────────────┐  │
    │  │ Grupo:    [Combobox: Tratamento   ▼]  │  │
    │  │ Sujeito:  [Entry: S02              ]  │  │
    │  │ Dia:      [Spinbox: 1        ▲▼   ]  │  │
    │  └───────────────────────────────────────┘  │
    │                                              │
    │  ☑ Aplicar para todos os vídeos do batch    │
    │                                              │
    │           [Cancelar]  [Confirmar]           │
    └──────────────────────────────────────────────┘
    """

    def __init__(
        self,
        parent: tk.Toplevel | tk.Tk,
        available_groups: list[str],
        video_path: str | None = None,
        on_confirm: Callable[[list[AquariumConfig], bool], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
    ):
        """Initialize the aquarium assignment dialog.

        Args:
            parent: Parent widget.
            available_groups: List of available group names.
            video_path: Path to the video being configured.
            on_confirm: Callback with (configs, apply_to_all) when confirmed.
            on_cancel: Callback when cancelled.
        """
        self.available_groups = available_groups or ["Controle", "Tratamento"]
        self.video_path = video_path
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel
        self.result: list[AquariumConfig] | None = None
        self.apply_to_all: bool = False

        # Variables for form fields
        self._group_vars: list[tk.StringVar] = []
        self._subject_vars: list[tk.StringVar] = []
        self._day_vars: list[tk.IntVar] = []
        self._apply_all_var: tk.BooleanVar | None = None

        log.debug(
            "aquarium_assignment.dialog.init",
            video_path=video_path,
            groups=available_groups,
        )

        super().__init__(parent, "Configuração dos Aquários")

    def body(self, master: tk.Frame) -> tk.Widget | None:
        """Create dialog body with aquarium configuration forms.

        Args:
            master: Parent widget for dialog body.

        Returns:
            The initial focus widget.
        """
        master.config(padx=20, pady=15)

        # Header
        header_label = ttk.Label(
            master,
            text="Atribua grupos e identificadores para cada aquário",
            font=("Helvetica", 11, "bold"),
        )
        header_label.pack(pady=(0, 15))

        # Create config frames for each aquarium
        first_combo = None
        for aquarium_id in range(2):
            frame, combo = self._create_aquarium_frame(master, aquarium_id)
            frame.pack(fill=tk.X, pady=8)
            if first_combo is None:
                first_combo = combo

        # Apply to all checkbox
        self._apply_all_var = tk.BooleanVar(value=False)
        apply_all_check = ttk.Checkbutton(
            master,
            text="Aplicar para todos os vídeos do batch",
            variable=self._apply_all_var,
        )
        apply_all_check.pack(anchor=tk.W, pady=(15, 0))

        return first_combo  # Initial focus

    def _create_aquarium_frame(
        self, parent: tk.Frame, aquarium_id: int
    ) -> tuple[ttk.LabelFrame, ttk.Combobox]:
        """Create configuration frame for a single aquarium.

        Args:
            parent: Parent widget.
            aquarium_id: ID of the aquarium (0 or 1).

        Returns:
            Tuple of (frame, group_combobox).
        """
        position = "Esquerda" if aquarium_id == 0 else "Direita"
        frame = ttk.LabelFrame(
            parent, text=f"Aquário {aquarium_id + 1} ({position})", padding=10
        )

        # Group selection
        group_label = ttk.Label(frame, text="Grupo:")
        group_label.grid(row=0, column=0, sticky=tk.W, pady=3)

        group_var = tk.StringVar(value=self._get_default_group(aquarium_id))
        self._group_vars.append(group_var)

        group_combo = ttk.Combobox(
            frame,
            textvariable=group_var,
            values=self.available_groups,
            width=20,
            state="readonly" if self.available_groups else "normal",
        )
        group_combo.grid(row=0, column=1, sticky=tk.W, pady=3, padx=(10, 0))

        # Subject ID
        subject_label = ttk.Label(frame, text="Sujeito:")
        subject_label.grid(row=1, column=0, sticky=tk.W, pady=3)

        subject_var = tk.StringVar(value=f"S{aquarium_id + 1:02d}")
        self._subject_vars.append(subject_var)

        subject_entry = ttk.Entry(frame, textvariable=subject_var, width=22)
        subject_entry.grid(row=1, column=1, sticky=tk.W, pady=3, padx=(10, 0))

        # Day
        day_label = ttk.Label(frame, text="Dia:")
        day_label.grid(row=2, column=0, sticky=tk.W, pady=3)

        day_var = tk.IntVar(value=1)
        self._day_vars.append(day_var)

        day_spinbox = ttk.Spinbox(
            frame,
            from_=1,
            to=365,
            textvariable=day_var,
            width=20,
        )
        day_spinbox.grid(row=2, column=1, sticky=tk.W, pady=3, padx=(10, 0))

        return frame, group_combo

    def _get_default_group(self, aquarium_id: int) -> str:
        """Get default group for an aquarium.

        Args:
            aquarium_id: ID of the aquarium.

        Returns:
            Default group name.
        """
        if not self.available_groups:
            return "Controle" if aquarium_id == 0 else "Tratamento"

        # Try to assign different groups by default
        if len(self.available_groups) >= 2:
            return self.available_groups[aquarium_id % len(self.available_groups)]
        return self.available_groups[0]

    def buttonbox(self) -> None:
        """Create custom button box with Confirm and Cancel buttons."""
        box = ttk.Frame(self)
        box.pack(pady=(15, 0))

        confirm_btn = ttk.Button(
            box,
            text="Confirmar",
            width=12,
            command=self._on_confirm_click,
        )
        confirm_btn.pack(side=tk.LEFT, padx=5)

        cancel_btn = ttk.Button(
            box,
            text="Cancelar",
            width=12,
            command=self.cancel,
        )
        cancel_btn.pack(side=tk.LEFT, padx=5)

        self.bind("<Return>", lambda e: self._on_confirm_click())
        self.bind("<Escape>", lambda e: self.cancel())

    def _on_confirm_click(self) -> None:
        """Handle confirmation and validate inputs."""
        try:
            configs = self.get_configs()
            self.result = configs
            self.apply_to_all = self._apply_all_var.get() if self._apply_all_var else False

            log.info(
                "aquarium_assignment.dialog.confirmed",
                configs=[
                    {"id": c.aquarium_id, "group": c.group, "subject": c.subject_id}
                    for c in configs
                ],
                apply_to_all=self.apply_to_all,
            )

            if self._on_confirm:
                self._on_confirm(configs, self.apply_to_all)

            self.ok()

        except ValueError as e:
            log.warning("aquarium_assignment.dialog.validation_error", error=str(e))
            # Show error in dialog
            from tkinter import messagebox

            messagebox.showerror("Erro de Validação", str(e), parent=self)

    def cancel(self, event=None) -> None:
        """Handle dialog cancellation."""
        log.debug("aquarium_assignment.dialog.cancelled")
        self.result = None

        if self._on_cancel:
            self._on_cancel()

        super().cancel()

    def get_configs(self) -> list[AquariumConfig]:
        """Return the configured AquariumConfig objects.

        Returns:
            List of 2 AquariumConfig objects.

        Raises:
            ValueError: If validation fails.
        """
        configs = []

        for i in range(2):
            group = self._group_vars[i].get().strip()
            subject = self._subject_vars[i].get().strip()
            day = self._day_vars[i].get()

            if not group:
                raise ValueError(f"Grupo do Aquário {i + 1} não pode estar vazio")

            config = AquariumConfig(
                aquarium_id=i,
                group=group,
                subject_id=subject,
                day=day,
            )
            configs.append(config)

        return configs

    def get_result(self) -> tuple[list[AquariumConfig] | None, bool]:
        """Return the dialog result.

        Returns:
            Tuple of (configs, apply_to_all) or (None, False) if cancelled.
        """
        return self.result, self.apply_to_all
