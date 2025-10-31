"""
Configuration editor widget component - advanced settings editor.

Provides a form-based interface for editing application configuration
parameters across multiple categories: video processing, trajectory
smoothing, recorder settings, and ROI parameters.
"""

from pathlib import Path
from tkinter import StringVar, ttk
from typing import Any

import structlog

from zebtrack.ui.components.base import BaseWidget
from zebtrack.ui.event_bus import EventBus

log = structlog.get_logger()


class ConfigEditorWidget(BaseWidget):
    """
    Reusable configuration editor widget.

    Provides:
    - Video processing settings (FPS, interval, offset)
    - Trajectory smoothing (window length, polynomial order)
    - Recorder settings (flush interval, row limit)
    - ROI parameters (inclusion rule, buffer, overlap)
    - Action buttons (save, reset)

    Events emitted:
    - config.save_requested: User clicked save (payload: dict of values)
    - config.reset_requested: User clicked reset
    - config.roi_rule_changed: ROI rule selection changed
    """

    def __init__(self, parent, event_bus: EventBus | None = None, **kwargs):
        """
        Initialize configuration editor widget.

        Args:
            parent: Parent Tkinter widget
            event_bus: Optional event bus for event emission
            **kwargs: Additional arguments for ttk.Frame
        """
        # Initialize all StringVar instances with default values
        self.fps_var = StringVar(value="30")
        self.processing_interval_var = StringVar(value="10")
        self.processing_offset_var = StringVar(value="0")
        self.window_length_var = StringVar(value="7")
        self.polyorder_var = StringVar(value="3")
        self.flush_interval_var = StringVar(value="5.0")
        self.flush_rows_var = StringVar(value="500")
        self.roi_inclusion_rule_var = StringVar(value="centroid_in")
        self.roi_buffer_radius_var = StringVar(value="0")
        self.roi_overlap_ratio_var = StringVar(value="0.5")

        # ROI rule widgets list for conditional enable/disable
        self._roi_rule_widgets: list[ttk.Widget] = []

        super().__init__(parent, event_bus=event_bus, **kwargs)

    def _build_ui(self) -> None:
        """Build the configuration editor UI."""
        self._build_intro()
        self._build_video_processing_section()
        self._build_trajectory_smoothing_section()
        self._build_recorder_section()
        self._build_roi_section()
        self._build_action_buttons()

    def _build_intro(self) -> None:
        """Build introduction text."""
        intro = (
            "Edite parâmetros avançados do config.yaml sem sair do aplicativo. "
            "As alterações são persistidas em config.local.yaml e recarregadas "
            "automaticamente por settings.load_settings()."
        )
        ttk.Label(
            self,
            text=intro,
            wraplength=560,
            justify="left",
        ).pack(fill="x", pady=(0, 12))

        config_path_hint = ttk.Label(
            self,
            text=(
                f"Arquivos monitorados: {Path('config.yaml').absolute()} → "
                f"{Path('config.local.yaml').absolute()}"
            ),
            wraplength=560,
            justify="left",
            font=("TkDefaultFont", 8),
        )
        config_path_hint.pack(fill="x", pady=(0, 12))

    def _build_video_processing_section(self) -> None:
        """Build video processing settings frame."""
        video_frame = ttk.LabelFrame(
            self,
            text="Processamento de Vídeo",
            padding=10,
        )
        video_frame.pack(fill="x", pady=6)
        video_frame.columnconfigure(1, weight=0)
        video_frame.columnconfigure(2, weight=1)

        # FPS
        ttk.Label(video_frame, text="FPS de saída (MP4):").grid(
            row=0, column=0, sticky="w", padx=(0, 6), pady=2
        )
        ttk.Entry(video_frame, textvariable=self.fps_var, width=8).grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(
            video_frame,
            text="Define a taxa de quadros do vídeo salvo em disco.",
            font=("TkDefaultFont", 8),
            wraplength=320,
        ).grid(row=0, column=2, sticky="w")

        # Processing interval
        ttk.Label(video_frame, text="Intervalo de processamento (N):").grid(
            row=1, column=0, sticky="w", padx=(0, 6), pady=2
        )
        ttk.Entry(video_frame, textvariable=self.processing_interval_var, width=8).grid(
            row=1, column=1, sticky="w"
        )
        ttk.Label(
            video_frame,
            text="Processa 1 frame a cada N frames originais.",
            font=("TkDefaultFont", 8),
            wraplength=320,
        ).grid(row=1, column=2, sticky="w")

        # Processing offset
        ttk.Label(video_frame, text="Offset inicial (frames):").grid(
            row=2, column=0, sticky="w", padx=(0, 6), pady=2
        )
        ttk.Entry(video_frame, textvariable=self.processing_offset_var, width=8).grid(
            row=2, column=1, sticky="w"
        )
        ttk.Label(
            video_frame,
            text=(
                "Offset inicial: Número de frames iniciais ignorados antes de começar "
                "a análise, útil para desconsiderar período de estabilização."
            ),
            font=("TkDefaultFont", 8),
            wraplength=320,
        ).grid(row=2, column=2, sticky="w")

    def _build_trajectory_smoothing_section(self) -> None:
        """Build trajectory smoothing settings frame."""
        smoothing_frame = ttk.LabelFrame(
            self,
            text="Suavização de Trajetória (Remove Tremidos/Ruído)",
            padding=10,
        )
        smoothing_frame.pack(fill="x", pady=6)
        smoothing_frame.columnconfigure(2, weight=1)

        # Window Length
        ttk.Label(smoothing_frame, text="Janela de Suavização (frames):").grid(
            row=0, column=0, sticky="w", padx=(0, 6), pady=2
        )
        ttk.Entry(smoothing_frame, textvariable=self.window_length_var, width=8).grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(
            smoothing_frame,
            text=(
                "Janela de suavização: Número de frames usados para calcular a média "
                "móvel das posições, reduzindo ruído na trajetória."
            ),
            font=("TkDefaultFont", 8),
            foreground="#555",
            wraplength=380,
        ).grid(row=0, column=2, sticky="w")

        # Polynomial Order
        ttk.Label(smoothing_frame, text="Ordem do Polinômio:").grid(
            row=1, column=0, sticky="w", padx=(0, 6), pady=2
        )
        ttk.Entry(smoothing_frame, textvariable=self.polyorder_var, width=8).grid(
            row=1, column=1, sticky="w"
        )
        ttk.Label(
            smoothing_frame,
            text=(
                "Tipo de curva: 1=reta, 2=curva suave, 3=curva com dobra. "
                "Maior = curvas mais sinuosas (bom para viradas bruscas)."
            ),
            font=("TkDefaultFont", 8),
            foreground="#555",
            wraplength=380,
        ).grid(row=1, column=2, sticky="w")

        # Overall explanation
        ttk.Label(
            smoothing_frame,
            text=(
                "ℹ️ Remove tremidos da câmera sem apagar movimentos reais. "
                "Ajusta uma curva suave aos pontos detectados. "
                "Restrição: janela ímpar (3, 5, 7...) e ordem < janela. "
                "Padrão: janela=7, ordem=3."
            ),
            font=("TkDefaultFont", 8),
            foreground="#2563eb",
            justify="left",
            wraplength=550,
        ).grid(row=2, column=0, columnspan=3, sticky="w", padx=(0, 6), pady=(8, 0))

    def _build_recorder_section(self) -> None:
        """Build recorder settings frame."""
        recorder_frame = ttk.LabelFrame(
            self,
            text="Recorder (Parquet/MP4)",
            padding=10,
        )
        recorder_frame.pack(fill="x", pady=6)
        recorder_frame.columnconfigure(2, weight=1)

        # Flush interval
        ttk.Label(recorder_frame, text="Flush automático (s):").grid(
            row=0, column=0, sticky="w", padx=(0, 6), pady=2
        )
        ttk.Entry(recorder_frame, textvariable=self.flush_interval_var, width=8).grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(
            recorder_frame,
            text="Define intervalo para descarregar buffers no Parquet.",
            font=("TkDefaultFont", 8),
            wraplength=320,
        ).grid(row=0, column=2, sticky="w")

        # Flush rows
        ttk.Label(recorder_frame, text="Limite de linhas por flush:").grid(
            row=1, column=0, sticky="w", padx=(0, 6), pady=2
        )
        ttk.Entry(recorder_frame, textvariable=self.flush_rows_var, width=8).grid(
            row=1, column=1, sticky="w"
        )
        ttk.Label(
            recorder_frame,
            text="Quando atingir este limite, os dados são gravados imediatamente.",
            font=("TkDefaultFont", 8),
            wraplength=320,
        ).grid(row=1, column=2, sticky="w")

    def _build_roi_section(self) -> None:
        """Build ROI parameters frame."""
        roi_frame = ttk.LabelFrame(
            self,
            text="Parâmetros padrão de ROI",
            padding=10,
        )
        roi_frame.pack(fill="x", pady=6)
        roi_frame.columnconfigure(2, weight=1)

        # Inclusion rule
        ttk.Label(roi_frame, text="Regra de inclusão:").grid(
            row=0, column=0, sticky="w", padx=(0, 6), pady=2
        )
        config_roi_combo = ttk.Combobox(
            roi_frame,
            textvariable=self.roi_inclusion_rule_var,
            values=[
                "centroid_in",
                "centroid_in_on_buffered_roi",
                "bbox_intersects",
                "seg_overlap",
            ],
            state="readonly",
            width=28,
        )
        config_roi_combo.grid(row=0, column=1, sticky="w")
        config_roi_combo.bind("<<ComboboxSelected>>", self._on_roi_rule_changed)
        self._roi_rule_widgets.append(config_roi_combo)
        ttk.Label(
            roi_frame,
            text="Selecione a lógica padrão aplicada ao carregar projetos.",
            font=("TkDefaultFont", 8),
            wraplength=320,
        ).grid(row=0, column=2, sticky="w")

        # Buffer radius
        ttk.Label(roi_frame, text="Raio de buffer (r):").grid(
            row=1, column=0, sticky="w", padx=(0, 6), pady=2
        )
        ttk.Entry(roi_frame, textvariable=self.roi_buffer_radius_var, width=8).grid(
            row=1, column=1, sticky="w"
        )
        ttk.Label(
            roi_frame,
            text="Obrigatório (>0) para a opção de centróide com buffer.",
            font=("TkDefaultFont", 8),
            wraplength=320,
        ).grid(row=1, column=2, sticky="w")

        # Overlap ratio
        ttk.Label(roi_frame, text="Sobreposição mínima (0–1):").grid(
            row=2, column=0, sticky="w", padx=(0, 6), pady=2
        )
        ttk.Entry(roi_frame, textvariable=self.roi_overlap_ratio_var, width=8).grid(
            row=2, column=1, sticky="w"
        )
        ttk.Label(
            roi_frame,
            text="É aplicado às regras bbox_intersects/seg_overlap.",
            font=("TkDefaultFont", 8),
            wraplength=320,
        ).grid(row=2, column=2, sticky="w")

        # Hint
        ttk.Label(
            roi_frame,
            text="Dica: use o painel de Zonas para testar combinações em tempo real.",
            font=("TkDefaultFont", 8),
            foreground="#555555",
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))

    def _build_action_buttons(self) -> None:
        """Build action buttons frame."""
        actions_frame = ttk.Frame(self)
        actions_frame.pack(fill="x", pady=(12, 0))
        ttk.Button(
            actions_frame,
            text="Recarregar valores atuais",
            command=self._on_reset_clicked,
        ).pack(side="left")
        ttk.Button(
            actions_frame,
            text="Salvar em config.local.yaml",
            command=self._on_save_clicked,
        ).pack(side="right")

        # Validation info
        ttk.Label(
            self,
            text=(
                "As validações avançadas (offset < intervalo, polyorder < janela, "
                "etc.) são aplicadas automaticamente ao salvar."
            ),
            wraplength=560,
            justify="left",
            font=("TkDefaultFont", 8),
        ).pack(fill="x", pady=(6, 0))

    def get_values(self) -> dict[str, Any]:
        """
        Get all form values as nested dict matching Settings structure.

        Returns:
            Dictionary with nested structure matching Settings model
        """
        return {
            "video_processing": {
                "fps": int(self.fps_var.get().strip()),
                "processing_interval": int(self.processing_interval_var.get().strip()),
                "processing_offset": int(self.processing_offset_var.get().strip()),
            },
            "trajectory_smoothing": {
                "window_length": int(self.window_length_var.get().strip()),
                "polyorder": int(self.polyorder_var.get().strip()),
            },
            "recorder": {
                "flush_interval_seconds": float(self.flush_interval_var.get().strip()),
                "flush_row_threshold": int(self.flush_rows_var.get().strip()),
            },
            "roi_inclusion_rule": self.roi_inclusion_rule_var.get(),
            "roi_buffer_radius_value": float(self.roi_buffer_radius_var.get().strip()),
            "roi_min_bbox_overlap_ratio": float(self.roi_overlap_ratio_var.get().strip()),
        }

    def set_values(self, values: dict[str, Any]) -> None:
        """
        Populate form from nested dict.

        Args:
            values: Nested dictionary matching Settings structure
        """
        # Video processing
        if "video_processing" in values:
            vp = values["video_processing"]
            if "fps" in vp:
                self.fps_var.set(str(vp["fps"]))
            if "processing_interval" in vp:
                self.processing_interval_var.set(str(vp["processing_interval"]))
            if "processing_offset" in vp:
                self.processing_offset_var.set(str(vp["processing_offset"]))

        # Trajectory smoothing
        if "trajectory_smoothing" in values:
            ts = values["trajectory_smoothing"]
            if "window_length" in ts:
                self.window_length_var.set(str(ts["window_length"]))
            if "polyorder" in ts:
                self.polyorder_var.set(str(ts["polyorder"]))

        # Recorder
        if "recorder" in values:
            rec = values["recorder"]
            if "flush_interval_seconds" in rec:
                self.flush_interval_var.set(str(rec["flush_interval_seconds"]))
            if "flush_row_threshold" in rec:
                self.flush_rows_var.set(str(rec["flush_row_threshold"]))

        # ROI parameters
        if "roi_inclusion_rule" in values:
            self.roi_inclusion_rule_var.set(values["roi_inclusion_rule"])
        if "roi_buffer_radius_value" in values:
            self.roi_buffer_radius_var.set(str(values["roi_buffer_radius_value"]))
        if "roi_min_bbox_overlap_ratio" in values:
            self.roi_overlap_ratio_var.set(str(values["roi_min_bbox_overlap_ratio"]))

    def _on_save_clicked(self) -> None:
        """Handle save button click."""
        try:
            values = self.get_values()
            self.emit_event("config.save_requested", {"values": values})
        except ValueError as e:
            self.emit_event("config.validation_error", {"error": str(e)})

    def _on_reset_clicked(self) -> None:
        """Handle reset button click."""
        self.emit_event("config.reset_requested", {})

    def _on_roi_rule_changed(self, event=None) -> None:
        """Handle ROI rule combobox change."""
        selected_rule = self.roi_inclusion_rule_var.get()
        self.emit_event("config.roi_rule_changed", {"rule": selected_rule})
