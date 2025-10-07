"""
Step 1: Discovery Dialog

Gathers initial context about project type, folder organization, and
existing parquet files before scanning any videos.
"""

from pathlib import Path

from tkinter import (
    Button,
    Canvas,
    Frame,
    IntVar,
    Label,
    LabelFrame,
    Radiobutton,
    StringVar,
    filedialog,
    messagebox,
)
from tkinter import (
    font as tkfont,
)
from tkinter.ttk import Scrollbar

from zebtrack.ui.wizard.base import WizardStep
from zebtrack.ui.wizard.enums import ProjectType, WizardStepID
from zebtrack.ui.wizard.tooltip import ToolTip
from zebtrack.ui.wizard.templates import TemplateManager, format_template_banner


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
        self.template_manager = TemplateManager()
        self.template_info_var = StringVar(value="")
        self.template_info_label = None

    def build_ui(self):
        """Build discovery step UI."""
        background_color = self.cget("background")

        self.scroll_canvas = Canvas(
            self, highlightthickness=0, bg=background_color, borderwidth=0
        )
        self.scrollbar = Scrollbar(
            self, orient="vertical", command=self.scroll_canvas.yview
        )
        self.scroll_canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scroll_canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.content_frame = Frame(self.scroll_canvas, bg=background_color)
        self.content_frame.bind(
            "<Configure>",
            lambda event: self.scroll_canvas.configure(
                scrollregion=self.scroll_canvas.bbox("all")
            ),
        )
        self._canvas_window = self.scroll_canvas.create_window(
            (0, 0), window=self.content_frame, anchor="nw"
        )

        self.scroll_canvas.bind("<Configure>", self._on_canvas_configure)
        self.scroll_canvas.bind("<Enter>", self._bind_mousewheel)
        self.scroll_canvas.bind("<Leave>", self._unbind_mousewheel)

        self.content_container = Frame(self.content_frame, bg=background_color)
        self.content_container.pack(fill="both", expand=True, padx=10, pady=10)

        # Title
        title_font = tkfont.Font(size=14, weight="bold")
        title = Label(
            self.content_container,
            text="Bem-vindo ao Assistente de Criação de Projeto",
            font=title_font,
        )
        title.pack(pady=(0, 20))

        subtitle = Label(
            self.content_container,
            text="Vamos começar entendendo o contexto do seu projeto.",
            fg="gray",
        )
        subtitle.pack(pady=(0, 20))

        actions_frame = Frame(self.content_container, bg=background_color)
        actions_frame.pack(fill="x", pady=(0, 10))

        Button(
            actions_frame,
            text="📂 Carregar Template...",
            command=self._load_template,
            width=24,
        ).pack(side="right")

        self.template_info_label = Label(
            self.content_container,
            textvariable=self.template_info_var,
            fg="#555555",
            bg=background_color,
            wraplength=520,
            justify="left",
        )
        self.template_info_label.pack_forget()

        # Question 1: Project Type
        q1_header = Frame(self.content_container)
        q1_header.pack(fill="x", pady=(0, 5))

        self.q1_frame = LabelFrame(
            self.content_container, text="1. Tipo de Projeto", padx=15, pady=10
        )
        self.q1_frame.pack(fill="x", pady=(0, 15))

        rb1 = Radiobutton(
            self.q1_frame,
            text="Experimental (vídeos pré-gravados com grupos, dias, sujeitos)",
            variable=self.project_type_var,
            value=ProjectType.EXPERIMENTAL.value,
            command=self._on_project_type_change,
        )
        rb1.pack(anchor="w", pady=2)
        experimental_tip = (
            "Projetos com design formal: grupos de tratamento, "
            "controles, séries temporais, etc."
        )
        ToolTip(rb1, experimental_tip)

        rb2 = Radiobutton(
            self.q1_frame,
            text="Exploratório (vídeos pré-gravados, análise livre)",
            variable=self.project_type_var,
            value=ProjectType.EXPLORATORY.value,
            command=self._on_project_type_change,
        )
        rb2.pack(anchor="w", pady=2)
        exploratory_tip = (
            "Para testes rápidos, validações, ou análises sem estrutura "
            "experimental definida."
        )
        ToolTip(rb2, exploratory_tip)

        rb_live = Radiobutton(
            self.q1_frame,
            text="Ao Vivo (gravar diretamente da câmera em tempo real)",
            variable=self.project_type_var,
            value=ProjectType.LIVE.value,
            command=self._on_project_type_change,
        )
        rb_live.pack(anchor="w", pady=2)
        live_tip = (
            "Gravar experimentos em tempo real usando câmera conectada ao "
            "computador."
        )
        ToolTip(rb_live, live_tip)

        # Question 2: Folder Organization (only for experimental)
        self.q2_frame = LabelFrame(
            self.content_container, text="2. Organização de Pastas", padx=15, pady=10
        )
        self.q2_frame.pack(fill="x", pady=(0, 15))

        rb3 = Radiobutton(
            self.q2_frame,
            text="Sim - pastas representam estrutura experimental (ex: Grupo/Dia/)",
            variable=self.folder_organization_var,
            value=1,
        )
        rb3.pack(anchor="w", pady=2)
        experimental_structure_tip = (
            "O assistente detectará automaticamente grupos, dias e sujeitos "
            "a partir da estrutura de pastas (ex: /Control/Day01/Subject01.mp4)."
        )
        ToolTip(rb3, experimental_structure_tip)

        rb4 = Radiobutton(
            self.q2_frame,
            text="Sim - mas apenas para organização (nomes arbitrários)",
            variable=self.folder_organization_var,
            value=2,
        )
        rb4.pack(anchor="w", pady=2)
        rb4_tip = "Pastas são usadas só para organização, sem significado experimental."
        ToolTip(rb4, rb4_tip)

        rb5 = Radiobutton(
            self.q2_frame,
            text="Não - todos os vídeos estão em um único diretório",
            variable=self.folder_organization_var,
            value=3,
        )
        rb5.pack(anchor="w", pady=2)
        rb5_tip = "Todos os vídeos estão numa pasta plana, sem subpastas."
        ToolTip(rb5, rb5_tip)

        # Question 3: Existing Parquet Files
        self.q3_frame = LabelFrame(
            self.content_container,
            text="3. Arquivos Parquet Existentes",
            padx=15,
            pady=10,
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
        ToolTip(
            rb6,
            (
                "Importar apenas a arena de arquivos *_arena.parquet. "
                "ROIs e trajetórias serão definidas/geradas novamente."
            ),
        )

        rb7 = Radiobutton(
            self.q3_frame,
            text="Sim - quero importar zonas (arena e ROIs)",
            variable=self.parquet_scope_var,
            value=2,
        )
        rb7.pack(anchor="w", pady=2)
        ToolTip(
            rb7,
            (
                "Importar arena e ROIs de arquivos *_arena.parquet e *_rois.parquet. "
                "Trajetórias serão geradas novamente."
            ),
        )

        rb8 = Radiobutton(
            self.q3_frame,
            text="Sim - quero importar tudo (zonas + trajetória)",
            variable=self.parquet_scope_var,
            value=3,
        )
        rb8.pack(anchor="w", pady=2)
        ToolTip(
            rb8,
            (
                "Importar arena, ROIs e trajetórias de arquivos *_arena.parquet, "
                "*_rois.parquet e *_trajectory.parquet. Economiza tempo evitando "
                "reprocessamento."
            ),
        )

        rb9 = Radiobutton(
            self.q3_frame,
            text="Não - começar do zero",
            variable=self.parquet_scope_var,
            value=0,
        )
        rb9.pack(anchor="w", pady=2)
        ToolTip(
            rb9,
            (
                "Processar tudo do início: desenhar arena, definir ROIs e gerar "
                "trajetórias."
            ),
        )

        # Glossary / Help text explaining technical terms
        glossary_frame = LabelFrame(
            self.content_container,
            text="O que significam esses termos?",
            padx=15,
            pady=10,
        )
        glossary_frame.pack(fill="x", pady=(15, 0))

        glossary_text = Label(
            glossary_frame,
            text=(
                "• Parquet: Formato de arquivo eficiente para armazenar dados\n\n"
                "• Arena: Área do aquário onde os animais se movem "
                "(polígono delimitador)\n\n"
                "• ROI (Region of Interest): Regiões específicas como 'Centro', "
                "'Borda', 'Zona de Escape'\n\n"
                "• Trajetória: Coordenadas frame-a-frame do movimento dos "
                "animais\n\n"
                "Importar esses dados de análises anteriores evita "
                "reprocessamento."
            ),
            fg="gray",
            justify="left",
            font=("TkDefaultFont", 9),
        )
        glossary_text.pack(anchor="w")

        # Update UI state
        self._on_project_type_change()

        self.after(0, self._initialize_scroll_area)
        self._update_template_banner()

    def _on_canvas_configure(self, event):
        self.scroll_canvas.itemconfig(self._canvas_window, width=event.width)

    def _bind_mousewheel(self, _event=None):
        self.scroll_canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.scroll_canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.scroll_canvas.bind_all("<Button-5>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event=None):
        self.scroll_canvas.unbind_all("<MouseWheel>")
        self.scroll_canvas.unbind_all("<Button-4>")
        self.scroll_canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event):
        if getattr(event, "delta", 0) != 0:
            delta = -1 * int(event.delta / 120)
            if delta != 0:
                self.scroll_canvas.yview_scroll(delta, "units")
        else:
            num = getattr(event, "num", None)
            if num == 4:
                self.scroll_canvas.yview_scroll(-1, "units")
            elif num == 5:
                self.scroll_canvas.yview_scroll(1, "units")

    def _initialize_scroll_area(self):
        if not hasattr(self, "scroll_canvas"):
            return

        self.update_idletasks()

        requested_width = self.content_container.winfo_reqwidth() + 20
        requested_height = self.content_container.winfo_reqheight() + 20

        screen_width = self.winfo_toplevel().winfo_screenwidth()
        screen_height = self.winfo_toplevel().winfo_screenheight()

        preferred_width = min(max(requested_width, 760), screen_width - 160)
        preferred_height = min(max(requested_height, 520), screen_height - 200)

        # Ensure sane fallbacks when running on very small displays
        preferred_width = max(preferred_width, 520)
        preferred_height = max(preferred_height, 420)

        self.scroll_canvas.configure(width=preferred_width, height=preferred_height)

        toplevel = self.winfo_toplevel()
        if toplevel is not None:
            toplevel.update_idletasks()

            min_width = min(preferred_width + 60, screen_width - 60)
            min_height = min(preferred_height + 160, screen_height - 60)

            toplevel.minsize(min_width, min_height)

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
                self.q2_frame.pack(
                    fill="x",
                    pady=(0, 15),
                    after=self.q1_frame,
                    before=self.q3_frame,
                )
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
        self._update_template_banner()

    def on_show(self):
        super().on_show()
        self._update_template_banner()
        if hasattr(self, "scroll_canvas"):
            self.scroll_canvas.update_idletasks()
            self.scroll_canvas.yview_moveto(0)

    def on_hide(self):
        super().on_hide()
        self._unbind_mousewheel()

    def _load_template(self):
        template_path = filedialog.askopenfilename(
            title="Carregar Template do Wizard",
            filetypes=[("Templates do Wizard", "*.json"), ("JSON", "*.json")],
            initialdir=str(self.template_manager.templates_dir),
        )

        if not template_path:
            return

        template = self.template_manager.load_template_from_path(template_path)

        if not template:
            messagebox.showerror(
                "Carregar Template",
                "Não foi possível carregar o template selecionado. Verifique o arquivo e tente novamente.",
                parent=self,
            )
            return

        self._apply_template_data(template, template_path)

        messagebox.showinfo(
            "Template Carregado",
            "Configurações carregadas. Revise cada etapa antes de continuar.",
            parent=self,
        )

    def _apply_template_data(self, template: dict, template_path: str):
        template_name = template.get("name") or Path(template_path).stem

        metadata = {
            "name": template_name,
            "path": template_path,
            "created_at": template.get("created_at"),
        }
        self.wizard_data["template_metadata"] = metadata

        mappings = {
            "project_type": template.get("project_type"),
            "num_aquariums": template.get("num_aquariums"),
            "animals_per_aquarium": template.get("animals_per_aquarium"),
            "aquarium_width_cm": template.get("aquarium_width_cm"),
            "aquarium_height_cm": template.get("aquarium_height_cm"),
            "parquet_import_scope": template.get("parquet_import_scope"),
            "detected_design": template.get("detected_design"),
            "custom_regex_patterns": template.get("custom_regex_patterns"),
        }

        for key, value in mappings.items():
            if value is not None:
                self.wizard_data[key] = value

        # Update local UI state
        parquet_scope = self.wizard_data.get("parquet_import_scope")
        self.wizard_data["has_parquets"] = bool(parquet_scope)

        discovery_data = {
            "project_type": self.wizard_data.get("project_type"),
            "parquet_import_scope": parquet_scope,
            "has_parquets": bool(parquet_scope),
        }

        self.set_data(discovery_data)
        self._update_template_banner()

    def _update_template_banner(self):
        banner_text = format_template_banner(self.wizard_data.get("template_metadata"))

        if banner_text:
            self.template_info_var.set(banner_text)
            if self.template_info_label and not self.template_info_label.winfo_ismapped():
                self.template_info_label.pack(fill="x", pady=(0, 15))
        else:
            self.template_info_var.set("")
            if self.template_info_label and self.template_info_label.winfo_ismapped():
                self.template_info_label.pack_forget()
