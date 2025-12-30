"""
Step 3: Physical Calibration Dialog.

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
from typing import TYPE_CHECKING

from zebtrack.core.wizard_service import WizardService
from zebtrack.ui.components.behavioral_config_widget import BehavioralConfigWidget
from zebtrack.ui.wizard.base import WizardStep
from zebtrack.ui.wizard.enums import WizardStepID
from zebtrack.ui.wizard.templates import format_template_banner
from zebtrack.ui.wizard.tooltip import ToolTip

if TYPE_CHECKING:
    from zebtrack.ui.event_bus import EventBus


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

    def __init__(self, parent, wizard_data: dict, event_bus: "EventBus | None" = None):
        """Initialize calibration step."""
        super().__init__(parent, wizard_data)
        self.step_id = WizardStepID.CALIBRATION
        self.event_bus = event_bus

        # UI state
        self.num_aquariums_var = IntVar(value=1)
        self.animals_per_aquarium_var = IntVar(value=1)
        self.aquarium_width_var = DoubleVar(value=10.0)
        self.aquarium_height_var = DoubleVar(value=10.0)
        # Processing intervals
        self.analysis_interval_var = IntVar(value=5)
        self.display_interval_var = IntVar(value=5)
        self.template_info_var = StringVar(value="")
        self.template_info_label = None

        # Behavioral analysis widget reference
        self.behavioral_config_widget: BehavioralConfigWidget | None = None

    def build_ui(self):
        """Build calibration UI - horizontal 2-column layout for better space usage."""
        # Title (full width)
        title_font = tkfont.Font(size=14, weight="bold")
        title = Label(self, text="Calibração Física", font=title_font)
        title.pack(pady=(0, 5))

        subtitle = Label(
            self,
            text=(
                "Configure as dimensões físicas da arena para conversão de pixels para centímetros."
            ),
            fg="gray",
            wraplength=700,
        )
        subtitle.pack(pady=(0, 10))

        self.template_info_label = Label(
            self,
            textvariable=self.template_info_var,
            fg="#555555",
            wraplength=700,
            justify="left",
        )
        self.template_info_label.pack_forget()

        # HORIZONTAL 2-COLUMN LAYOUT: Basic config (left) + Behavioral (right)
        content_frame = Frame(self)
        content_frame.pack(fill="both", expand=True, pady=(5, 0))
        content_frame.columnconfigure(0, weight=1, minsize=420)  # Left column (45%)
        content_frame.columnconfigure(1, weight=1, minsize=580)  # Right column (55%)
        content_frame.rowconfigure(0, weight=1)

        # LEFT COLUMN: Basic configuration sections (stacked vertically)
        left_panel = Frame(content_frame)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        # Video and animal configuration
        video_frame = LabelFrame(
            left_panel, text="Configuração de Vídeos e Animais", padx=10, pady=8
        )
        video_frame.pack(fill="x", pady=(0, 8))

        # Number of aquariums (videos)
        aquarium_row = Frame(video_frame)
        aquarium_row.pack(fill="x", pady=3)

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
        animals_row.pack(fill="x", pady=3)

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
        dimensions_frame = LabelFrame(
            left_panel, text="Dimensões Físicas do Aquário", padx=10, pady=8
        )
        dimensions_frame.pack(fill="x", pady=(0, 8))

        # Width
        width_row = Frame(dimensions_frame)
        width_row.pack(fill="x", pady=3)

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
        height_row.pack(fill="x", pady=3)

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

        # Advanced processing settings
        advanced_frame = LabelFrame(left_panel, text="⚙️ Configurações Avançadas", padx=10, pady=8)
        advanced_frame.pack(fill="x", pady=(0, 8))

        # Analysis interval
        analysis_row = Frame(advanced_frame)
        analysis_row.pack(fill="x", pady=3)

        Label(analysis_row, text="Intervalo de Análise (frames):", width=30, anchor="w").pack(
            side="left"
        )
        analysis_entry = Entry(analysis_row, textvariable=self.analysis_interval_var, width=10)
        analysis_entry.pack(side="left", padx=(5, 0))
        ToolTip(
            analysis_entry,
            (
                "🎬 Intervalo de Análise\n\n"
                "Processa 1 frame a cada N frames originais.\n\n"
                "• N=1: Analisa todos os frames (máxima precisão, mais lento)\n"
                "• N=10: Analisa 1 frame e pula 9 (mais rápido, ideal para vídeos longos)\n\n"
                "💡 Dica: Use 5 ou 10 para um bom equilíbrio entre velocidade e precisão."
            ),
        )

        # Display interval
        display_row = Frame(advanced_frame)
        display_row.pack(fill="x", pady=3)

        Label(display_row, text="Intervalo de Exibição (frames):", width=30, anchor="w").pack(
            side="left"
        )
        display_entry = Entry(display_row, textvariable=self.display_interval_var, width=10)
        display_entry.pack(side="left", padx=(5, 0))
        ToolTip(
            display_entry,
            (
                "🖥️ Intervalo de Exibição\n\n"
                "Atualiza a imagem na tela a cada N frames processados.\n\n"
                "• Valores altos (ex: 30) tornam a interface mais fluida "
                "durante o processamento em lote."
            ),
        )

        # RIGHT COLUMN: Behavioral analysis configuration (full height)
        behavioral_frame = LabelFrame(
            content_frame, text="🧠 Análise Comportamental", padx=10, pady=8
        )
        behavioral_frame.grid(row=0, column=1, sticky="nsew")

        # Determine defaults from global settings
        from zebtrack.settings import load_settings

        settings = load_settings()

        def_thig = settings.behavioral_analysis.default_thigmotaxis_distance_cm
        def_geo = settings.behavioral_analysis.default_geotaxis_distance_cm
        def_geo_zones = settings.behavioral_analysis.default_geotaxis_num_zones
        def_geo_btm = settings.behavioral_analysis.default_geotaxis_bottom_zones

        # Defaults for perspective and mode (added in Phase 9)
        def_perspective = "lateral"
        def_geotaxis_mode = "zones"
        if hasattr(settings.behavioral_analysis, "aquarium_perspective"):
            def_perspective = settings.behavioral_analysis.aquarium_perspective
        if hasattr(settings.behavioral_analysis, "geotaxis_mode"):
            def_geotaxis_mode = settings.behavioral_analysis.geotaxis_mode

        self.behavioral_config_widget = BehavioralConfigWidget(
            behavioral_frame,
            default_thigmotaxis_cm=def_thig,
            default_geotaxis_cm=def_geo,
            default_num_zones=def_geo_zones,
            default_bottom_zones=def_geo_btm,
            default_perspective=def_perspective,
            default_geotaxis_mode=def_geotaxis_mode,
            event_bus=self.event_bus,
        )
        self.behavioral_config_widget.pack(fill="x", expand=True)

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
                - behavioral_analysis (dict)
        """
        data = {
            "num_aquariums": self.num_aquariums_var.get(),
            "animals_per_aquarium": self.animals_per_aquarium_var.get(),
            "aquarium_width_cm": self.aquarium_width_var.get(),
            "aquarium_height_cm": self.aquarium_height_var.get(),
            "analysis_interval_frames": self.analysis_interval_var.get(),
            "display_interval_frames": self.display_interval_var.get(),
        }

        # Add behavioral analysis configuration
        if self.behavioral_config_widget:
            data["behavioral_analysis"] = self.behavioral_config_widget.get_values()

        return data

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

        if "analysis_interval_frames" in data:
            self.analysis_interval_var.set(data["analysis_interval_frames"])

        if "display_interval_frames" in data:
            self.display_interval_var.set(data["display_interval_frames"])

        # Restore behavioral analysis configuration
        if "behavioral_analysis" in data and self.behavioral_config_widget:
            self.behavioral_config_widget.set_values(data["behavioral_analysis"])

        self._update_template_banner()

    def on_show(self):
        """Execute actions when step becomes visible."""
        self._update_template_banner()

        if "num_aquariums" in self.wizard_data:
            self.num_aquariums_var.set(self.wizard_data["num_aquariums"])

        if "animals_per_aquarium" in self.wizard_data:
            self.animals_per_aquarium_var.set(self.wizard_data["animals_per_aquarium"])

        if "aquarium_width_cm" in self.wizard_data:
            self.aquarium_width_var.set(self.wizard_data["aquarium_width_cm"])

        if "aquarium_height_cm" in self.wizard_data:
            self.aquarium_height_var.set(self.wizard_data["aquarium_height_cm"])

        if "analysis_interval_frames" in self.wizard_data:
            self.analysis_interval_var.set(self.wizard_data["analysis_interval_frames"])

        if "display_interval_frames" in self.wizard_data:
            self.display_interval_var.set(self.wizard_data["display_interval_frames"])

        # Auto-detect number of aquariums from video count
        video_count = self.wizard_data.get("video_count", 0)
        if video_count > 0 and "num_aquariums" not in self.wizard_data:
            # Only set if user hasn't modified it yet
            current_value = self.num_aquariums_var.get()
            if current_value == 1 and video_count > 1:
                self.num_aquariums_var.set(video_count)

        # Restore behavioral analysis configuration
        if "behavioral_analysis" in self.wizard_data and self.behavioral_config_widget:
            self.behavioral_config_widget.set_values(self.wizard_data["behavioral_analysis"])

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
