"""
SingleVideoConfigDialog.

Extracted from gui.py for better modularity.
"""

from tkinter import (
    BooleanVar,
    StringVar,
    filedialog,
    messagebox,
    simpledialog,
    ttk,
)
from typing import TYPE_CHECKING, Any, Literal, cast

import structlog

from zebtrack.ui.components.behavioral_config_widget import BehavioralConfigWidget
from zebtrack.ui.wizard.tooltip import create_help_label

if TYPE_CHECKING:
    from zebtrack.ui.event_bus_v2 import EventBusV2

if TYPE_CHECKING:
    from zebtrack.settings import Settings

log = structlog.get_logger()


class SingleVideoConfigDialog(simpledialog.Dialog):
    """A simplified dialog to get configuration for a single video analysis."""

    def __init__(
        self,
        parent,
        settings_obj: "Settings | None" = None,
        event_bus: "EventBusV2 | None" = None,
    ):
        """Initialize the single video configuration dialog.

        Args:
            parent: Parent widget.
            settings_obj: Settings object with configuration.
            event_bus: Optional event bus.
        """
        log.info("single_video_dialog.__init__")
        self.result: dict[str, Any] | None = None
        self.settings = settings_obj
        self.event_bus = event_bus
        super().__init__(parent, "Configuração de Análise de Vídeo Único")

    def body(self, master):
        """Create dialog body with single video configuration options.

        Args:
            master: Parent widget for dialog body.

        Returns:
            The initial focus widget.
        """
        # --- Tkinter Variables ---
        self.video_path_var = StringVar(value="")
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
        analysis_interval_default = "5"
        display_interval_default = "5"

        if self.settings:
            if hasattr(self.settings, "video_processing"):
                sharp_turn_default = str(self.settings.video_processing.sharp_turn_threshold_deg_s)
                freeze_thresh_default = str(
                    self.settings.video_processing.freezing_velocity_threshold
                )
                freeze_dur_default = str(self.settings.video_processing.freezing_min_duration_s)
                analysis_interval_default = str(self.settings.video_processing.processing_interval)
                display_interval_default = str(self.settings.video_processing.display_interval)

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
        self.analysis_interval_var = StringVar(value=analysis_interval_default)
        self.display_interval_var = StringVar(value=display_interval_default)

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

        # --- Video File Selection (Full Width) ---
        source_frame = ttk.LabelFrame(main_frame, text="Arquivo de Vídeo", padding=10)
        source_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        source_frame.columnconfigure(0, weight=1)

        # Video file selection
        video_container = ttk.Frame(source_frame)
        video_container.pack(fill="x")
        video_container.columnconfigure(0, weight=1)

        self.video_entry = ttk.Entry(
            video_container, textvariable=self.video_path_var, state="readonly"
        )
        self.video_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        self.browse_btn = ttk.Button(
            video_container, text="Procurar...", command=self._browse_video, width=12
        )
        self.browse_btn.grid(row=0, column=1, sticky="e")

        # Create two-column layout
        left_column = ttk.Frame(main_frame)
        left_column.grid(row=1, column=0, sticky="nsew", padx=(0, 5))

        right_column = ttk.Frame(main_frame)
        right_column.grid(row=1, column=1, sticky="nsew", padx=(5, 0))

        # ===== LEFT COLUMN =====

        # --- Aquarium Dimensions ---
        dim_frame = ttk.LabelFrame(left_column, text="Configuração Experimental", padding=10)
        dim_frame.pack(fill="x", pady=(0, 5))

        # Grid: Label | Help | Entry
        dim_frame.columnconfigure(1, weight=0)
        dim_frame.columnconfigure(2, weight=1)

        # Num Aquariums
        ttk.Label(dim_frame, text="Número de Aquários:").grid(
            row=0, column=0, sticky="w", padx=(5, 2), pady=2
        )
        create_help_label(
            dim_frame,
            "Número de Aquários\n\n"
            "Define se o vídeo contém 1 ou 2 tanques independentes.\n"
            "• 1: Análise padrão.\n"
            "• 2: Permite desenhar duas arenas e processá-las em conjunto.",
        ).grid(row=0, column=1, padx=2)
        ttk.Entry(dim_frame, textvariable=self.num_aquariums_var, width=8).grid(
            row=0, column=2, sticky="w", padx=5
        )

        # Animals per aquarium
        ttk.Label(dim_frame, text="Animais por Aquário:").grid(
            row=1, column=0, sticky="w", padx=(5, 2), pady=2
        )
        create_help_label(
            dim_frame,
            "Animais por Aquário\n\n"
            "Quantidade de peixes em cada tanque.\n"
            "• 1: Ativa o rastreador otimizado para sujeito único.\n"
            "• >1: Exige o modo de Segmentação (seg) para evitar trocas de ID.",
        ).grid(row=1, column=1, padx=2)
        ttk.Entry(dim_frame, textvariable=self.animals_per_aquarium_var, width=8).grid(
            row=1, column=2, sticky="w", padx=5
        )

        # Width
        ttk.Label(dim_frame, text="Largura Aquário (cm):").grid(
            row=2, column=0, sticky="w", padx=(5, 2), pady=2
        )
        create_help_label(
            dim_frame,
            "Largura Real (cm)\n\n"
            "Dimensão horizontal do tanque em centímetros.\n"
            "• Essencial para calcular velocidade em cm/s e distância total.",
        ).grid(row=2, column=1, padx=2)
        ttk.Entry(dim_frame, textvariable=self.aquarium_width_var, width=8).grid(
            row=2, column=2, sticky="w", padx=5
        )

        # Height
        ttk.Label(dim_frame, text="Altura Aquário (cm):").grid(
            row=3, column=0, sticky="w", padx=(5, 2), pady=2
        )
        create_help_label(
            dim_frame, "Altura Real (cm)\n\nDimensão vertical do tanque em centímetros."
        ).grid(row=3, column=1, padx=2)
        ttk.Entry(dim_frame, textvariable=self.aquarium_height_var, width=8).grid(
            row=3, column=2, sticky="w", padx=5
        )

        # --- Behavior Analysis Parameters ---
        behavior_frame = ttk.LabelFrame(left_column, text="Métricas de Comportamento", padding=10)
        behavior_frame.pack(fill="x", pady=5)

        # Grid: Label | Help | Entry
        behavior_frame.columnconfigure(1, weight=0)
        behavior_frame.columnconfigure(2, weight=1)

        # Sharp Turn
        ttk.Label(behavior_frame, text="Curva Acentuada (graus/s):").grid(
            row=0, column=0, sticky="w", padx=(5, 2), pady=2
        )
        create_help_label(
            behavior_frame,
            "Limiar de Curva Acentuada (Sharp Turn)\n\n"
            "Velocidade angular mínima para contar uma mudança de direção brusca.\n"
            "• Aumentar: Torna a detecção de curvas mais restritiva.\n"
            "• Padrão: 180.0 graus/s.",
        ).grid(row=0, column=1, padx=2)
        ttk.Entry(behavior_frame, textvariable=self.sharp_turn_var, width=8).grid(
            row=0, column=2, sticky="w", padx=5
        )

        # Freezing Velocity
        ttk.Label(behavior_frame, text="Congelamento (cm/s):").grid(
            row=1, column=0, sticky="w", padx=(5, 2), pady=2
        )
        create_help_label(
            behavior_frame,
            "Limiar de Congelamento (Velocidade)\n\n"
            "Velocidade abaixo da qual o peixe é considerado imóvel.\n"
            "• Diminuir: Se pequenos movimentos de respiração estiverem contando como nado.\n"
            "• Padrão: 0.5 cm/s.",
        ).grid(row=1, column=1, padx=2)
        ttk.Entry(behavior_frame, textvariable=self.freeze_thresh_var, width=8).grid(
            row=1, column=2, sticky="w", padx=5
        )

        # Freezing Duration
        ttk.Label(behavior_frame, text="Duração Mín. (s):").grid(
            row=2, column=0, sticky="w", padx=(5, 2), pady=2
        )
        create_help_label(
            behavior_frame,
            "Duração Mínima de Congelamento\n\n"
            "Tempo mínimo que o peixe deve ficar parado para registrar o evento.\n"
            "• Ex: 1.0s significa que paradas rápidas (<1s) serão ignoradas.",
        ).grid(row=2, column=1, padx=2)
        ttk.Entry(behavior_frame, textvariable=self.freeze_dur_var, width=8).grid(
            row=2, column=2, sticky="w", padx=5
        )

        # ===== RIGHT COLUMN =====

        # --- Smoothing Parameters ---
        smoothing_frame = ttk.LabelFrame(right_column, text="Suavização de Trajetória", padding=10)
        smoothing_frame.pack(fill="x", pady=(0, 5))

        # Grid: Label | Help | Entry
        smoothing_frame.columnconfigure(1, weight=0)
        smoothing_frame.columnconfigure(2, weight=1)

        # Smoothing Window Length
        ttk.Label(smoothing_frame, text="Janela Suavização:").grid(
            row=0, column=0, sticky="w", padx=(5, 2), pady=2
        )
        create_help_label(
            smoothing_frame,
            "Janela de Suavização (frames)\n\n"
            "Número de frames para média móvel. DEVE SER ÍMPAR.\n"
            "• Aumentar: Remove tremidos, mas suaviza demais os cantos.\n"
            "• Padrão: 5 (Express) ou 7 (Completo).",
        ).grid(row=0, column=1, padx=2)
        ttk.Entry(smoothing_frame, textvariable=self.smoothing_window_var, width=8).grid(
            row=0, column=2, sticky="w", padx=5
        )

        # Polynomial Order
        ttk.Label(smoothing_frame, text="Ordem Polinômio:").grid(
            row=1, column=0, sticky="w", padx=(5, 2), pady=2
        )
        create_help_label(
            smoothing_frame,
            "Ordem do Polinômio\n\n"
            "Complexidade do ajuste de curva. Deve ser MENOR que a janela.\n"
            "• Padrão: 2.",
        ).grid(row=1, column=1, padx=2)
        ttk.Entry(smoothing_frame, textvariable=self.smoothing_polyorder_var, width=8).grid(
            row=1, column=2, sticky="w", padx=5
        )

        # Overall explanation (Reduced text since we have help icons)
        ttk.Label(
            smoothing_frame,
            text="ℹ️ Remove tremidos sem apagar movimentos reais.",
            font=("TkDefaultFont", 8),
            foreground="#2563eb",
        ).grid(row=2, column=0, columnspan=3, sticky="w", padx=5, pady=(5, 0))

        # --- Frame Interval Settings ---
        interval_frame = ttk.LabelFrame(
            right_column, text="Otimização de Processamento", padding=10
        )
        interval_frame.pack(fill="x", pady=5)

        # Grid: Label | Help | Entry
        interval_frame.columnconfigure(1, weight=0)
        interval_frame.columnconfigure(2, weight=1)

        # Analysis Interval
        ttk.Label(interval_frame, text="Intervalo Análise:").grid(
            row=0, column=0, sticky="w", padx=(5, 2), pady=2
        )
        create_help_label(
            interval_frame,
            "Intervalo de Análise (frames)\n\n"
            "Processa 1 frame a cada N frames do vídeo.\n"
            "• 1: Analisa tudo (lento).\n"
            "• 10: Pula 9 frames (rápido).\n"
            "• Recomendado: 5 ou 10 conforme a velocidade do vídeo.",
        ).grid(row=0, column=1, padx=2)
        ttk.Entry(interval_frame, textvariable=self.analysis_interval_var, width=8).grid(
            row=0, column=2, sticky="w", padx=5
        )

        # Display Interval
        ttk.Label(interval_frame, text="Intervalo Exibição:").grid(
            row=1, column=0, sticky="w", padx=(5, 2), pady=2
        )
        create_help_label(
            interval_frame,
            "Intervalo de Exibição (frames)\n\n"
            "Frequência de atualização da imagem na tela durante o processo.\n"
            "• Use valores altos (ex: 30) para acelerar a análise economizando recursos de vídeo.",
        ).grid(row=1, column=1, padx=2)
        ttk.Entry(interval_frame, textvariable=self.display_interval_var, width=8).grid(
            row=1, column=2, sticky="w", padx=5
        )

        # --- Detection Method Settings ---
        method_frame = ttk.LabelFrame(right_column, text="Modelos de IA", padding=10)
        method_frame.pack(fill="x", pady=5)

        # Grid: Label | Help | Entry
        method_frame.columnconfigure(1, weight=0)
        method_frame.columnconfigure(2, weight=1)

        # Aquarium Method
        ttk.Label(method_frame, text="IA Aquário:").grid(
            row=0, column=0, sticky="w", padx=(5, 2), pady=2
        )
        create_help_label(
            method_frame,
            "Modelo para Detecção do Aquário\n\n"
            "• seg: Segmentação (mais preciso nos cantos).\n"
            "• det: Detecção por caixa (mais rápido).",
        ).grid(row=0, column=1, padx=2)
        aquarium_method_combo = ttk.Combobox(
            method_frame,
            textvariable=self.aquarium_method_var,
            values=["seg", "det"],
            state="readonly",
            width=8,
        )
        aquarium_method_combo.grid(row=0, column=2, sticky="w", padx=5)

        # Animal Method
        ttk.Label(method_frame, text="IA Peixe:").grid(
            row=1, column=0, sticky="w", padx=(5, 2), pady=2
        )
        create_help_label(
            method_frame,
            "Modelo para Rastreamento do Peixe\n\n"
            "• seg: Recomendado para múltiplos peixes (evita confusão).\n"
            "• det: Recomendado para 1 peixe (muito rápido).",
        ).grid(row=1, column=1, padx=2)
        animal_method_combo = ttk.Combobox(
            method_frame,
            textvariable=self.animal_method_var,
            values=["seg", "det"],
            state="readonly",
            width=8,
        )
        animal_method_combo.grid(row=1, column=2, sticky="w", padx=5)

        # OpenVINO option
        openvino_check = ttk.Checkbutton(
            method_frame,
            text="Usar aceleração OpenVINO (Intel)",
            variable=self.use_openvino_var,
        )
        openvino_check.grid(row=2, column=0, columnspan=3, sticky="w", padx=5, pady=(10, 0))

        # --- Behavioral Analysis Widget (New) ---
        # Add it to the left column, below the behavior metrics frame
        behavioral_frame_container = ttk.Frame(left_column)
        behavioral_frame_container.pack(fill="x", pady=(5, 0))

        # Determine defaults
        def_thig = 1.5
        def_geo = 1.5
        def_geo_zones = 3
        def_geo_btm = 1
        def_perspective = "lateral"
        def_geotaxis_mode = "zones"

        if self.settings and hasattr(self.settings, "behavioral_analysis"):
            def_thig = self.settings.behavioral_analysis.default_thigmotaxis_distance_cm
            def_geo = self.settings.behavioral_analysis.default_geotaxis_distance_cm
            def_geo_zones = self.settings.behavioral_analysis.default_geotaxis_num_zones
            def_geo_btm = self.settings.behavioral_analysis.default_geotaxis_bottom_zones
            # Added in Phase 9
            if hasattr(self.settings.behavioral_analysis, "aquarium_perspective"):
                def_perspective = self.settings.behavioral_analysis.aquarium_perspective
            if hasattr(self.settings.behavioral_analysis, "geotaxis_mode"):
                def_geotaxis_mode = self.settings.behavioral_analysis.geotaxis_mode

        self.behavioral_config_widget = BehavioralConfigWidget(
            behavioral_frame_container,
            default_thigmotaxis_cm=def_thig,
            default_geotaxis_cm=def_geo,
            default_num_zones=def_geo_zones,
            default_bottom_zones=def_geo_btm,
            default_perspective=def_perspective,
            default_geotaxis_mode=def_geotaxis_mode,
            event_bus=self.event_bus,
        )
        self.behavioral_config_widget.pack(fill="x", expand=True)

        return main_frame

    def _browse_video(self):
        """Open file dialog to select a video file."""
        video_path = filedialog.askopenfilename(
            parent=self,
            title="Selecione um Arquivo de Vídeo",
            filetypes=[("Arquivos de vídeo", "*.mp4 *.avi *.mov"), ("Todos os arquivos", "*.*")],
        )
        if video_path:
            self.video_path_var.set(video_path)

    def validate(self):
        """Validate video file and configuration settings.

        Returns:
            True if configuration is valid, False otherwise.
        """
        log.info("single_video_dialog.validate.START")

        # Check if video file was selected
        if not self.video_path_var.get():
            messagebox.showerror(
                "Erro", "Por favor, selecione um arquivo de vídeo antes de continuar."
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

            # Validate behavioral config
            if self.behavioral_config_widget:
                is_valid, errors = self.behavioral_config_widget.validate()
                if not is_valid:
                    raise ValueError("\n".join(errors))

        except ValueError as e:
            messagebox.showerror(
                "Erro",
                f"Erro de validação: {e}\n\n"
                "Verifique se todos os campos estão preenchidos corretamente.",
            )
            return False

        log.info("single_video_dialog.validate.SUCCESS")
        return True

    def apply(self):
        """Apply the single video configuration to result dictionary and settings."""
        log.info("single_video_dialog.apply.START")

        analysis_interval = int(self.analysis_interval_var.get())
        display_interval = int(self.display_interval_var.get())
        num_aquariums = int(self.num_aquariums_var.get())
        animals_per_aquarium = int(self.animals_per_aquarium_var.get())

        behavioral_config = {}
        if self.behavioral_config_widget:
            behavioral_config = self.behavioral_config_widget.get_values()

        # Update the shared settings object to ensure consistency in other UI tabs
        if self.settings:
            try:
                if hasattr(self.settings, "video_processing"):
                    self.settings.video_processing.processing_interval = analysis_interval
                    self.settings.video_processing.display_interval = display_interval
                    self.settings.video_processing.sharp_turn_threshold_deg_s = float(
                        self.sharp_turn_var.get()
                    )
                    self.settings.video_processing.freezing_velocity_threshold = float(
                        self.freeze_thresh_var.get()
                    )
                    self.settings.video_processing.freezing_min_duration_s = float(
                        self.freeze_dur_var.get()
                    )

                if hasattr(self.settings, "trajectory_smoothing"):
                    self.settings.trajectory_smoothing.window_length = int(
                        self.smoothing_window_var.get()
                    )
                    self.settings.trajectory_smoothing.polyorder = int(
                        self.smoothing_polyorder_var.get()
                    )

                if hasattr(self.settings, "model_selection"):
                    self.settings.model_selection.aquarium_method = cast(
                        Literal["seg", "det"], self.aquarium_method_var.get()
                    )
                    self.settings.model_selection.animal_method = cast(
                        Literal["seg", "det"], self.animal_method_var.get()
                    )
                    self.settings.model_selection.use_openvino = self.use_openvino_var.get()

                if hasattr(self.settings, "analysis_config"):
                    self.settings.analysis_config.num_aquariums = num_aquariums

                if hasattr(self.settings, "tracking"):
                    self.settings.tracking.use_single_subject_tracker = animals_per_aquarium == 1

                if hasattr(self.settings, "behavioral_analysis"):
                    # Phase 9: Persist behavioral settings
                    # Keys from BehavioralConfigWidget.get_values() use short names;
                    # map to the "default_" prefixed settings field names.
                    if "aquarium_perspective" in behavioral_config:
                        self.settings.behavioral_analysis.aquarium_perspective = behavioral_config[
                            "aquarium_perspective"
                        ]
                    if "geotaxis_mode" in behavioral_config:
                        self.settings.behavioral_analysis.geotaxis_mode = behavioral_config[
                            "geotaxis_mode"
                        ]
                    num_zones = behavioral_config.get(
                        "geotaxis_num_zones",
                        behavioral_config.get("default_geotaxis_num_zones"),
                    )
                    if num_zones is not None:
                        self.settings.behavioral_analysis.default_geotaxis_num_zones = num_zones
                    bottom_zones = behavioral_config.get(
                        "geotaxis_bottom_zones",
                        behavioral_config.get("default_geotaxis_bottom_zones"),
                    )
                    if bottom_zones is not None:
                        self.settings.behavioral_analysis.default_geotaxis_bottom_zones = (
                            bottom_zones
                        )
                    thigmo = behavioral_config.get(
                        "thigmotaxis_distance_cm",
                        behavioral_config.get("default_thigmotaxis_distance_cm"),
                    )
                    if thigmo is not None:
                        self.settings.behavioral_analysis.default_thigmotaxis_distance_cm = thigmo
                    geo_dist = behavioral_config.get(
                        "geotaxis_distance_cm",
                        behavioral_config.get("default_geotaxis_distance_cm"),
                    )
                    if geo_dist is not None:
                        self.settings.behavioral_analysis.default_geotaxis_distance_cm = geo_dist

                log.info("single_video_dialog.apply.settings_updated")
            except Exception as e:
                log.warning("single_video_dialog.apply.settings_update_failed", error=str(e))

        log.info(
            "single_video_dialog.apply.values_parsed",
            analysis_interval=analysis_interval,
            display_interval=display_interval,
            video_path=self.video_path_var.get(),
        )

        self.result = {
            "video_path": self.video_path_var.get(),
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
            "behavioral_analysis": behavioral_config,
        }

        log.info(
            "single_video_dialog.apply.END",
            result_set=bool(self.result),
            video_path=self.result.get("video_path") if self.result else None,
        )
