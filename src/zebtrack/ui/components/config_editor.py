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
from zebtrack.ui.components.behavioral_config_widget import BehavioralConfigWidget
from zebtrack.ui.event_bus_v2 import EventBusV2, UIEvents
from zebtrack.ui.wizard.tooltip import create_help_label

log = structlog.get_logger()


class ConfigEditorWidget(BaseWidget):
    """
    Reusable configuration editor widget.

    Provides:
    - Video processing settings (FPS, interval, offset)
    - Trajectory smoothing (window length, polynomial order)
    - Recorder settings (flush interval, row limit)
    - ROI parameters (inclusion rule, buffer, overlap)
    - Behavioral Analysis defaults (perspective, geotaxis)
    - Action buttons (save, reset)

    Events emitted:
    - config.save_requested: User clicked save (payload: dict of values)
    - config.reset_requested: User clicked reset
    - config.roi_rule_changed: ROI rule selection changed
    """

    def __init__(self, parent, event_bus: EventBusV2 | None = None, **kwargs):
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
        self.display_interval_var = StringVar(value="10")
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

        self.behavioral_config_widget: BehavioralConfigWidget | None = None

        super().__init__(parent, event_bus=event_bus, **kwargs)

    def _build_ui(self) -> None:
        """Build the configuration editor UI with 2-column layout."""
        self._build_intro()

        # Create 2-column container for better horizontal space usage
        columns_frame = ttk.Frame(self)
        columns_frame.pack(fill="both", expand=True, pady=(0, 10))
        columns_frame.columnconfigure(0, weight=1)  # Left column
        columns_frame.columnconfigure(1, weight=1)  # Right column

        # LEFT COLUMN: Video Processing, Smoothing, Recorder
        left_column = ttk.Frame(columns_frame)
        left_column.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        self._build_video_processing_section(left_column)
        self._build_trajectory_smoothing_section(left_column)
        self._build_recorder_section(left_column)
        self._build_action_buttons(left_column)  # Place buttons in left column (empty space)

        # RIGHT COLUMN: ROI, Behavioral Analysis
        right_column = ttk.Frame(columns_frame)
        right_column.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        self._build_roi_section(right_column)
        self._build_behavioral_analysis_section(right_column)

    def _build_behavioral_analysis_section(self, parent=None) -> None:
        """Build behavioral analysis default settings."""
        container = parent if parent else self
        behavioral_frame = ttk.LabelFrame(
            container,
            text="Padrões de Análise Comportamental",
            padding=10,
        )
        behavioral_frame.pack(fill="x", pady=6)

        self.behavioral_config_widget = BehavioralConfigWidget(
            behavioral_frame,
            event_bus=self.event_bus,
            default_perspective="lateral",
            default_geotaxis_mode="zones",
        )
        self.behavioral_config_widget.pack(fill="x", expand=True)

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

    def _build_video_processing_section(self, parent=None) -> None:
        """Build video processing settings frame."""
        container = parent if parent else self
        video_frame = ttk.LabelFrame(
            container,
            text="Processamento de Vídeo",
            padding=10,
        )
        video_frame.pack(fill="x", pady=6)

        # Grid: Label | Help | Entry | Extra
        video_frame.columnconfigure(1, weight=0)
        video_frame.columnconfigure(2, weight=0)
        video_frame.columnconfigure(3, weight=1)

        # FPS
        ttk.Label(video_frame, text="FPS de saída (MP4):").grid(
            row=0, column=0, sticky="w", padx=(0, 2), pady=2
        )
        create_help_label(
            video_frame,
            "FPS de Saída (Frames Per Second)\n\n"
            "Define a velocidade de reprodução do vídeo .mp4 resultante da análise.\n"
            "• Recomendado: O mesmo valor do vídeo original (ex: 30).\n"
            "• Aumentar: O vídeo parecerá acelerado.\n"
            "• Diminuir: O vídeo parecerá em câmera lenta.",
        ).grid(row=0, column=1, padx=2)
        ttk.Entry(video_frame, textvariable=self.fps_var, width=8).grid(
            row=0, column=2, sticky="w", padx=5
        )

        # Processing interval
        ttk.Label(video_frame, text="Intervalo Processamento (N):").grid(
            row=1, column=0, sticky="w", padx=(0, 2), pady=2
        )
        create_help_label(
            video_frame,
            "Intervalo de Processamento (Análise)\n\n"
            "Processa 1 frame a cada N frames originais.\n"
            "• N=1: Processa TODOS os frames (máxima precisão, mais lento).\n"
            "• N=10: Processa 1 frame e pula 9 (mais rápido, ideal para vídeos longos).\n"
            "• Aumentar: Reduz drasticamente o tempo de processamento.\n"
            "• Diminuir: Melhora a resolução temporal das métricas de velocidade.",
        ).grid(row=1, column=1, padx=2)
        ttk.Entry(video_frame, textvariable=self.processing_interval_var, width=8).grid(
            row=1, column=2, sticky="w", padx=5
        )

        # Display interval
        ttk.Label(video_frame, text="Intervalo Exibição (N):").grid(
            row=2, column=0, sticky="w", padx=(0, 2), pady=2
        )
        create_help_label(
            video_frame,
            "Intervalo de Exibição (UI)\n\n"
            "Atualiza a imagem na tela a cada N frames processados.\n"
            "• N=1: Exibição fluida (consome mais CPU/GPU).\n"
            "• N=30: Atualiza a cada 30 frames (mais leve).\n"
            "• Útil para acelerar a análise economizando recursos visuais.",
        ).grid(row=2, column=1, padx=2)
        ttk.Entry(video_frame, textvariable=self.display_interval_var, width=8).grid(
            row=2, column=2, sticky="w", padx=5
        )

        # Processing offset
        ttk.Label(video_frame, text="Offset Inicial (frames):").grid(
            row=3, column=0, sticky="w", padx=(0, 2), pady=2
        )
        create_help_label(
            video_frame,
            "Offset Inicial\n\n"
            "Número de frames iniciais a serem ignorados antes de "
            "começar o rastreamento.\n"
            "• Use para descartar o período de estabilização da água ou a mão "
            "do experimentador saindo de cena.\n"
            "• Ex: Em um vídeo de 30fps, um offset de 90 frames ignora os primeiros 3 segundos.",
        ).grid(row=3, column=1, padx=2)
        ttk.Entry(video_frame, textvariable=self.processing_offset_var, width=8).grid(
            row=3, column=2, sticky="w", padx=5
        )

    def _build_trajectory_smoothing_section(self, parent=None) -> None:
        """Build trajectory smoothing settings frame."""
        container = parent if parent else self
        smoothing_frame = ttk.LabelFrame(
            container,
            text="Suavização de Trajetória (Filtro Savitzky-Golay)",
            padding=10,
        )
        smoothing_frame.pack(fill="x", pady=6)

        # Grid: Label | Help | Entry
        smoothing_frame.columnconfigure(1, weight=0)
        smoothing_frame.columnconfigure(2, weight=0)
        smoothing_frame.columnconfigure(3, weight=1)

        # Window Length
        ttk.Label(smoothing_frame, text="Janela de Suavização:").grid(
            row=0, column=0, sticky="w", padx=(0, 2), pady=2
        )
        create_help_label(
            smoothing_frame,
            "Janela de Suavização (Window Length)\n\n"
            "Número de frames usados para suavizar a trajetória. DEVE SER ÍMPAR.\n"
            "• Aumentar (ex: 11, 15): Remove mais ruído/tremido, mas pode "
            "'arredondar' demais as curvas.\n"
            "• Diminuir (ex: 3, 5): Mantém mais detalhes dos movimentos bruscos.\n"
            "• Padrão: 7",
        ).grid(row=0, column=1, padx=2)
        ttk.Entry(smoothing_frame, textvariable=self.window_length_var, width=8).grid(
            row=0, column=2, sticky="w", padx=5
        )

        # Polynomial Order
        ttk.Label(smoothing_frame, text="Ordem do Polinômio:").grid(
            row=1, column=0, sticky="w", padx=(0, 2), pady=2
        )
        create_help_label(
            smoothing_frame,
            "Ordem do Polinômio (Polyorder)\n\n"
            "Complexidade da curva usada para ajustar os pontos. Deve ser MENOR que a janela.\n"
            "• 1: Linha reta (suavização agressiva).\n"
            "• 2: Curva simples (parábola).\n"
            "• 3: Curva mais complexa (recomendado).\n"
            "• Aumentar: A curva segue mais de perto os pontos originais.\n"
            "• Padrão: 3",
        ).grid(row=1, column=1, padx=2)
        ttk.Entry(smoothing_frame, textvariable=self.polyorder_var, width=8).grid(
            row=1, column=2, sticky="w", padx=5
        )

        # Overall explanation
        ttk.Label(
            smoothing_frame,
            text=(
                "ℹ️ Este filtro remove tremidos pequenos da detecção sem perder o rastro real. "
                "Útil para métricas de distância e velocidade mais precisas."
            ),
            font=("TkDefaultFont", 8),
            foreground="#2563eb",
            justify="left",
            wraplength=550,
        ).grid(row=2, column=0, columnspan=4, sticky="w", padx=(0, 6), pady=(8, 0))

    def _build_recorder_section(self, parent=None) -> None:
        """Build recorder settings frame."""
        container = parent if parent else self
        recorder_frame = ttk.LabelFrame(
            container,
            text="Gravação de Dados (Recorder)",
            padding=10,
        )
        recorder_frame.pack(fill="x", pady=6)

        # Grid: Label | Help | Entry
        recorder_frame.columnconfigure(1, weight=0)
        recorder_frame.columnconfigure(2, weight=0)
        recorder_frame.columnconfigure(3, weight=1)

        # Flush interval
        ttk.Label(recorder_frame, text="Flush Automático (s):").grid(
            row=0, column=0, sticky="w", padx=(0, 2), pady=2
        )
        create_help_label(
            recorder_frame,
            "Intervalo de Flush (Tempo)\n\n"
            "A cada X segundos, o sistema força a gravação dos dados da "
            "memória para o arquivo Parquet.\n"
            "• Protege contra perda de dados se o app cair.\n"
            "• Valores baixos (ex: 1.0) aumentam o uso de disco.\n"
            "• Padrão: 5.0s",
        ).grid(row=0, column=1, padx=2)
        ttk.Entry(recorder_frame, textvariable=self.flush_interval_var, width=8).grid(
            row=0, column=2, sticky="w", padx=5
        )

        # Flush rows
        ttk.Label(recorder_frame, text="Limite de Linhas (Flush):").grid(
            row=1, column=0, sticky="w", padx=(0, 2), pady=2
        )
        create_help_label(
            recorder_frame,
            "Limite de Linhas para Flush\n\n"
            "Grava dados imediatamente ao atingir X linhas em memória.\n"
            "• Padrão: 500 linhas.",
        ).grid(row=1, column=1, padx=2)
        ttk.Entry(recorder_frame, textvariable=self.flush_rows_var, width=8).grid(
            row=1, column=2, sticky="w", padx=5
        )

    def _build_roi_section(self, parent=None) -> None:
        """Build ROI parameters frame."""
        container = parent if parent else self
        roi_frame = ttk.LabelFrame(
            container,
            text="Lógica de Inclusão em ROI (Padrão)",
            padding=10,
        )
        roi_frame.pack(fill="x", pady=6)

        # Grid: Label | Help | Entry
        roi_frame.columnconfigure(1, weight=0)
        roi_frame.columnconfigure(2, weight=0)
        roi_frame.columnconfigure(3, weight=1)

        # Inclusion rule
        ttk.Label(roi_frame, text="Regra de Inclusão:").grid(
            row=0, column=0, sticky="w", padx=(0, 2), pady=2
        )
        create_help_label(
            roi_frame,
            "Lógica de Inclusão em ROI\n\n"
            "Define quando o peixe é considerado 'dentro' de uma zona.\n"
            "• Centroide (centroid_in): Apenas se o ponto central estiver na zona.\n"
            "• Centroide c/ Buffer: Expande a zona virtualmente para o cálculo.\n"
            "• Intersecção BBox: Se qualquer parte da caixa do peixe tocar a zona.\n"
            "• Sobreposição Seg: Baseado na máscara de pixels (mais preciso).",
        ).grid(row=0, column=1, padx=2)

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
        config_roi_combo.grid(row=0, column=2, sticky="w", padx=5)
        config_roi_combo.bind("<<ComboboxSelected>>", self._on_roi_rule_changed)
        self._roi_rule_widgets.append(config_roi_combo)

        # Buffer radius
        ttk.Label(roi_frame, text="Raio de Buffer (r):").grid(
            row=1, column=0, sticky="w", padx=(0, 2), pady=2
        )
        create_help_label(
            roi_frame,
            "Raio de Buffer\n\n"
            "Distância extra para expansão da ROI na regra 'Centroide c/ Buffer'.\n"
            "• Unidade: Centímetros (se calibrado) ou Pixels.",
        ).grid(row=1, column=1, padx=2)
        ttk.Entry(roi_frame, textvariable=self.roi_buffer_radius_var, width=8).grid(
            row=1, column=2, sticky="w", padx=5
        )

        # Overlap ratio
        ttk.Label(roi_frame, text="Sobreposição Mínima:").grid(
            row=2, column=0, sticky="w", padx=(0, 2), pady=2
        )
        create_help_label(
            roi_frame,
            "Fração de Sobreposição Mínima\n\n"
            "Mínimo de área do peixe (0 a 1) que deve estar na zona para contar.\n"
            "• Ex: 0.50 significa que metade do peixe deve estar dentro.",
        ).grid(row=2, column=1, padx=2)
        ttk.Entry(roi_frame, textvariable=self.roi_overlap_ratio_var, width=8).grid(
            row=2, column=2, sticky="w", padx=5
        )

        # Hint
        ttk.Label(
            roi_frame,
            text=(
                "💡 Dica: Estas são configurações GLOBAIS. Você pode alterá-las "
                "por projeto na aba de Zonas."
            ),
            font=("TkDefaultFont", 8),
            foreground="#555555",
        ).grid(row=3, column=0, columnspan=4, sticky="w", pady=(6, 0))

    def _build_action_buttons(self, parent=None) -> None:
        """Build action buttons frame."""
        container = parent if parent else self
        actions_frame = ttk.Frame(container)
        actions_frame.pack(fill="x", pady=(12, 0))
        ttk.Button(
            actions_frame,
            text="Recarregar valores atuais",
            command=self._on_reset_clicked,
        ).pack(side="left")
        self.btn_save = ttk.Button(
            actions_frame,
            text="💾 Salvar Configurações",
            command=self._on_save_clicked,
            style="Accent.TButton",
        ).pack(side="right")

        # Validation info
        ttk.Label(
            container,
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
                "display_interval": int(self.display_interval_var.get().strip()),
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
            "behavioral_analysis": self._get_behavioral_values(),
        }

    def _get_behavioral_values(self) -> dict[str, Any]:
        """Extract and map behavioral values."""
        if not self.behavioral_config_widget:
            return {}

        widget_values = self.behavioral_config_widget.get_values()
        return {
            "default_thigmotaxis_distance_cm": widget_values["thigmotaxis_distance_cm"],
            "default_geotaxis_distance_cm": widget_values["geotaxis_distance_cm"],
            "default_geotaxis_num_zones": widget_values["geotaxis_num_zones"],
            "default_geotaxis_bottom_zones": widget_values["geotaxis_bottom_zones"],
            "aquarium_perspective": widget_values["aquarium_perspective"],
            "geotaxis_mode": widget_values["geotaxis_mode"],
        }

    def set_values(self, values: dict[str, Any]) -> None:
        """
        Populate form from nested dict.

        Args:
            values: Nested dictionary matching Settings structure
        """
        self._set_video_processing(values.get("video_processing", {}))
        self._set_trajectory_smoothing(values.get("trajectory_smoothing", {}))
        self._set_recorder(values.get("recorder", {}))
        self._set_roi_settings(values)
        self._set_behavioral_analysis(values.get("behavioral_analysis", {}))

    def _set_video_processing(self, vp: dict[str, Any]) -> None:
        """Populate video processing settings."""
        if not vp:
            return
        if "fps" in vp:
            self.fps_var.set(str(vp["fps"]))
        if "processing_interval" in vp:
            self.processing_interval_var.set(str(vp["processing_interval"]))
        if "display_interval" in vp:
            self.display_interval_var.set(str(vp["display_interval"]))
        if "processing_offset" in vp:
            self.processing_offset_var.set(str(vp["processing_offset"]))

    def _set_trajectory_smoothing(self, ts: dict[str, Any]) -> None:
        """Populate trajectory smoothing settings."""
        if not ts:
            return
        if "window_length" in ts:
            self.window_length_var.set(str(ts["window_length"]))
        if "polyorder" in ts:
            self.polyorder_var.set(str(ts["polyorder"]))

    def _set_recorder(self, rec: dict[str, Any]) -> None:
        """Populate recorder settings."""
        if not rec:
            return
        if "flush_interval_seconds" in rec:
            self.flush_interval_var.set(str(rec["flush_interval_seconds"]))
        if "flush_row_threshold" in rec:
            self.flush_rows_var.set(str(rec["flush_row_threshold"]))

    def _set_roi_settings(self, values: dict[str, Any]) -> None:
        """Populate ROI settings."""
        if "roi_min_bbox_overlap_ratio" in values:
            self.roi_overlap_ratio_var.set(str(values["roi_min_bbox_overlap_ratio"]))

        if "roi_inclusion_rule" in values:
            self.roi_inclusion_rule_var.set(str(values["roi_inclusion_rule"]))

        if "roi_buffer_radius_value" in values:
            self.roi_buffer_radius_var.set(str(values["roi_buffer_radius_value"]))

    def _set_behavioral_analysis(self, ba: dict[str, Any]) -> None:
        """Populate behavioral analysis settings."""
        if not ba or not self.behavioral_config_widget:
            return

        widget_values = {}
        # Map settings keys -> widget keys
        if "default_thigmotaxis_distance_cm" in ba:
            widget_values["thigmotaxis_distance_cm"] = ba["default_thigmotaxis_distance_cm"]
        if "default_geotaxis_distance_cm" in ba:
            widget_values["geotaxis_distance_cm"] = ba["default_geotaxis_distance_cm"]
        if "default_geotaxis_num_zones" in ba:
            widget_values["geotaxis_num_zones"] = ba["default_geotaxis_num_zones"]
        if "default_geotaxis_bottom_zones" in ba:
            widget_values["geotaxis_bottom_zones"] = ba["default_geotaxis_bottom_zones"]
        if "aquarium_perspective" in ba:
            widget_values["aquarium_perspective"] = ba["aquarium_perspective"]
        if "geotaxis_mode" in ba:
            widget_values["geotaxis_mode"] = ba["geotaxis_mode"]

        # We enable geotaxis in the editor so user can edit the values,
        # even if it's not "enabled" by default in a specific analysis.
        widget_values["geotaxis_enabled"] = True

        self.behavioral_config_widget.set_values(widget_values)

    def _on_save_clicked(self) -> None:
        """Handle save button click."""
        try:
            values = self.get_values()
            self.emit_event(UIEvents.CONFIG_SAVE_REQUESTED, {"values": values})
        except ValueError as e:
            self.emit_event(UIEvents.CONFIG_VALIDATION_ERROR, {"error": str(e)})

    def _on_reset_clicked(self) -> None:
        """Handle reset button click."""
        self.emit_event(UIEvents.CONFIG_RESET_REQUESTED, {})

    def _on_roi_rule_changed(self, event=None) -> None:
        """Handle ROI rule combobox change."""
        selected_rule = self.roi_inclusion_rule_var.get()
        self.emit_event(UIEvents.CONFIG_ROI_RULE_CHANGED, {"rule": selected_rule})
