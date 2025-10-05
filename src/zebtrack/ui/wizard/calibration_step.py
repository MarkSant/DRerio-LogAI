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
    font as tkfont,
)

from zebtrack.ui.wizard.base import WizardStep
from zebtrack.ui.wizard.enums import WizardStepID
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

    def build_ui(self):
        """Build calibration UI."""
        # Title
        title_font = tkfont.Font(size=14, weight="bold")
        title = Label(
            self, text="Calibração Física", font=title_font
        )
        title.pack(pady=(0, 10))

        subtitle = Label(
            self,
            text="Configure as dimensões físicas da arena para conversão de pixels para centímetros.",
            fg="gray",
            wraplength=500,
        )
        subtitle.pack(pady=(0, 20))

        # Video and animal configuration
        video_frame = LabelFrame(self, text="Configuração de Vídeos e Animais", padx=15, pady=10)
        video_frame.pack(fill="x", pady=(0, 15))

        # Number of aquariums (videos)
        aquarium_row = Frame(video_frame)
        aquarium_row.pack(fill="x", pady=5)

        Label(aquarium_row, text="Número de aquários (vídeos):", width=30, anchor="w").pack(side="left")
        aquarium_entry = Entry(aquarium_row, textvariable=self.num_aquariums_var, width=10)
        aquarium_entry.pack(side="left", padx=(5, 0))
        ToolTip(aquarium_entry, "Número de aquários/vídeos que serão analisados neste projeto.")

        # Animals per aquarium
        animals_row = Frame(video_frame)
        animals_row.pack(fill="x", pady=5)

        Label(animals_row, text="Animais por aquário:", width=30, anchor="w").pack(side="left")
        animals_entry = Entry(animals_row, textvariable=self.animals_per_aquarium_var, width=10)
        animals_entry.pack(side="left", padx=(5, 0))
        ToolTip(animals_entry, "Número de animais em cada aquário (vídeo). Use 1 para rastreamento individual.")

        # Physical dimensions
        dimensions_frame = LabelFrame(self, text="Dimensões Físicas do Aquário", padx=15, pady=10)
        dimensions_frame.pack(fill="x", pady=(0, 15))

        # Width
        width_row = Frame(dimensions_frame)
        width_row.pack(fill="x", pady=5)

        Label(width_row, text="Largura (cm):", width=30, anchor="w").pack(side="left")
        width_entry = Entry(width_row, textvariable=self.aquarium_width_var, width=10)
        width_entry.pack(side="left", padx=(5, 0))
        ToolTip(width_entry, "Largura física do aquário em centímetros.")

        # Height
        height_row = Frame(dimensions_frame)
        height_row.pack(fill="x", pady=5)

        Label(height_row, text="Altura (cm):", width=30, anchor="w").pack(side="left")
        height_entry = Entry(height_row, textvariable=self.aquarium_height_var, width=10)
        height_entry.pack(side="left", padx=(5, 0))
        ToolTip(height_entry, "Altura física do aquário em centímetros.")

        # Help text
        help_frame = LabelFrame(self, text="Sobre a Calibração", padx=15, pady=10)
        help_frame.pack(fill="x", pady=(15, 0))

        help_text = Label(
            help_frame,
            text=(
                "A calibração física permite converter coordenadas de pixels para centímetros.\n\n"
                "Isso é necessário para:\n"
                "• Calcular distâncias percorridas reais\n"
                "• Calcular velocidades em cm/s\n"
                "• Comparar resultados entre diferentes configurações de câmera\n\n"
                "💡 Dica: Se você não souber as dimensões exatas, pode usar valores padrão "
                "e ajustar depois nas configurações do projeto."
            ),
            fg="gray",
            wraplength=500,
            justify="left",
        )
        help_text.pack()

    def validate(self) -> tuple[bool, str]:
        """
        Validate calibration inputs.

        Returns:
            tuple[bool, str]: (True, "") if all inputs are valid,
                             (False, error_message) otherwise
        """
        try:
            num_aquariums = self.num_aquariums_var.get()
            animals_per_aquarium = self.animals_per_aquarium_var.get()
            width = self.aquarium_width_var.get()
            height = self.aquarium_height_var.get()

            if num_aquariums < 1:
                return (False, "O número de aquários deve ser pelo menos 1.")

            if animals_per_aquarium < 1:
                return (False, "O número de animais por aquário deve ser pelo menos 1.")

            if width <= 0:
                return (False, "A largura do aquário deve ser maior que zero.")

            if height <= 0:
                return (False, "A altura do aquário deve ser maior que zero.")

            return (True, "")

        except Exception as e:
            return (False, f"Erro ao validar dados: {str(e)}")

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

    def on_show(self):
        """Called when step becomes visible."""
        # Auto-detect number of aquariums from video count
        video_count = self.wizard_data.get("video_count", 0)
        if video_count > 0:
            # Only set if user hasn't modified it yet
            current_value = self.num_aquariums_var.get()
            if current_value == 1 and video_count > 1:
                self.num_aquariums_var.set(video_count)
