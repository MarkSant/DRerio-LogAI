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
    LabelFrame,
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
from zebtrack.ui.wizard.tooltip import ToolTip

log = structlog.get_logger()


class LiveAnalysisDialog(Dialog):
    """
    Dialog for configuring live camera analysis sessions.

    Provides an interface to:
    - Detect and select available cameras
    - Set analysis duration and intervals
    - Configure recording options
    - Start immediate analysis

    Result:
        dict with keys:
            - camera_index: int
            - duration_s: float
            - analysis_interval_frames: int
            - display_interval_frames: int
            - record_video: bool
            - experiment_id: str (optional)
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

        super().__init__(parent, title="Analisar Câmera ao Vivo")

        # Set application icon
        from zebtrack.ui.icon_utils import set_window_icon

        set_window_icon(self)

    def body(self, master):
        """Create dialog body."""
        # Title
        title = Label(
            master,
            text="Análise de Câmera ao Vivo",
            font=("TkDefaultFont", 12, "bold"),
        )
        title.pack(pady=(0, 10))

        subtitle = Label(
            master,
            text="Configure e inicie uma sessão de análise em tempo real da câmera.",
            fg="gray",
        )
        subtitle.pack(pady=(0, 20))

        # Camera selection
        camera_frame = LabelFrame(master, text="Câmera", padx=15, pady=10)
        camera_frame.pack(fill="x", pady=(0, 10))

        camera_row = Frame(camera_frame)
        camera_row.pack(fill="x", pady=5)

        Label(camera_row, text="Selecionar Câmera:", width=20, anchor="w").pack(side="left")

        self.camera_combo = ttk.Combobox(
            camera_row,
            textvariable=self.camera_selection_var,
            width=40,
            state="readonly",
        )
        self.camera_combo.pack(side="left", padx=(5, 10))
        ToolTip(self.camera_combo, "Selecione a câmera para análise ao vivo.")

        Button(camera_row, text="🔍 Detectar", command=self._detect_cameras, width=10).pack(
            side="left", padx=5
        )

        self.camera_status_label = Label(camera_row, text="", fg="gray")
        self.camera_status_label.pack(side="left", padx=5)

        # Duration settings
        duration_frame = LabelFrame(master, text="Duração", padx=15, pady=10)
        duration_frame.pack(fill="x", pady=(0, 10))

        duration_row = Frame(duration_frame)
        duration_row.pack(fill="x", pady=5)

        Label(duration_row, text="Duração (segundos):", width=20, anchor="w").pack(side="left")

        duration_spinbox = Spinbox(
            duration_row,
            from_=10,
            to=7200,
            textvariable=self.duration_var,
            width=10,
        )
        duration_spinbox.pack(side="left", padx=(5, 10))
        ToolTip(duration_spinbox, "Duração máxima da análise em segundos (10-7200).")

        # Quick duration buttons
        Button(
            duration_row, text="1 min", command=lambda: self.duration_var.set(60), width=6
        ).pack(side="left", padx=2)
        Button(
            duration_row, text="5 min", command=lambda: self.duration_var.set(300), width=6
        ).pack(side="left", padx=2)
        Button(
            duration_row, text="10 min", command=lambda: self.duration_var.set(600), width=6
        ).pack(side="left", padx=2)
        Button(
            duration_row, text="30 min", command=lambda: self.duration_var.set(1800), width=6
        ).pack(side="left", padx=2)

        # Processing intervals
        intervals_frame = LabelFrame(master, text="Intervalos de Processamento", padx=15, pady=10)
        intervals_frame.pack(fill="x", pady=(0, 10))

        analysis_row = Frame(intervals_frame)
        analysis_row.pack(fill="x", pady=5)

        Label(analysis_row, text="Intervalo de Análise:", width=20, anchor="w").pack(side="left")

        analysis_spinbox = Spinbox(
            analysis_row,
            from_=1,
            to=60,
            textvariable=self.analysis_interval_var,
            width=10,
        )
        analysis_spinbox.pack(side="left", padx=(5, 10))
        ToolTip(
            analysis_spinbox,
            "Processar detecções a cada N frames (menor = mais preciso, maior = mais rápido).",
        )

        display_row = Frame(intervals_frame)
        display_row.pack(fill="x", pady=5)

        Label(display_row, text="Intervalo de Exibição:", width=20, anchor="w").pack(side="left")

        display_spinbox = Spinbox(
            display_row,
            from_=1,
            to=60,
            textvariable=self.display_interval_var,
            width=10,
        )
        display_spinbox.pack(side="left", padx=(5, 10))
        ToolTip(
            display_spinbox, "Atualizar visualização a cada N frames (maior = menos carga de UI)."
        )

        # Recording options
        options_frame = LabelFrame(master, text="Opções", padx=15, pady=10)
        options_frame.pack(fill="x", pady=(0, 10))

        record_cb = ttk.Checkbutton(
            options_frame,
            text="Gravar vídeo com overlay de detecções",
            variable=self.record_video_var,
        )
        record_cb.pack(anchor="w", pady=5)
        ToolTip(
            record_cb,
            "Salvar vídeo com bounding boxes e rastreamento visualizado (aumenta uso de disco).",
        )

        # Experiment ID (optional)
        id_row = Frame(options_frame)
        id_row.pack(fill="x", pady=5)

        Label(id_row, text="ID do Experimento:", width=20, anchor="w").pack(side="left")

        id_entry = ttk.Entry(id_row, textvariable=self.experiment_id_var, width=30)
        id_entry.pack(side="left", padx=(5, 0))
        ToolTip(
            id_entry,
            "Identificador opcional para o experimento (padrão: camera_TIMESTAMP).",
        )

        # Auto-detect cameras on show
        self.after(100, self._detect_cameras)

        return self.camera_combo  # Initial focus

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

            max_duration = (
                self.settings.live_analysis.max_duration_s if self.settings else 7200.0
            )
            if duration > max_duration:
                messagebox.showwarning(
                    "Duração Muito Longa",
                    f"Duração máxima permitida: {max_duration}s\n"
                    f"Ajustando para o máximo...",
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

        return True

    def apply(self):
        """Build result dictionary."""
        selected = self.camera_selection_var.get().strip()
        camera_index = self.camera_index_map[selected]

        experiment_id = self.experiment_id_var.get().strip()
        if not experiment_id:
            from datetime import datetime

            experiment_id = f"camera_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self.result = {
            "camera_index": camera_index,
            "duration_s": float(self.duration_var.get()),
            "analysis_interval_frames": int(self.analysis_interval_var.get()),
            "display_interval_frames": int(self.display_interval_var.get()),
            "record_video": bool(self.record_video_var.get()),
            "experiment_id": experiment_id,
        }

        log.info(
            "live_analysis_dialog.configured",
            camera_index=camera_index,
            duration_s=self.result["duration_s"],
            experiment_id=experiment_id,
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
