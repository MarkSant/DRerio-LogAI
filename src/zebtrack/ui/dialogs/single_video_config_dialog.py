"""
SingleVideoConfigDialog

Extracted from gui.py for better modularity.
"""

from tkinter import (
    BooleanVar,
    IntVar,
    StringVar,
    filedialog,
    messagebox,
    simpledialog,
    ttk,
)
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from zebtrack.settings import Settings

log = structlog.get_logger()


class SingleVideoConfigDialog(simpledialog.Dialog):
    """A simplified dialog to get configuration for a single video analysis."""

    def __init__(self, parent, settings_obj: "Settings | None" = None):
        self.result = None
        self.settings = settings_obj
        super().__init__(parent, "Configuração de Análise de Vídeo Único")

    def body(self, master):
        # --- Tkinter Variables ---
        self.source_type_var = StringVar(value="video")  # "video" or "camera"
        self.video_path_var = StringVar(value="")
        self.camera_index_var = IntVar(value=0)
        self.camera_selection_var = StringVar(value="")  # For combobox display
        self.camera_index_map = {}  # Map camera description to index
        self.num_aquariums_var = StringVar(value="1")
        self.animals_per_aquarium_var = StringVar(value="1")
        self.aquarium_width_var = StringVar(value="10.0")
        self.aquarium_height_var = StringVar(value="10.0")

        # Pre-fill with defaults from settings or use hardcoded defaults
        sharp_turn_default = "180.0"
        freeze_thresh_default = "0.5"
        freeze_dur_default = "1.0"
        smoothing_window_default = "5"
        smoothing_polyorder_default = "2"
        aquarium_method_default = "seg"
        animal_method_default = "seg"

        if self.settings:
            if hasattr(self.settings, "video_processing"):
                sharp_turn_default = str(self.settings.video_processing.sharp_turn_threshold_deg_s)
                freeze_thresh_default = str(
                    self.settings.video_processing.freezing_velocity_threshold
                )
                freeze_dur_default = str(self.settings.video_processing.freezing_min_duration_s)
            if hasattr(self.settings, "trajectory_smoothing"):
                smoothing_window_default = str(self.settings.trajectory_smoothing.window_length)
                smoothing_polyorder_default = str(self.settings.trajectory_smoothing.polyorder)
            if hasattr(self.settings, "model_selection"):
                aquarium_method_default = self.settings.model_selection.aquarium_method
                animal_method_default = self.settings.model_selection.animal_method

        self.sharp_turn_var = StringVar(value=sharp_turn_default)
        self.freeze_thresh_var = StringVar(value=freeze_thresh_default)
        self.freeze_dur_var = StringVar(value=freeze_dur_default)
        self.smoothing_window_var = StringVar(value=smoothing_window_default)
        self.smoothing_polyorder_var = StringVar(value=smoothing_polyorder_default)

        # Frame interval configuration variables
        self.analysis_interval_var = StringVar(value="10")
        self.display_interval_var = StringVar(value="10")

        # Detection method configuration variables
        self.aquarium_method_var = StringVar(value=aquarium_method_default)
        self.animal_method_var = StringVar(value=animal_method_default)
        self.use_openvino_var = BooleanVar(value=True)  # OpenVINO enabled by default

        # --- Layout ---
        main_frame = ttk.Frame(master, padding=10)
        main_frame.pack(expand=True, fill="both")

        # Configure grid layout for main_frame
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(1, weight=1)

        # --- Source Selection (Full Width) ---
        source_frame = ttk.LabelFrame(main_frame, text="Seleção de Origem", padding=10)
        source_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        source_frame.columnconfigure(0, weight=1)

        # Source type selection
        type_container = ttk.Frame(source_frame)
        type_container.pack(fill="x", pady=(0, 10))

        ttk.Radiobutton(
            type_container,
            text="Arquivo de Vídeo",
            variable=self.source_type_var,
            value="video",
            command=self._on_source_type_changed,
        ).pack(side="left", padx=5)

        ttk.Radiobutton(
            type_container,
            text="Câmera ao Vivo",
            variable=self.source_type_var,
            value="camera",
            command=self._on_source_type_changed,
        ).pack(side="left", padx=5)

        # Video file selection
        self.video_select_container = ttk.Frame(source_frame)
        self.video_select_container.pack(fill="x")
        self.video_select_container.columnconfigure(0, weight=1)

        self.video_entry = ttk.Entry(
            self.video_select_container, textvariable=self.video_path_var, state="readonly"
        )
        self.video_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        self.browse_btn = ttk.Button(
            self.video_select_container, text="Procurar...", command=self._browse_video, width=12
        )
        self.browse_btn.grid(row=0, column=1, sticky="e")

        # Camera selection
        self.camera_select_container = ttk.Frame(source_frame)
        self.camera_select_container.columnconfigure(0, weight=0)
        self.camera_select_container.columnconfigure(1, weight=1)

        ttk.Label(self.camera_select_container, text="Câmera:").grid(
            row=0, column=0, sticky="w", padx=(0, 5)
        )

        self.camera_combo = ttk.Combobox(
            self.camera_select_container,
            textvariable=self.camera_selection_var,
            state="readonly",
            width=40,
        )
        self.camera_combo.grid(row=0, column=1, sticky="ew", padx=(0, 5))

        ttk.Button(
            self.camera_select_container,
            text="Detectar Câmeras",
            command=self._detect_cameras,
        ).grid(row=0, column=2, sticky="w", padx=5)

        # Create two-column layout
        left_column = ttk.Frame(main_frame)
        left_column.grid(row=1, column=0, sticky="nsew", padx=(0, 5))

        right_column = ttk.Frame(main_frame)
        right_column.grid(row=1, column=1, sticky="nsew", padx=(5, 0))

        # ===== LEFT COLUMN =====

        # --- Aquarium Dimensions ---
        dim_frame = ttk.LabelFrame(left_column, text="Calibração", padding=10)
        dim_frame.pack(fill="x", pady=(0, 5))
        dim_frame.columnconfigure(1, weight=1)

        ttk.Label(dim_frame, text="Número de Aquários:").grid(
            row=0, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(dim_frame, textvariable=self.num_aquariums_var, width=10).grid(
            row=0, column=1, sticky="w", padx=5
        )

        ttk.Label(dim_frame, text="Animais por Aquário:").grid(
            row=1, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(dim_frame, textvariable=self.animals_per_aquarium_var, width=10).grid(
            row=1, column=1, sticky="w", padx=5
        )

        ttk.Label(dim_frame, text="Largura do Aquário (cm):").grid(
            row=2, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(dim_frame, textvariable=self.aquarium_width_var, width=10).grid(
            row=2, column=1, sticky="w", padx=5
        )

        ttk.Label(dim_frame, text="Altura do Aquário (cm):").grid(
            row=3, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(dim_frame, textvariable=self.aquarium_height_var, width=10).grid(
            row=3, column=1, sticky="w", padx=5
        )

        # --- Behavior Analysis Parameters ---
        behavior_frame = ttk.LabelFrame(left_column, text="Parâmetros de Análise", padding=10)
        behavior_frame.pack(fill="x", pady=5)
        behavior_frame.columnconfigure(1, weight=1)

        ttk.Label(behavior_frame, text="Limiar de Curva Acentuada (graus/s):").grid(
            row=0, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(behavior_frame, textvariable=self.sharp_turn_var, width=10).grid(
            row=0, column=1, sticky="w", padx=5
        )

        ttk.Label(behavior_frame, text="Limiar de Congelamento (cm/s):").grid(
            row=1, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(behavior_frame, textvariable=self.freeze_thresh_var, width=10).grid(
            row=1, column=1, sticky="w", padx=5
        )

        ttk.Label(behavior_frame, text="Duração Mín. de Congelamento (s):").grid(
            row=2, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(behavior_frame, textvariable=self.freeze_dur_var, width=10).grid(
            row=2, column=1, sticky="w", padx=5
        )

        # ===== RIGHT COLUMN =====

        # --- Smoothing Parameters ---
        smoothing_frame = ttk.LabelFrame(right_column, text="Suavização de Trajetória", padding=10)
        smoothing_frame.pack(fill="x", pady=(0, 5))
        smoothing_frame.columnconfigure(1, weight=1)

        # Smoothing Window Length
        ttk.Label(smoothing_frame, text="Janela de Suavização (frames):").grid(
            row=0, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(smoothing_frame, textvariable=self.smoothing_window_var, width=10).grid(
            row=0, column=1, sticky="w", padx=5
        )
        ttk.Label(
            smoothing_frame,
            text=(
                "Janela de suavização: Número de frames usados para calcular a média "
                "móvel das posições, reduzindo ruído na trajetória."
            ),
            wraplength=280,
            font=("TkDefaultFont", 8),
            foreground="#555",
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=5, pady=(0, 5))

        # Polynomial Order
        ttk.Label(smoothing_frame, text="Ordem do Polinômio:").grid(
            row=2, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(smoothing_frame, textvariable=self.smoothing_polyorder_var, width=10).grid(
            row=2, column=1, sticky="w", padx=5
        )
        ttk.Label(
            smoothing_frame,
            text="Tipo de curva: 1=reta, 2=suave, 3=com dobra.",
            wraplength=280,
            font=("TkDefaultFont", 8),
            foreground="#555",
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=(0, 5))

        # Overall explanation
        ttk.Label(
            smoothing_frame,
            text=(
                "ℹ️ Remove tremidos sem apagar movimentos reais. "
                "Janela ímpar (3,5,7...) e ordem < janela. Padrão: 7 e 3."
            ),
            wraplength=280,
            font=("TkDefaultFont", 8),
            foreground="#2563eb",
            justify="left",
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=5, pady=(5, 0))

        # --- Frame Interval Settings ---
        interval_frame = ttk.LabelFrame(
            right_column, text="Intervalos de Processamento", padding=10
        )
        interval_frame.pack(fill="x", pady=5)
        interval_frame.columnconfigure(1, weight=1)

        ttk.Label(interval_frame, text="Intervalo de Análise (frames):").grid(
            row=0, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(interval_frame, textvariable=self.analysis_interval_var, width=10).grid(
            row=0, column=1, sticky="w", padx=5
        )

        ttk.Label(interval_frame, text="Intervalo de Exibição (frames):").grid(
            row=1, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(interval_frame, textvariable=self.display_interval_var, width=10).grid(
            row=1, column=1, sticky="w", padx=5
        )

        # --- Detection Method Settings ---
        method_frame = ttk.LabelFrame(right_column, text="Métodos de Detecção", padding=10)
        method_frame.pack(fill="x", pady=5)
        method_frame.columnconfigure(1, weight=1)

        ttk.Label(method_frame, text="Método para Aquário:").grid(
            row=0, column=0, sticky="w", padx=5, pady=2
        )
        aquarium_method_combo = ttk.Combobox(
            method_frame,
            textvariable=self.aquarium_method_var,
            values=["seg", "det"],
            state="readonly",
            width=8,
        )
        aquarium_method_combo.grid(row=0, column=1, sticky="w", padx=5)

        ttk.Label(method_frame, text="Método para Animais:").grid(
            row=1, column=0, sticky="w", padx=5, pady=2
        )
        animal_method_combo = ttk.Combobox(
            method_frame,
            textvariable=self.animal_method_var,
            values=["seg", "det"],
            state="readonly",
            width=8,
        )
        animal_method_combo.grid(row=1, column=1, sticky="w", padx=5)

        # Add tooltips/help text
        ttk.Label(
            method_frame,
            text="seg = Segmentação, det = Detecção",
            font=("TkDefaultFont", 8),
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=5, pady=(5, 0))

        # OpenVINO option
        openvino_check = ttk.Checkbutton(
            method_frame,
            text="Usar OpenVINO (acelera inferência em CPU)",
            variable=self.use_openvino_var,
        )
        openvino_check.grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=5)

        return main_frame

    def _on_source_type_changed(self):
        """Handle source type change between video and camera."""
        source_type = self.source_type_var.get()

        if source_type == "video":
            self.video_select_container.pack(fill="x")
            self.camera_select_container.pack_forget()
        else:  # camera
            self.video_select_container.pack_forget()
            self.camera_select_container.pack(fill="x")

    def _browse_video(self):
        """Open file dialog to select a video file."""

        video_path = filedialog.askopenfilename(
            parent=self,
            title="Selecione um Arquivo de Vídeo",
            filetypes=[("Arquivos de vídeo", "*.mp4 *.avi *.mov"), ("Todos os arquivos", "*.*")],
        )
        if video_path:
            self.video_path_var.set(video_path)

    def _detect_cameras(self):
        """Detect available cameras and update UI."""
        try:
            # Import wizard service to use camera detection
            from zebtrack.core.wizard_service import WizardService

            cameras = WizardService.detect_available_cameras()

            if not cameras:
                messagebox.showinfo(
                    "Câmeras",
                    (
                        "Nenhuma câmera detectada.\n\n"
                        "Verifique se a câmera está conectada e não está sendo "
                        "usada por outro aplicativo."
                    ),
                )
                self.camera_combo["values"] = []
                self.camera_index_map.clear()
                return

            # Build display list with camera names and map to indices
            camera_list = []
            self.camera_index_map.clear()

            for cam in cameras:
                description = cam.get("description", f"Câmera {cam['index']}")
                camera_list.append(description)
                self.camera_index_map[description] = cam["index"]

            # Update combobox
            self.camera_combo["values"] = camera_list

            # Auto-select first camera if none selected
            if not self.camera_selection_var.get() and camera_list:
                self.camera_selection_var.set(camera_list[0])

            messagebox.showinfo(
                "Câmeras Detectadas",
                f"{len(cameras)} câmera(s) detectada(s).\n\nSelecione a câmera desejada na lista."
            )

        except Exception as e:
            log.error("single_video_config.detect_cameras_error", error=str(e), exc_info=True)
            messagebox.showerror(
                "Erro",
                f"Erro ao detectar câmeras:\n{e}"
            )

    def validate(self):
        # Check if source was selected
        source_type = self.source_type_var.get()

        if source_type == "video":
            if not self.video_path_var.get():
                messagebox.showerror(
                    "Erro", "Por favor, selecione um arquivo de vídeo antes de continuar."
                )
                return False
        elif source_type == "camera":
            if not self.camera_selection_var.get():
                messagebox.showerror(
                    "Erro",
                    "Por favor, detecte e selecione uma câmera antes de continuar.\n\n"
                    "Clique em 'Detectar Câmeras' para ver as câmeras disponíveis."
                )
                return False

        try:
            num_aquariums = int(self.num_aquariums_var.get())
            animals_per_aquarium = int(self.animals_per_aquarium_var.get())
            float(self.aquarium_width_var.get())
            float(self.aquarium_height_var.get())
            float(self.sharp_turn_var.get())
            float(self.freeze_thresh_var.get())
            float(self.freeze_dur_var.get())
            smoothing_window = int(self.smoothing_window_var.get())
            smoothing_polyorder = int(self.smoothing_polyorder_var.get())
            analysis_interval = int(self.analysis_interval_var.get())
            display_interval = int(self.display_interval_var.get())
            if num_aquariums <= 0 or animals_per_aquarium <= 0:
                raise ValueError("Os valores devem ser positivos.")
            if analysis_interval <= 0 or display_interval <= 0:
                raise ValueError("Os intervalos devem ser números inteiros positivos.")
            if smoothing_window <= 0:
                raise ValueError("A janela de suavização deve ser positiva.")
            if smoothing_window % 2 == 0:
                raise ValueError("A janela de suavização deve ser um número ímpar.")
            if smoothing_polyorder < 1:
                raise ValueError("A ordem do polinômio deve ser pelo menos 1.")
            if smoothing_polyorder >= smoothing_window:
                raise ValueError("A ordem do polinômio deve ser menor que a janela de suavização.")
        except ValueError as e:
            messagebox.showerror(
                "Erro",
                f"Erro de validação: {e}\n\n"
                "Todos os campos de configuração devem ser números válidos e "
                "positivos.",
            )
            return False
        return True

    def apply(self):
        analysis_interval = int(self.analysis_interval_var.get())
        display_interval = int(self.display_interval_var.get())
        num_aquariums = int(self.num_aquariums_var.get())
        animals_per_aquarium = int(self.animals_per_aquarium_var.get())
        source_type = self.source_type_var.get()

        # Get camera index from mapping if camera source
        camera_index = None
        if source_type == "camera":
            camera_description = self.camera_selection_var.get()
            camera_index = self.camera_index_map.get(camera_description, 0)

        log.info(
            "single_video_dialog.apply",
            analysis_interval=analysis_interval,
            display_interval=display_interval,
            source_type=source_type,
            video_path=self.video_path_var.get() if source_type == "video" else None,
            camera_index=camera_index,
        )

        self.result = {
            "source_type": source_type,
            "video_path": self.video_path_var.get() if source_type == "video" else None,
            "camera_index": camera_index,
            "num_aquariums": num_aquariums,
            "animals_per_aquarium": animals_per_aquarium,
            "aquarium_width_cm": float(self.aquarium_width_var.get()),
            "aquarium_height_cm": float(self.aquarium_height_var.get()),
            "sharp_turn_threshold_deg_s": float(self.sharp_turn_var.get()),
            "freezing_velocity_threshold": float(self.freeze_thresh_var.get()),
            "freezing_min_duration_s": float(self.freeze_dur_var.get()),
            "smoothing_window_length": int(self.smoothing_window_var.get()),
            "smoothing_polyorder": int(self.smoothing_polyorder_var.get()),
            "analysis_interval_frames": analysis_interval,
            "display_interval_frames": display_interval,
            "aquarium_method": self.aquarium_method_var.get(),
            "animal_method": self.animal_method_var.get(),
            "use_openvino": self.use_openvino_var.get(),
            "use_single_subject_tracker": animals_per_aquarium == 1,
        }
