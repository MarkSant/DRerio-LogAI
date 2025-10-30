"""
Step 3: Physical Calibration Dialog

Allows user to configure physical dimensions of the arena for pixel-to-cm conversion.
Provides input fields for aquarium dimensions and number of animals.
"""

from tkinter import (
    DoubleVar,
    Entry,
    Frame,
    IntVar,
    Label,
    LabelFrame,
    StringVar,
)
from tkinter import (
    font as tkfont,
)

from zebtrack.core.wizard_service import WizardService
from zebtrack.ui.wizard.base import WizardStep
from zebtrack.ui.wizard.enums import WizardStepID
from zebtrack.ui.wizard.templates import format_template_banner
from zebtrack.ui.wizard.tooltip import ToolTip


class CalibrationStep(WizardStep):
    """
    Physical Calibration step - configure arena dimensions and animal count.

    Questions:
        - How many videos will be analyzed?
        - How many animals per video?
        - What are the physical dimensions of the arena?

    Output:
        {
            "num_aquariums": int,  # Number of videos to analyze
            "animals_per_aquarium": int,
            "aquarium_width_cm": float,
            "aquarium_height_cm": float,
        }
    """

    def __init__(self, parent, wizard_data: dict):
        """Initialize calibration step."""
        super().__init__(parent, wizard_data)
        self.step_id = WizardStepID.CALIBRATION

        # UI state
        self.num_aquariums_var = IntVar(value=1)
        self.animals_per_aquarium_var = IntVar(value=1)
        self.aquarium_width_var = DoubleVar(value=10.0)
        self.aquarium_height_var = DoubleVar(value=10.0)
        self.template_info_var = StringVar(value="")
        self.template_info_label = None

    def build_ui(self):
        """Build calibration UI."""
        # Title
        title_font = tkfont.Font(size=14, weight="bold")
        title = Label(self, text="Calibração Física", font=title_font)
        title.pack(pady=(0, 10))

        subtitle = Label(
            self,
            text=(
                "Configure as dimensões físicas da arena para conversão de pixels para centímetros."
            ),
            fg="gray",
            wraplength=500,
        )
        subtitle.pack(pady=(0, 20))

        self.template_info_label = Label(
            self,
            textvariable=self.template_info_var,
            fg="#555555",
            wraplength=500,
            justify="left",
        )
        self.template_info_label.pack_forget()

        # Video and animal configuration
        video_frame = LabelFrame(self, text="Configuração de Vídeos e Animais", padx=15, pady=10)
        video_frame.pack(fill="x", pady=(0, 15))

        # Number of aquariums (videos)
        aquarium_row = Frame(video_frame)
        aquarium_row.pack(fill="x", pady=5)

        Label(aquarium_row, text="Número de aquários (vídeos):", width=30, anchor="w").pack(
            side="left"
        )
        aquarium_entry = Entry(aquarium_row, textvariable=self.num_aquariums_var, width=10)
        aquarium_entry.pack(side="left", padx=(5, 0))
        ToolTip(
            aquarium_entry,
            (
                "🎬 Número de Aquários (Vídeos)\n\n"
                "Quantos vídeos independentes serão analisados neste projeto.\n\n"
                "• Cada aquário = 1 vídeo separado\n"
                "• Projeto LIVE: Tipicamente 1 (gravação única)\n"
                "• Projeto PRÉ-GRAVADO: Pode ser múltiplos vídeos\n\n"
                "Exemplos:\n"
                "  • 1 aquário: Um único experimento/gravação\n"
                "  • 6 aquários: 6 gravações diferentes (ex: 3 grupos × 2 dias)\n"
                "  • 24 aquários: Bateria completa de experimentos\n\n"
                "💡 Dica: Se não tiver certeza, comece com 1 e adicione mais vídeos depois."
            ),
        )

        # Animals per aquarium
        animals_row = Frame(video_frame)
        animals_row.pack(fill="x", pady=5)

        Label(animals_row, text="Animais por aquário:", width=30, anchor="w").pack(side="left")
        animals_entry = Entry(animals_row, textvariable=self.animals_per_aquarium_var, width=10)
        animals_entry.pack(side="left", padx=(5, 0))
        ToolTip(
            animals_entry,
            (
                "🐟 Animais por Aquário\n\n"
                "Quantos animais estarão presentes em CADA vídeo/aquário.\n\n"
                "Impacto na Análise:\n"
                "  • 1 animal: Rastreamento individual simplificado\n"
                "    → Ideal para: Estudos comportamentais individuais\n"
                "    → Método recomendado: Detecção (det)\n\n"
                "  • 2-5 animais: Rastreamento multi-animal moderado\n"
                "    → Ideal para: Interações sociais, comportamento de grupo pequeno\n"
                "    → Método recomendado: Segmentação (seg)\n\n"
                "  • 6+ animais: Rastreamento de cardume\n"
                "    → Ideal para: Dinâmica de cardume, comportamento coletivo\n"
                "    → Método recomendado: Segmentação (seg) com alta confiança\n\n"
                "⚠️ IMPORTANTE: Este valor deve ser o MESMO para todos os vídeos do projeto.\n"
                "Se você tem vídeos com números diferentes de animais, "
                "crie projetos separados.\n\n"
                "💡 Dica: Para múltiplos animais, prefira segmentação (seg) no "
                "passo de seleção de modelo."
            ),
        )

        # Physical dimensions
        dimensions_frame = LabelFrame(self, text="Dimensões Físicas do Aquário", padx=15, pady=10)
        dimensions_frame.pack(fill="x", pady=(0, 15))

        # Width
        width_row = Frame(dimensions_frame)
        width_row.pack(fill="x", pady=5)

        Label(width_row, text="Largura (cm):", width=30, anchor="w").pack(side="left")
        width_entry = Entry(width_row, textvariable=self.aquarium_width_var, width=10)
        width_entry.pack(side="left", padx=(5, 0))
        ToolTip(
            width_entry,
            (
                "📏 Largura do Aquário (eixo horizontal)\n\n"
                "Dimensão física REAL da arena visível no vídeo, medida em centímetros.\n\n"
                "Como Medir:\n"
                "  1. Identifique a área visível no vídeo (dentro do campo de visão)\n"
                "  2. Meça a largura HORIZONTAL dessa área com régua/trena\n"
                "  3. Meça em linha reta, do lado esquerdo ao direito\n\n"
                "Valores Típicos:\n"
                "  • Larvas (Petri dish): 5-10 cm\n"
                "  • Adultos (aquário pequeno): 15-30 cm\n"
                "  • Adultos (aquário médio): 30-50 cm\n"
                "  • Setup experimental grande: 50-100 cm\n\n"
                "Uso na Análise:\n"
                "  • Converte coordenadas de pixels → centímetros\n"
                "  • Permite calcular distâncias reais percorridas\n"
                "  • Essencial para velocidade (cm/s) e aceleração\n"
                "  • Necessário para comparar experimentos com câmeras diferentes\n\n"
                "💡 Dica: Se não souber exatamente, use uma estimativa. "
                "Você pode ajustar depois."
            ),
        )

        # Height
        height_row = Frame(dimensions_frame)
        height_row.pack(fill="x", pady=5)

        Label(height_row, text="Altura (cm):", width=30, anchor="w").pack(side="left")
        height_entry = Entry(height_row, textvariable=self.aquarium_height_var, width=10)
        height_entry.pack(side="left", padx=(5, 0))
        ToolTip(
            height_entry,
            (
                "📏 Altura do Aquário (eixo vertical)\n\n"
                "Dimensão física REAL da arena visível no vídeo, medida em centímetros.\n\n"
                "Como Medir:\n"
                "  1. Identifique a área visível no vídeo (dentro do campo de visão)\n"
                "  2. Meça a altura VERTICAL dessa área com régua/trena\n"
                "  3. Meça em linha reta, de cima para baixo\n\n"
                "Valores Típicos:\n"
                "  • Larvas (Petri dish): 5-10 cm\n"
                "  • Adultos (aquário pequeno): 10-20 cm\n"
                "  • Adultos (aquário médio): 20-40 cm\n"
                "  • Setup experimental grande: 40-80 cm\n\n"
                "Uso na Análise:\n"
                "  • Converte coordenadas de pixels → centímetros\n"
                "  • Permite calcular distâncias verticais reais\n"
                "  • Essencial para mapas de calor em escala real\n"
                "  • Necessário para métricas espaciais (tempo em zonas, etc.)\n\n"
                "⚠️ IMPORTANTE: Largura e altura devem corresponder à MESMA arena.\n"
                "Use as dimensões da área VISÍVEL no vídeo, não do aquário todo.\n\n"
                "💡 Dica: Para câmera superior (top-down), largura ≈ altura "
                "(campo de visão quadrado/retangular)."
            ),
        )

        # Help text
        help_frame = LabelFrame(self, text="Sobre a Calibração", padx=15, pady=10)
        help_frame.pack(fill="x", pady=(15, 0))

        help_text = Label(
            help_frame,
            text=(
                "A calibração física permite converter coordenadas de pixels para "
                "centímetros.\n\n"
                "Isso é necessário para:\n"
                "• Calcular distâncias percorridas reais\n"
                "• Calcular velocidades em cm/s\n"
                "• Comparar resultados entre diferentes configurações de câmera\n\n"
                "💡 Dica: Se você não souber as dimensões exatas, pode usar "
                "valores padrão e ajustar depois nas configurações do projeto."
            ),
            fg="gray",
            wraplength=500,
            justify="left",
        )
        help_text.pack()
        self._update_template_banner()

    def validate(self) -> tuple[bool, str]:
        """
        Validate calibration using WizardService.

        Returns:
            tuple[bool, str]: (True, "") if all inputs are valid,
                             (False, error_message) otherwise
        """
        try:
            # Get current data and use WizardService for validation
            data = self.get_data()
            is_valid, error_msg = WizardService.validate_basic_calibration(data)

            return (is_valid, error_msg)

        except Exception as e:
            return (False, f"Erro ao validar dados: {e!s}")

    def get_data(self) -> dict:
        """
        Extract calibration data.

        Returns:
            dict: Calibration data with keys:
                - num_aquariums (int)
                - animals_per_aquarium (int)
                - aquarium_width_cm (float)
                - aquarium_height_cm (float)
        """
        return {
            "num_aquariums": self.num_aquariums_var.get(),
            "animals_per_aquarium": self.animals_per_aquarium_var.get(),
            "aquarium_width_cm": self.aquarium_width_var.get(),
            "aquarium_height_cm": self.aquarium_height_var.get(),
        }

    def set_data(self, data: dict):
        """
        Restore UI from data (for back navigation).

        Args:
            data: Previously collected calibration data
        """
        if "num_aquariums" in data:
            self.num_aquariums_var.set(data["num_aquariums"])

        if "animals_per_aquarium" in data:
            self.animals_per_aquarium_var.set(data["animals_per_aquarium"])

        if "aquarium_width_cm" in data:
            self.aquarium_width_var.set(data["aquarium_width_cm"])

        if "aquarium_height_cm" in data:
            self.aquarium_height_var.set(data["aquarium_height_cm"])

        self._update_template_banner()

    def on_show(self):
        """Called when step becomes visible."""
        self._update_template_banner()

        if "num_aquariums" in self.wizard_data:
            self.num_aquariums_var.set(self.wizard_data["num_aquariums"])

        if "animals_per_aquarium" in self.wizard_data:
            self.animals_per_aquarium_var.set(self.wizard_data["animals_per_aquarium"])

        if "aquarium_width_cm" in self.wizard_data:
            self.aquarium_width_var.set(self.wizard_data["aquarium_width_cm"])

        if "aquarium_height_cm" in self.wizard_data:
            self.aquarium_height_var.set(self.wizard_data["aquarium_height_cm"])

        # Auto-detect number of aquariums from video count
        video_count = self.wizard_data.get("video_count", 0)
        if video_count > 0 and "num_aquariums" not in self.wizard_data:
            # Only set if user hasn't modified it yet
            current_value = self.num_aquariums_var.get()
            if current_value == 1 and video_count > 1:
                self.num_aquariums_var.set(video_count)

    def _update_template_banner(self):
        banner_text = format_template_banner(self.wizard_data.get("template_metadata"))

        if banner_text:
            self.template_info_var.set(banner_text)
            if self.template_info_label and not self.template_info_label.winfo_ismapped():
                self.template_info_label.pack(pady=(0, 10))
        else:
            self.template_info_var.set("")
            if self.template_info_label and self.template_info_label.winfo_ismapped():
                self.template_info_label.pack_forget()
