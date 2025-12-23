"""
Dialog for configuring and starting live camera analysis sessions.

This dialog allows users to:
- Select a camera device
- Set analysis duration
- Configure analysis parameters
- Start immediate analysis from camera feed
"""

from tkinter import (
    BooleanVar,
    Button,
    DoubleVar,
    Frame,
    IntVar,
    Label,
    Spinbox,
    StringVar,
    messagebox,
    ttk,
)
from tkinter.simpledialog import Dialog
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from zebtrack.settings import Settings

from zebtrack.core.wizard_service import WizardService
from zebtrack.ui.wizard.tooltip import ToolTip, create_help_label

log = structlog.get_logger()


class LiveAnalysisDialog(Dialog):
    """
    Dialog for configuring live camera analysis sessions.

    Provides an interface to:
    - Detect and select available cameras
    - Set analysis duration and intervals
    - Configure recording options
    - Configure calibration parameters
    - Configure behavioral analysis parameters
    - Configure trajectory smoothing
    - Configure detection methods
    - Start immediate analysis

    Result:
        dict with keys:
            - camera_index: int
            - duration_s: float
            - analysis_interval_frames: int
            - display_interval_frames: int
            - record_video: bool
            - experiment_id: str
            - num_aquariums: int
            - animals_per_aquarium: int
            - aquarium_width_cm: float
            - aquarium_height_cm: float
            - sharp_turn_threshold_deg_s: float
            - freezing_velocity_threshold: float
            - freezing_min_duration_s: float
            - smoothing_window_length: int
            - smoothing_polyorder: int
            - aquarium_method: str
            - animal_method: str
            - use_openvino: bool
            - use_single_subject_tracker: bool
        or None if cancelled
    """

    def __init__(self, parent, settings_obj: "Settings | None" = None):
        """
        Initialize live analysis dialog.

        Args:
            parent: Parent Tkinter widget
            settings_obj: Settings instance for defaults
        """
        self.settings = settings_obj
        self.result = None

        # UI state
        self.camera_selection_var = StringVar(value="")
        self.camera_index_map = {}
        self.duration_var = DoubleVar(
            value=settings_obj.live_analysis.default_duration_s if settings_obj else 300.0
        )
        self.analysis_interval_var = IntVar(value=10)
        self.display_interval_var = IntVar(value=10)
        self.record_video_var = BooleanVar(value=True)
        self.experiment_id_var = StringVar(value="")

        # Calibration parameters
        self.num_aquariums_var = IntVar(value=1)
        self.animals_per_aquarium_var = IntVar(value=1)
        self.aquarium_width_var = DoubleVar(value=10.0)
        self.aquarium_height_var = DoubleVar(value=10.0)

        # Behavior analysis parameters
        sharp_turn_default = 180.0
        freeze_thresh_default = 0.5
        freeze_dur_default = 1.0
        if settings_obj and hasattr(settings_obj, "video_processing"):
            sharp_turn_default = settings_obj.video_processing.sharp_turn_threshold_deg_s
            freeze_thresh_default = settings_obj.video_processing.freezing_velocity_threshold
            freeze_dur_default = settings_obj.video_processing.freezing_min_duration_s

        self.sharp_turn_var = DoubleVar(value=sharp_turn_default)
        self.freeze_thresh_var = DoubleVar(value=freeze_thresh_default)
        self.freeze_dur_var = DoubleVar(value=freeze_dur_default)

        # Smoothing parameters
        smoothing_window_default = 5
        smoothing_polyorder_default = 2
        if settings_obj and hasattr(settings_obj, "trajectory_smoothing"):
            smoothing_window_default = settings_obj.trajectory_smoothing.window_length
            smoothing_polyorder_default = settings_obj.trajectory_smoothing.polyorder

        self.smoothing_window_var = IntVar(value=smoothing_window_default)
        self.smoothing_polyorder_var = IntVar(value=smoothing_polyorder_default)

        # Detection method parameters
        aquarium_method_default = "seg"
        animal_method_default = "seg"
        use_openvino_default = True
        if settings_obj and hasattr(settings_obj, "model_selection"):
            aquarium_method_default = settings_obj.model_selection.aquarium_method
            animal_method_default = settings_obj.model_selection.animal_method
            use_openvino_default = settings_obj.model_selection.use_openvino

        self.aquarium_method_var = StringVar(value=aquarium_method_default)
        self.animal_method_var = StringVar(value=animal_method_default)
        self.use_openvino_var = BooleanVar(value=use_openvino_default)

        super().__init__(parent, title="Analisar Câmera ao Vivo")

        # Set application icon
        from zebtrack.ui.icon_utils import set_window_icon

        set_window_icon(self)

    def body(self, master):
        """Create dialog body."""
        # Main container with padding
        container = ttk.Frame(master, padding=10)
        container.pack(fill="both", expand=True)

        # Title
        title = Label(
            container,
            text="Análise de Câmera ao Vivo",
            font=("TkDefaultFont", 12, "bold"),
        )
        title.pack(pady=(0, 5))

        subtitle = Label(
            container,
            text="Configure e inicie uma sessão de análise em tempo real.",
            fg="gray",
        )
        subtitle.pack(pady=(0, 15))

        # --- Camera Selection (Top) ---
        camera_frame = ttk.LabelFrame(container, text="Seleção de Câmera", padding=10)
        camera_frame.pack(fill="x", pady=(0, 10))

        # Grid for camera selection
        camera_frame.columnconfigure(1, weight=1)

        ttk.Label(camera_frame, text="Dispositivo:").grid(row=0, column=0, padx=5, sticky="w")

        self.camera_combo = ttk.Combobox(
            camera_frame,
            textvariable=self.camera_selection_var,
            state="readonly",
        )
        self.camera_combo.grid(row=0, column=1, padx=5, sticky="ew")
        ToolTip(self.camera_combo, "Selecione a câmera para análise ao vivo.")

        ttk.Button(camera_frame, text="🔍 Detectar", command=self._detect_cameras, width=10).grid(
            row=0, column=2, padx=5
        )

        self.camera_status_label = Label(camera_frame, text="", fg="gray")
        self.camera_status_label.grid(row=1, column=1, sticky="w", padx=5)

        # --- Configuration Grid (2 Columns) ---
        config_container = ttk.Frame(container)
        config_container.pack(fill="both", expand=True)
        config_container.columnconfigure(0, weight=1)
        config_container.columnconfigure(1, weight=1)

        # Left Column: Timing & Processing
        left_col = ttk.Frame(config_container)
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        # Duration Settings
        duration_frame = ttk.LabelFrame(left_col, text="Tempo e Processamento", padding=10)
        duration_frame.pack(fill="x", pady=(0, 10))

        # Grid: Label | Help | Entry
        duration_frame.columnconfigure(1, weight=0)
        duration_frame.columnconfigure(2, weight=1)

        # Duration
        ttk.Label(duration_frame, text="Duração (s):").grid(
            row=0, column=0, padx=(5, 2), pady=2, sticky="w"
        )
        create_help_label(
            duration_frame,
            "Tempo de Gravação/Análise\n\n"
            "Define quanto tempo a sessão ao vivo irá durar em segundos.\n"
            "• 60s = 1 minuto.\n"
            "• 300s = 5 minutos."
        ).grid(row=0, column=1, padx=2)
        duration_spin = Spinbox(
            duration_frame,
            from_=10,
            to=7200,
            textvariable=self.duration_var,
            width=8,
        )
        duration_spin.grid(row=0, column=2, padx=5, pady=2, sticky="w")

        # Quick buttons for duration
        quick_btns = ttk.Frame(duration_frame)
        quick_btns.grid(row=0, column=3, padx=5, pady=2)
        ttk.Button(quick_btns, text="1m", width=4, command=lambda: self.duration_var.set(60)).pack(
            side="left", padx=1
        )
        ttk.Button(quick_btns, text="5m", width=4, command=lambda: self.duration_var.set(300)).pack(
            side="left", padx=1
        )

        # Analysis Interval
        ttk.Label(duration_frame, text="Intervalo Análise:").grid(
            row=1, column=0, padx=(5, 2), pady=2, sticky="w"
        )
        create_help_label(
            duration_frame,
            "Intervalo de Análise (frames)\n\n"
            "Processa 1 frame a cada N frames da câmera.\n"
            "• Valores baixos exigem um computador potente.\n"
            "• Recomendado para Live: 1 ou 2."
        ).grid(row=1, column=1, padx=2)
        analysis_spin = Spinbox(
            duration_frame,
            from_=1,
            to=60,
            textvariable=self.analysis_interval_var,
            width=8,
        )
        analysis_spin.grid(row=1, column=2, padx=5, pady=2, sticky="w")

        # Display Interval
        ttk.Label(duration_frame, text="Intervalo Exibição:").grid(
            row=2, column=0, padx=(5, 2), pady=2, sticky="w"
        )
        create_help_label(
            duration_frame,
            "Intervalo de Exibição (frames)\n\n"
            "Frequência de atualização do vídeo na tela.\n"
            "• Aumentar este valor ajuda se a interface estiver lenta."
        ).grid(row=2, column=1, padx=2)
        display_spin = Spinbox(
            duration_frame,
            from_=1,
            to=60,
            textvariable=self.display_interval_var,
            width=8,
        )
        display_spin.grid(row=2, column=2, padx=5, pady=2, sticky="w")

        # Right Column: Options & ID
        right_col = ttk.Frame(config_container)
        right_col.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        # Options Settings
        options_frame = ttk.LabelFrame(right_col, text="Opções da Sessão", padding=10)
        options_frame.pack(fill="x", pady=(0, 10))

        # Grid: Label | Help | Entry
        options_frame.columnconfigure(1, weight=0)
        options_frame.columnconfigure(2, weight=1)

        # Experiment ID
        ttk.Label(options_frame, text="ID Experimento:").grid(
            row=0, column=0, padx=(5, 2), pady=5, sticky="w"
        )
        create_help_label(
            options_frame,
            "Identificador do Experimento\n\n"
            "Nome usado para organizar os arquivos de saída.\n"
            "• Se deixado em branco, o sistema gerará um nome com a data e hora."
        ).grid(row=0, column=1, padx=2)
        id_entry = ttk.Entry(options_frame, textvariable=self.experiment_id_var)
        id_entry.grid(row=0, column=2, padx=5, pady=5, sticky="ew")

        # Checkboxes
        ttk.Checkbutton(
            options_frame,
            text="Gravar vídeo com overlay",
            variable=self.record_video_var,
        ).grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky="w")

        # OpenVINO Option
        ttk.Checkbutton(
            options_frame,
            text="Usar aceleração OpenVINO",
            variable=self.use_openvino_var,
        ).grid(row=2, column=0, columnspan=3, padx=5, pady=5, sticky="w")

        # --- Calibration & Detection (Bottom, simplified) ---
        adv_frame = ttk.LabelFrame(container, text="Parâmetros Avançados de IA e Setup", padding=10)
        adv_frame.pack(fill="x", pady=(0, 10))

        # Grid: Label | Help | Entry | Label | Help | Entry
        adv_frame.columnconfigure(1, weight=0)
        adv_frame.columnconfigure(2, weight=1)
        adv_frame.columnconfigure(4, weight=0)
        adv_frame.columnconfigure(5, weight=1)

        # Row 0: Model Methods
        ttk.Label(adv_frame, text="IA Aquário:").grid(row=0, column=0, padx=(5, 2), sticky="w")
        create_help_label(
            adv_frame,
            "Modelo de Segmentação ou Detecção do tanque.\n"
            "• seg: Mais lento, mas delimita melhor as bordas.\n"
            "• det: Muito rápido."
        ).grid(row=0, column=1, padx=2)
        ttk.Combobox(
            adv_frame,
            textvariable=self.aquarium_method_var,
            values=["seg", "det"],
            width=8,
            state="readonly",
        ).grid(row=0, column=2, padx=5, sticky="w")

        ttk.Label(adv_frame, text="IA Peixe:").grid(row=0, column=3, padx=(15, 2), sticky="w")
        create_help_label(
            adv_frame,
            "Modelo para o peixe.\n"
            "• Use 'seg' se tiver mais de um peixe por aquário."
        ).grid(row=0, column=4, padx=2)
        ttk.Combobox(
            adv_frame,
            textvariable=self.animal_method_var,
            values=["seg", "det"],
            width=8,
            state="readonly",
        ).grid(row=0, column=5, padx=5, sticky="w")

        # Row 1: Physical setup
        ttk.Label(adv_frame, text="Num. Aquários:").grid(
            row=1, column=0, padx=(5, 2), pady=5, sticky="w"
        )
        create_help_label(
            adv_frame,
            "Quantidade de tanques no campo de visão (1 ou 2)."
        ).grid(row=1, column=1, padx=2)
        Spinbox(adv_frame, from_=1, to=10, textvariable=self.num_aquariums_var, width=8).grid(
            row=1, column=2, padx=5, sticky="w"
        )

        ttk.Label(adv_frame, text="Animais/Aquário:").grid(
            row=1, column=3, padx=(15, 2), pady=5, sticky="w"
        )
        create_help_label(
            adv_frame,
            "Quantidade de peixes dentro de cada aquário."
        ).grid(row=1, column=4, padx=2)
        Spinbox(
            adv_frame, from_=1, to=100, textvariable=self.animals_per_aquarium_var, width=8
        ).grid(row=1, column=5, padx=5, sticky="w")

        # Auto-detect on open
        self.after(100, self._detect_cameras)

        return self.camera_combo

    def buttonbox(self):
        """Create custom button box with Start and Cancel."""
        box = Frame(self)

        Button(box, text="Iniciar Análise", width=15, command=self.ok, default="active").pack(
            side="left", padx=5, pady=5
        )
        Button(box, text="Cancelar", width=10, command=self.cancel).pack(
            side="left", padx=5, pady=5
        )

        self.bind("<Return>", lambda e: self.ok())
        self.bind("<Escape>", lambda e: self.cancel())

        box.pack()

    def _detect_cameras(self):
        """Detect available cameras using WizardService."""
        self.camera_status_label.config(text="Detectando...", fg="blue")
        self.update_idletasks()

        try:
            cameras = WizardService.detect_available_cameras()

            if cameras:
                # Build display names and index map
                self.camera_index_map.clear()
                display_names = []

                for cam in cameras:
                    index = cam["index"]
                    name = cam.get("name", f"Câmera {index}")
                    resolution = cam.get("resolution", "Unknown")
                    display_name = f"[{index}] {name} ({resolution})"
                    display_names.append(display_name)
                    self.camera_index_map[display_name] = index

                self.camera_combo["values"] = display_names

                # Auto-select first camera
                if display_names and not self.camera_selection_var.get():
                    self.camera_selection_var.set(display_names[0])

                self.camera_status_label.config(
                    text=f"✓ {len(cameras)} câmera(s) detectada(s)",
                    fg="green",
                )
            else:
                self.camera_combo["values"] = []
                self.camera_status_label.config(
                    text="✗ Nenhuma câmera detectada",
                    fg="red",
                )

        except Exception as e:
            log.error("live_analysis_dialog.camera_detection_error", error=str(e), exc_info=True)
            self.camera_status_label.config(
                text="✗ Erro ao detectar câmeras",
                fg="red",
            )
            messagebox.showerror(
                "Erro de Detecção",
                f"Falha ao detectar câmeras:\n{e}",
                parent=self,
            )

    def validate(self):
        """Validate inputs before accepting."""
        # Check camera selection
        selected = self.camera_selection_var.get().strip()
        if not selected:
            messagebox.showwarning(
                "Câmera Não Selecionada",
                "Por favor, selecione uma câmera para análise.",
                parent=self,
            )
            return False

        camera_index = self.camera_index_map.get(selected)
        if camera_index is None:
            messagebox.showerror(
                "Câmera Inválida",
                f"Índice de câmera não encontrado para: {selected}",
                parent=self,
            )
            return False

        # Check duration
        try:
            duration = float(self.duration_var.get())
            if duration <= 0:
                raise ValueError("Duração deve ser positiva")

            max_duration = self.settings.live_analysis.max_duration_s if self.settings else 7200.0
            if duration > max_duration:
                messagebox.showwarning(
                    "Duração Muito Longa",
                    f"Duração máxima permitida: {max_duration}s\nAjustando para o máximo...",
                    parent=self,
                )
                self.duration_var.set(max_duration)
                duration = max_duration

        except (ValueError, TypeError) as e:
            messagebox.showerror(
                "Duração Inválida",
                f"Duração deve ser um número positivo:\n{e}",
                parent=self,
            )
            return False

        # Validate intervals
        try:
            analysis_interval = int(self.analysis_interval_var.get())
            display_interval = int(self.display_interval_var.get())

            if analysis_interval < 1 or display_interval < 1:
                raise ValueError("Intervalos devem ser >= 1")

        except (ValueError, TypeError) as e:
            messagebox.showerror(
                "Intervalo Inválido",
                f"Intervalos devem ser números inteiros positivos:\n{e}",
                parent=self,
            )
            return False

        # Validate calibration parameters
        try:
            num_aquariums = int(self.num_aquariums_var.get())
            animals_per_aquarium = int(self.animals_per_aquarium_var.get())
            aquarium_width = float(self.aquarium_width_var.get())
            aquarium_height = float(self.aquarium_height_var.get())

            if num_aquariums < 1 or animals_per_aquarium < 1:
                raise ValueError("Número de aquários e animais devem ser >= 1")
            if aquarium_width <= 0 or aquarium_height <= 0:
                raise ValueError("Dimensões do aquário devem ser positivas")

        except (ValueError, TypeError) as e:
            messagebox.showerror(
                "Parâmetro de Calibração Inválido",
                f"Erro na calibração:\n{e}",
                parent=self,
            )
            return False

        # Validate behavior parameters
        try:
            sharp_turn = float(self.sharp_turn_var.get())
            freeze_thresh = float(self.freeze_thresh_var.get())
            freeze_dur = float(self.freeze_dur_var.get())

            if sharp_turn < 0 or freeze_thresh < 0 or freeze_dur < 0:
                raise ValueError("Parâmetros comportamentais devem ser não-negativos")

        except (ValueError, TypeError) as e:
            messagebox.showerror(
                "Parâmetro Comportamental Inválido",
                f"Erro nos parâmetros comportamentais:\n{e}",
                parent=self,
            )
            return False

        # Validate smoothing parameters
        try:
            smoothing_window = int(self.smoothing_window_var.get())
            smoothing_polyorder = int(self.smoothing_polyorder_var.get())

            if smoothing_window < 3:
                raise ValueError("Janela de suavização deve ser >= 3")
            if smoothing_window % 2 == 0:
                raise ValueError("Janela de suavização deve ser ímpar")
            if smoothing_polyorder < 1:
                raise ValueError("Ordem do polinômio deve ser >= 1")
            if smoothing_polyorder >= smoothing_window:
                raise ValueError("Ordem do polinômio deve ser menor que a janela")

        except (ValueError, TypeError) as e:
            messagebox.showerror(
                "Parâmetro de Suavização Inválido",
                f"Erro nos parâmetros de suavização:\n{e}",
                parent=self,
            )
            return False

        return True

    def apply(self):
        """Build result dictionary and update settings."""
        selected = self.camera_selection_var.get().strip()
        camera_index = self.camera_index_map[selected]

        experiment_id = self.experiment_id_var.get().strip()
        if not experiment_id:
            from datetime import datetime

            experiment_id = f"camera_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        analysis_interval = int(self.analysis_interval_var.get())
        display_interval = int(self.display_interval_var.get())
        num_aquariums = int(self.num_aquariums_var.get())
        animals_per_aquarium = int(self.animals_per_aquarium_var.get())

        # Update the shared settings object to ensure consistency in other UI tabs
        if self.settings:
            try:
                if hasattr(self.settings, "video_processing"):
                    self.settings.video_processing.processing_interval = analysis_interval
                    self.settings.video_processing.display_interval = display_interval
                    self.settings.video_processing.sharp_turn_threshold_deg_s = float(self.sharp_turn_var.get())
                    self.settings.video_processing.freezing_velocity_threshold = float(self.freeze_thresh_var.get())
                    self.settings.video_processing.freezing_min_duration_s = float(self.freeze_dur_var.get())
                
                if hasattr(self.settings, "trajectory_smoothing"):
                    self.settings.trajectory_smoothing.window_length = int(self.smoothing_window_var.get())
                    self.settings.trajectory_smoothing.polyorder = int(self.smoothing_polyorder_var.get())
                
                if hasattr(self.settings, "model_selection"):
                    self.settings.model_selection.aquarium_method = self.aquarium_method_var.get()
                    self.settings.model_selection.animal_method = self.animal_method_var.get()
                    self.settings.model_selection.use_openvino = bool(self.use_openvino_var.get())
                
                if hasattr(self.settings, "analysis_config"):
                    self.settings.analysis_config.num_aquariums = num_aquariums
                
                if hasattr(self.settings, "tracking"):
                    self.settings.tracking.use_single_subject_tracker = (animals_per_aquarium == 1)

                log.info("live_analysis_dialog.apply.settings_updated")
            except Exception as e:
                log.warning("live_analysis_dialog.apply.settings_update_failed", error=str(e))

        self.result = {
            "camera_index": camera_index,
            "duration_s": float(self.duration_var.get()),
            "analysis_interval_frames": analysis_interval,
            "display_interval_frames": display_interval,
            "record_video": bool(self.record_video_var.get()),
            "experiment_id": experiment_id,
            # Calibration parameters
            "num_aquariums": num_aquariums,
            "animals_per_aquarium": animals_per_aquarium,
            "aquarium_width_cm": float(self.aquarium_width_var.get()),
            "aquarium_height_cm": float(self.aquarium_height_var.get()),
            # Behavior parameters
            "sharp_turn_threshold_deg_s": float(self.sharp_turn_var.get()),
            "freezing_velocity_threshold": float(self.freeze_thresh_var.get()),
            "freezing_min_duration_s": float(self.freeze_dur_var.get()),
            # Smoothing parameters
            "smoothing_window_length": int(self.smoothing_window_var.get()),
            "smoothing_polyorder": int(self.smoothing_polyorder_var.get()),
            # Detection methods
            "aquarium_method": self.aquarium_method_var.get(),
            "animal_method": self.animal_method_var.get(),
            "use_openvino": bool(self.use_openvino_var.get()),
            "use_single_subject_tracker": animals_per_aquarium == 1,
        }

        log.info(
            "live_analysis_dialog.configured",
            camera_index=camera_index,
            duration_s=self.result["duration_s"],
            experiment_id=experiment_id,
            num_aquariums=self.result["num_aquariums"],
            animals_per_aquarium=self.result["animals_per_aquarium"],
        )


if __name__ == "__main__":
    """Test LiveAnalysisDialog."""
    import tkinter as tk

    from zebtrack.settings import load_settings

    print("Testing LiveAnalysisDialog...")

    try:
        settings = load_settings()
        root = tk.Tk()
        root.withdraw()

        dialog = LiveAnalysisDialog(root, settings_obj=settings)

        if dialog.result:
            print("\nDialog Result:")
            for key, value in dialog.result.items():
                print(f"  {key}: {value}")
        else:
            print("\nDialog cancelled")

        root.destroy()

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()

    print("\nLiveAnalysisDialog test finished.")
