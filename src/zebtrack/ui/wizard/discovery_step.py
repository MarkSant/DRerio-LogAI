"""
Step 1: Discovery Dialog

Gathers initial context about project type, folder organization, and
existing parquet files before scanning any videos.
"""

from tkinter import (
    Frame,
    IntVar,
    Label,
    LabelFrame,
    Radiobutton,
    StringVar,
    font as tkfont,
)

from zebtrack.ui.wizard.base import WizardStep
from zebtrack.ui.wizard.enums import ProjectType, WizardStepID


class DiscoveryStep(WizardStep):
    """
    Discovery step - understand user's context.

    Questions:
        1. Project type: Experimental vs Exploratory
        2. Folder organization (if experimental)
        3. Existing parquet files

    Output:
        {
            "project_type": "experimental" | "exploratory",
            "has_folder_structure": bool,
            "folder_meaning": "experimental" | "organizational" | None,
            "has_parquets": bool,
            "parquet_import_scope": "zones" | "all" | None
        }
    """

    def __init__(self, parent, wizard_data: dict):
        """Initialize discovery step."""
        super().__init__(parent, wizard_data)
        self.step_id = WizardStepID.DISCOVERY

        # UI state variables
        self.project_type_var = StringVar(value=ProjectType.EXPERIMENTAL.value)
        self.folder_organization_var = IntVar(value=1)  # 1=experimental, 2=org, 3=none
        self.parquet_scope_var = IntVar(value=0)  # 0=none, 1=zones, 2=all

    def build_ui(self):
        """Build discovery step UI."""
        # Title
        title_font = tkfont.Font(size=14, weight="bold")
        title = Label(
            self, text="Bem-vindo ao Assistente de Criação de Projeto", font=title_font
        )
        title.pack(pady=(0, 20))

        subtitle = Label(
            self,
            text="Vamos começar entendendo o contexto do seu projeto.",
            fg="gray",
        )
        subtitle.pack(pady=(0, 20))

        # Question 1: Project Type
        q1_frame = LabelFrame(self, text="1. Tipo de Projeto", padx=15, pady=10)
        q1_frame.pack(fill="x", pady=(0, 15))

        Radiobutton(
            q1_frame,
            text="Experimental (com grupos, dias, sujeitos)",
            variable=self.project_type_var,
            value=ProjectType.EXPERIMENTAL.value,
            command=self._on_project_type_change,
        ).pack(anchor="w", pady=2)

        Radiobutton(
            q1_frame,
            text="Exploratório (análise livre sem design experimental)",
            variable=self.project_type_var,
            value=ProjectType.EXPLORATORY.value,
            command=self._on_project_type_change,
        ).pack(anchor="w", pady=2)

        # Question 2: Folder Organization (only for experimental)
        self.q2_frame = LabelFrame(
            self, text="2. Organização de Pastas", padx=15, pady=10
        )
        self.q2_frame.pack(fill="x", pady=(0, 15))

        Radiobutton(
            self.q2_frame,
            text="Sim - pastas representam estrutura experimental (ex: Grupo/Dia/)",
            variable=self.folder_organization_var,
            value=1,
        ).pack(anchor="w", pady=2)

        Radiobutton(
            self.q2_frame,
            text="Sim - mas apenas para organização (nomes arbitrários)",
            variable=self.folder_organization_var,
            value=2,
        ).pack(anchor="w", pady=2)

        Radiobutton(
            self.q2_frame,
            text="Não - todos os vídeos estão em um único diretório",
            variable=self.folder_organization_var,
            value=3,
        ).pack(anchor="w", pady=2)

        # Question 3: Existing Parquet Files
        q3_frame = LabelFrame(
            self, text="3. Arquivos Parquet Existentes", padx=15, pady=10
        )
        q3_frame.pack(fill="x", pady=(0, 15))

        Label(
            q3_frame,
            text="Você possui arquivos .parquet de análises anteriores?",
            fg="gray",
        ).pack(anchor="w", pady=(0, 8))

        Radiobutton(
            q3_frame,
            text="Sim - quero importar zonas (arena e ROIs)",
            variable=self.parquet_scope_var,
            value=1,
        ).pack(anchor="w", pady=2)

        Radiobutton(
            q3_frame,
            text="Sim - quero importar tudo (zonas + trajetória)",
            variable=self.parquet_scope_var,
            value=2,
        ).pack(anchor="w", pady=2)

        Radiobutton(
            q3_frame,
            text="Não - começar do zero",
            variable=self.parquet_scope_var,
            value=0,
        ).pack(anchor="w", pady=2)

        # Help text
        help_text = Label(
            self,
            text="Dica: Arquivos parquet de análises anteriores podem ser reutilizados "
            "para economizar tempo.",
            fg="blue",
            wraplength=500,
            justify="left",
        )
        help_text.pack(pady=(15, 0))

        # Update UI state
        self._on_project_type_change()

    def _on_project_type_change(self):
        """Handle project type change - show/hide folder organization question."""
        if self.project_type_var.get() == ProjectType.EXPERIMENTAL.value:
            # Show folder organization question for experimental
            self.q2_frame.pack(fill="x", pady=(0, 15), before=self.q2_frame.master.children[list(self.q2_frame.master.children.keys())[3]])
        else:
            # Hide for exploratory
            self.q2_frame.pack_forget()

    def validate(self) -> tuple[bool, str]:
        """
        Validate discovery step.

        All radio buttons have defaults, so always valid.

        Returns:
            tuple[bool, str]: (True, "")
        """
        return (True, "")

    def get_data(self) -> dict:
        """
        Extract discovery step data.

        Returns:
            dict: Discovery data with keys:
                - project_type
                - has_folder_structure (bool, only if experimental)
                - folder_meaning (str, only if experimental + has folders)
                - has_parquets (bool)
                - parquet_import_scope (str | None)
        """
        project_type = self.project_type_var.get()
        parquet_scope_value = self.parquet_scope_var.get()

        # Map parquet scope value to string
        parquet_scope_map = {
            0: None,  # No parquets
            1: "zones",  # Import zones only
            2: "all",  # Import everything
        }

        data = {
            "project_type": project_type,
            "has_parquets": parquet_scope_value > 0,
            "parquet_import_scope": parquet_scope_map[parquet_scope_value],
        }

        # Add folder organization info only for experimental projects
        if project_type == ProjectType.EXPERIMENTAL.value:
            folder_org_value = self.folder_organization_var.get()
            data["has_folder_structure"] = folder_org_value in [1, 2]

            if folder_org_value == 1:
                data["folder_meaning"] = "experimental"
            elif folder_org_value == 2:
                data["folder_meaning"] = "organizational"
            else:
                data["folder_meaning"] = None

        return data

    def set_data(self, data: dict):
        """
        Restore UI from data (for back navigation).

        Args:
            data: Previously collected discovery data
        """
        if "project_type" in data:
            self.project_type_var.set(data["project_type"])

        if "folder_meaning" in data:
            folder_meaning = data["folder_meaning"]
            if folder_meaning == "experimental":
                self.folder_organization_var.set(1)
            elif folder_meaning == "organizational":
                self.folder_organization_var.set(2)
            elif data.get("has_folder_structure") is False:
                self.folder_organization_var.set(3)

        if "parquet_import_scope" in data:
            scope = data["parquet_import_scope"]
            if scope == "zones":
                self.parquet_scope_var.set(1)
            elif scope == "all":
                self.parquet_scope_var.set(2)
            else:
                self.parquet_scope_var.set(0)

        # Update UI visibility
        self._on_project_type_change()
