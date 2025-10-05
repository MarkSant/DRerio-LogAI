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
from zebtrack.ui.wizard.tooltip import ToolTip, create_help_label


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
        q1_header = Frame(self)
        q1_header.pack(fill="x", pady=(0, 5))

        self.q1_frame = LabelFrame(self, text="1. Tipo de Projeto", padx=15, pady=10)
        self.q1_frame.pack(fill="x", pady=(0, 15))

        rb1 = Radiobutton(
            self.q1_frame,
            text="Experimental (vídeos pré-gravados com grupos, dias, sujeitos)",
            variable=self.project_type_var,
            value=ProjectType.EXPERIMENTAL.value,
            command=self._on_project_type_change,
        )
        rb1.pack(anchor="w", pady=2)
        ToolTip(rb1, "Projetos com design formal: grupos de tratamento, controles, séries temporais, etc.")

        rb2 = Radiobutton(
            self.q1_frame,
            text="Exploratório (vídeos pré-gravados, análise livre)",
            variable=self.project_type_var,
            value=ProjectType.EXPLORATORY.value,
            command=self._on_project_type_change,
        )
        rb2.pack(anchor="w", pady=2)
        ToolTip(rb2, "Para testes rápidos, validações, ou análises sem estrutura experimental definida.")

        rb_live = Radiobutton(
            self.q1_frame,
            text="Ao Vivo (gravar diretamente da câmera em tempo real)",
            variable=self.project_type_var,
            value=ProjectType.LIVE.value,
            command=self._on_project_type_change,
        )
        rb_live.pack(anchor="w", pady=2)
        ToolTip(rb_live, "Gravar experimentos em tempo real usando câmera conectada ao computador.")

        # Question 2: Folder Organization (only for experimental)
        self.q2_frame = LabelFrame(
            self, text="2. Organização de Pastas", padx=15, pady=10
        )
        self.q2_frame.pack(fill="x", pady=(0, 15))

        rb3 = Radiobutton(
            self.q2_frame,
            text="Sim - pastas representam estrutura experimental (ex: Grupo/Dia/)",
            variable=self.folder_organization_var,
            value=1,
        )
        rb3.pack(anchor="w", pady=2)
        ToolTip(rb3, "O wizard detectará automaticamente grupos, dias e sujeitos a partir da estrutura de pastas (ex: /Control/Day01/Subject01.mp4)")

        rb4 = Radiobutton(
            self.q2_frame,
            text="Sim - mas apenas para organização (nomes arbitrários)",
            variable=self.folder_organization_var,
            value=2,
        )
        rb4.pack(anchor="w", pady=2)
        ToolTip(rb4, "Pastas são usadas só para organização, sem significado experimental.")

        rb5 = Radiobutton(
            self.q2_frame,
            text="Não - todos os vídeos estão em um único diretório",
            variable=self.folder_organization_var,
            value=3,
        )
        rb5.pack(anchor="w", pady=2)
        ToolTip(rb5, "Todos os vídeos estão numa pasta plana, sem subpastas.")

        # Question 3: Existing Parquet Files
        self.q3_frame = LabelFrame(
            self, text="3. Arquivos Parquet Existentes", padx=15, pady=10
        )
        self.q3_frame.pack(fill="x", pady=(0, 15))

        Label(
            self.q3_frame,
            text="Você possui arquivos .parquet de análises anteriores?",
            fg="gray",
        ).pack(anchor="w", pady=(0, 8))

        rb6 = Radiobutton(
            self.q3_frame,
            text="Sim - quero importar apenas arena",
            variable=self.parquet_scope_var,
            value=1,
        )
        rb6.pack(anchor="w", pady=2)
        ToolTip(rb6, "Importar apenas a arena de arquivos *_arena.parquet. ROIs e trajetórias serão definidas/geradas novamente.")

        rb7 = Radiobutton(
            self.q3_frame,
            text="Sim - quero importar zonas (arena e ROIs)",
            variable=self.parquet_scope_var,
            value=2,
        )
        rb7.pack(anchor="w", pady=2)
        ToolTip(rb7, "Importar arena e ROIs de arquivos *_arena.parquet e *_rois.parquet. Trajetórias serão geradas novamente.")

        rb8 = Radiobutton(
            self.q3_frame,
            text="Sim - quero importar tudo (zonas + trajetória)",
            variable=self.parquet_scope_var,
            value=3,
        )
        rb8.pack(anchor="w", pady=2)
        ToolTip(rb8, "Importar arena, ROIs e trajetórias de arquivos *_arena.parquet, *_rois.parquet e *_trajectory.parquet. Economiza tempo evitando reprocessamento.")

        rb9 = Radiobutton(
            self.q3_frame,
            text="Não - começar do zero",
            variable=self.parquet_scope_var,
            value=0,
        )
        rb9.pack(anchor="w", pady=2)
        ToolTip(rb9, "Processar tudo do início: desenhar arena, definir ROIs e gerar trajetórias.")

        # Glossary / Help text explaining technical terms
        glossary_frame = LabelFrame(self, text="O que significam esses termos?", padx=15, pady=10)
        glossary_frame.pack(fill="x", pady=(15, 0))

        glossary_text = Label(
            glossary_frame,
            text=(
                "• Parquet: Formato de arquivo eficiente para armazenar dados\n\n"
                "• Arena: Área do aquário onde os animais se movem (polígono delimitador)\n\n"
                "• ROI (Region of Interest): Regiões específicas como 'Centro', 'Borda', 'Zona de Escape'\n\n"
                "• Trajetória: Coordenadas frame-a-frame do movimento dos animais\n\n"
                "Importar esses dados de análises anteriores evita reprocessamento."
            ),
            fg="gray",
            justify="left",
            font=("TkDefaultFont", 9),
        )
        glossary_text.pack(anchor="w")

        # Update UI state
        self._on_project_type_change()

    def _on_project_type_change(self):
        """Handle project type change - show/hide questions based on project type."""
        project_type = self.project_type_var.get()

        if project_type == ProjectType.LIVE.value:
            # Live projects: hide both folder organization and parquets questions
            self.q2_frame.pack_forget()
            self.q3_frame.pack_forget()
        elif project_type == ProjectType.EXPERIMENTAL.value:
            # Experimental: show both questions
            if not self.q2_frame.winfo_ismapped():
                self.q2_frame.pack(fill="x", pady=(0, 15), after=self.q1_frame, before=self.q3_frame)
            if not self.q3_frame.winfo_ismapped():
                self.q3_frame.pack(fill="x", pady=(0, 15), after=self.q2_frame)
        else:  # Exploratory
            # Hide folder organization, show parquets
            self.q2_frame.pack_forget()
            if not self.q3_frame.winfo_ismapped():
                self.q3_frame.pack(fill="x", pady=(0, 15), after=self.q1_frame)

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
            1: "arena",  # Import arena only
            2: "zones",  # Import zones (arena + ROIs)
            3: "all",  # Import everything
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
            if scope == "arena":
                self.parquet_scope_var.set(1)
            elif scope == "zones":
                self.parquet_scope_var.set(2)
            elif scope == "all":
                self.parquet_scope_var.set(3)
            else:
                self.parquet_scope_var.set(0)

        # Update UI visibility
        self._on_project_type_change()
