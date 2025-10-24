"""
Experimental Design Step - Live Projects

Collects experimental structure for live recording projects:
- Number of groups
- Group names
- Number of days
- Number of subjects per group
"""

from __future__ import annotations

from tkinter import Entry, Frame, IntVar, Label, LabelFrame, Scale, StringVar

import structlog

from zebtrack.ui.wizard.base import WizardStep
from zebtrack.ui.wizard.enums import WizardStepID
from zebtrack.ui.wizard.tooltip import ToolTip

log = structlog.get_logger()


class ExperimentalDesignStep(WizardStep):
    """
    Experimental Design configuration step for live projects.

    Allows users to define experimental structure:
    - Duration in days
    - Number of experimental groups
    - Number of subjects per group
    - Custom names for each group
    """

    def __init__(self, parent, wizard_data: dict):
        """Initialize experimental design step."""
        super().__init__(parent, wizard_data)
        self.step_id = WizardStepID.EXPERIMENTAL_DESIGN

        # UI variables
        self.num_groups_var = IntVar(value=2)
        self.num_days_var = IntVar(value=1)
        self.subjects_per_group_var = IntVar(value=1)
        self.group_name_vars: list[StringVar] = []
        self.group_name_entries: list[Entry] = []

        # Container for dynamic group name entries
        self.group_names_container: Frame | None = None

    def build_ui(self):
        """Build experimental design step UI."""
        # Header
        title = Label(
            self,
            text="Configuração do Design Experimental",
            font=("TkDefaultFont", 13, "bold"),
        )
        title.pack(pady=(0, 10))

        subtitle = Label(
            self,
            text="Configure a estrutura do seu experimento ao vivo",
            fg="gray",
            font=("TkDefaultFont", 10),
        )
        subtitle.pack(pady=(0, 20))

        # 2-column layout
        config_container = Frame(self)
        config_container.pack(fill="both", expand=True, padx=10, pady=5)

        # Left column: Basic config
        left_col = LabelFrame(
            config_container,
            text="Configuração Básica",
            padx=15,
            pady=10,
        )
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 5))

        # Days
        Label(
            left_col,
            text="Duração do Experimento (dias):",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w", pady=(0, 2))

        days_frame = Frame(left_col)
        days_frame.pack(fill="x", pady=(0, 15))

        days_scale = Scale(
            days_frame,
            from_=1,
            to=30,
            variable=self.num_days_var,
            orient="horizontal",
            length=250,
        )
        days_scale.pack(side="left")

        days_value_label = Label(
            days_frame,
            textvariable=self.num_days_var,
            width=3,
            font=("TkDefaultFont", 10, "bold"),
        )
        days_value_label.pack(side="left", padx=5)

        ToolTip(
            days_frame,
            (
                "Duração do Experimento\n\n"
                "Quantos dias durará seu experimento completo.\n\n"
                "Exemplos:\n"
                "• 1 dia: Teste agudo\n"
                "• 7 dias: Tratamento de 1 semana\n"
                "• 21 dias: Tratamento crônico\n\n"
                "Isso afeta a organização dos arquivos de saída."
            ),
        )

        # Subjects per group
        Label(
            left_col,
            text="Animais por Grupo:",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w", pady=(0, 2))

        subjects_frame = Frame(left_col)
        subjects_frame.pack(fill="x", pady=(0, 15))

        subjects_scale = Scale(
            subjects_frame,
            from_=1,
            to=20,
            variable=self.subjects_per_group_var,
            orient="horizontal",
            length=250,
        )
        subjects_scale.pack(side="left")

        subjects_value_label = Label(
            subjects_frame,
            textvariable=self.subjects_per_group_var,
            width=3,
            font=("TkDefaultFont", 10, "bold"),
        )
        subjects_value_label.pack(side="left", padx=5)

        ToolTip(
            subjects_frame,
            (
                "Animais por Grupo\n\n"
                "Quantos animais em cada grupo experimental.\n\n"
                "Exemplo: 5 animais/grupo\n"
                "• Grupo Controle: 5 animais\n"
                "• Grupo Tratamento: 5 animais\n"
                "Total: 10 animais"
            ),
        )

        # Number of groups
        Label(
            left_col,
            text="Número de Grupos:",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w", pady=(0, 2))

        groups_frame = Frame(left_col)
        groups_frame.pack(fill="x", pady=(0, 15))

        groups_scale = Scale(
            groups_frame,
            from_=1,
            to=6,
            variable=self.num_groups_var,
            orient="horizontal",
            length=250,
            command=self._on_num_groups_change,
        )
        groups_scale.pack(side="left")

        groups_value_label = Label(
            groups_frame,
            textvariable=self.num_groups_var,
            width=3,
            font=("TkDefaultFont", 10, "bold"),
        )
        groups_value_label.pack(side="left", padx=5)

        ToolTip(
            groups_frame,
            (
                "Número de Grupos Experimentais\n\n"
                "Quantos grupos diferentes você terá.\n\n"
                "Exemplos:\n"
                "• 1 grupo: Apenas um tratamento\n"
                "• 2 grupos: Controle vs. Tratamento\n"
                "• 3+ grupos: Múltiplos tratamentos ou doses"
            ),
        )

        # Summary label
        self.summary_var = StringVar()
        summary_label = Label(
            left_col,
            textvariable=self.summary_var,
            fg="#2E7D32",
            font=("TkDefaultFont", 9, "bold"),
            wraplength=280,
            justify="left",
        )
        summary_label.pack(anchor="w", pady=(10, 0))

        self._update_summary()

        # Bind updates
        self.num_days_var.trace_add("write", lambda *_: self._update_summary())
        self.num_groups_var.trace_add("write", lambda *_: self._update_summary())
        self.subjects_per_group_var.trace_add("write", lambda *_: self._update_summary())

        # Right column: Group names
        right_col = LabelFrame(
            config_container,
            text="Nomes dos Grupos",
            padx=15,
            pady=10,
        )
        right_col.pack(side="left", fill="both", expand=True, padx=(5, 0))

        Label(
            right_col,
            text="Defina nomes descritivos para cada grupo:",
            fg="gray",
            font=("TkDefaultFont", 9),
        ).pack(anchor="w", pady=(0, 10))

        # Dynamic group name entries
        self.group_names_container = Frame(right_col)
        self.group_names_container.pack(fill="both", expand=True)

        self._rebuild_group_name_entries()

        # Info box
        info_frame = LabelFrame(
            self,
            text="ℹ️  Como isso será usado?",
            padx=15,
            pady=10,
        )
        info_frame.pack(fill="x", padx=10, pady=(15, 0))

        info_text = Label(
            info_frame,
            text=(
                "A estrutura configurada será usada para:\n\n"
                "• Organizar gravações por Dia → Grupo → Animal\n"
                "• Criar grid visual de progresso do experimento\n"
                "• Facilitar análise comparativa entre grupos\n\n"
                "Exemplo: 2 grupos × 5 dias × 3 animais = 30 gravações organizadas"
            ),
            justify="left",
            fg="#555",
            font=("TkDefaultFont", 9),
        )
        info_text.pack(anchor="w")

    def _on_num_groups_change(self, *_args):
        """Rebuild group name entries when number changes."""
        self._rebuild_group_name_entries()
        self._update_summary()

    def _rebuild_group_name_entries(self):
        """Dynamically create entry fields for group names."""
        if not self.group_names_container:
            return

        # Clear existing widgets
        for widget in self.group_names_container.winfo_children():
            widget.destroy()

        self.group_name_vars = []
        self.group_name_entries = []
        num_groups = self.num_groups_var.get()

        default_names = [
            "Controle",
            "Tratamento 1",
            "Tratamento 2",
            "Tratamento 3",
            "Grupo 5",
            "Grupo 6",
        ]

        for i in range(num_groups):
            frame = Frame(self.group_names_container)
            frame.pack(fill="x", pady=3)

            Label(
                frame,
                text=f"Grupo {i+1}:",
                width=10,
                anchor="w",
            ).pack(side="left")

            # Pre-fill with existing data or default
            existing_names = self.wizard_data.get("group_names", [])
            if i < len(existing_names):
                default_value = existing_names[i]
            elif i < len(default_names):
                default_value = default_names[i]
            else:
                default_value = f"Grupo {i+1}"

            var = StringVar(value=default_value)
            self.group_name_vars.append(var)

            entry = Entry(frame, textvariable=var, width=30)
            entry.pack(side="left", padx=5)
            self.group_name_entries.append(entry)

    def _update_summary(self):
        """Update summary label with experiment size calculation."""
        num_groups = self.num_groups_var.get()
        num_days = self.num_days_var.get()
        subjects = self.subjects_per_group_var.get()

        total_sessions = num_groups * num_days * subjects
        total_animals = num_groups * subjects

        self.summary_var.set(
            f"📊 Total: {total_sessions} gravações ({total_animals} animais × {num_days} dias)"
        )

    def validate(self) -> tuple[bool, str]:
        """Validate experimental design configuration."""
        num_groups = self.num_groups_var.get()

        # Check all group names are filled and trimmed
        for i, var in enumerate(self.group_name_vars[:num_groups]):
            name = var.get().strip()
            if not name:
                return (False, f"O nome do Grupo {i+1} não pode ficar vazio")

            # Update var with trimmed value
            var.set(name)

        # Check for duplicate names
        names = [var.get().strip() for var in self.group_name_vars[:num_groups]]
        if len(names) != len(set(names)):
            return (False, "Os nomes dos grupos devem ser únicos")

        return (True, "")

    def get_data(self) -> dict:
        """Extract experimental design data."""
        num_groups = self.num_groups_var.get()

        return {
            "experiment_days": self.num_days_var.get(),
            "num_groups": num_groups,
            "subjects_per_group": self.subjects_per_group_var.get(),
            "group_names": [
                var.get().strip() for var in self.group_name_vars[:num_groups]
            ],
        }

    def set_data(self, data: dict):
        """Restore UI from data (for back navigation)."""
        if "experiment_days" in data:
            self.num_days_var.set(data["experiment_days"])

        if "num_groups" in data:
            self.num_groups_var.set(data["num_groups"])
            # Rebuild will use data from wizard_data

        if "subjects_per_group" in data:
            self.subjects_per_group_var.set(data["subjects_per_group"])

        # Store in wizard_data for _rebuild_group_name_entries to use
        if "group_names" in data:
            self.wizard_data["group_names"] = data["group_names"]

        # Rebuild with new data
        self._rebuild_group_name_entries()
        self._update_summary()
