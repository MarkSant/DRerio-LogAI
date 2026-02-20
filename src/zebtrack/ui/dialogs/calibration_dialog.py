"""
CalibrationDialog.

Extracted from gui.py for better modularity.
"""

import os
import tkinter as tk
from tkinter import (
    BooleanVar,
    StringVar,
    filedialog,
    messagebox,
    simpledialog,
    ttk,
)
from typing import Any

import structlog
from pydantic import ValidationError

from zebtrack.ui.collapsible_frame import CollapsibleFrame
from zebtrack.ui.dialogs.manage_weights_dialog import ManageWeightsDialog
from zebtrack.ui.events import Events
from zebtrack.ui.icon_utils import set_window_icon
from zebtrack.ui.window_utils import schedule_maximize
from zebtrack.ui.wizard.tooltip import ToolTip, create_help_label

log = structlog.get_logger()


class CalibrationDialog(simpledialog.Dialog):
    """Dialog for model calibration, diagnostics, and project preferences."""

    WEIGHT_INHERIT_LABEL = "Herdar (padrão global)"
    OPENVINO_INHERIT = "inherit"
    OPENVINO_ON = "on"
    OPENVINO_OFF = "off"

    def __init__(self, parent, controller):
        """Initialize the calibration dialog.

        Args:
            parent: Parent widget.
            controller: Main view model controller instance.
        """
        self.controller = controller
        self.project_manager = controller.project_manager

        self.calibration_section: ttk.Frame | None = None
        self.preferences_section: ttk.Frame | None = None
        self.preferences_separator: ttk.Separator | None = None

        # Local Tkinter variables for calibration tab
        self.active_weight_var = StringVar()
        self.use_openvino_var = BooleanVar()
        self.openvino_status_var = StringVar()
        self.scope_info = controller.get_calibration_scope_info()
        self.scope = self.scope_info.get("scope", "global")
        self.scope_label_var = StringVar(value=self.scope_info["label"])
        self.scope_detail_var = StringVar(value=self.scope_info["detail"])
        self.scope_action_button: ttk.Button | None = None
        self.weights_dropdown: ttk.Combobox | None = None
        self.openvino_checkbox: ttk.Checkbutton | None = None
        self.openvino_status_label: ttk.Label | None = None
        self.model_test_dropdown: ttk.Combobox | None = None

        # Diagnostic variables
        self.frames_to_analyze_var = StringVar(value="10")
        self.confidence_threshold_var = StringVar(value="0.25")
        self.nms_threshold_var = StringVar(value="0.50")
        self.use_bytetrack_var = BooleanVar(value=True)
        self.track_threshold_var = StringVar(value="0.25")
        self.match_threshold_var = StringVar(value="0.95")
        self.track_buffer_var = StringVar(value="90")
        self.max_center_dist_var = StringVar(value="400.0")
        self.iou_threshold_var = StringVar(value="0.05")

        self.video_path_label_var = StringVar(value="Nenhum vídeo selecionado.")
        self.diagnostic_video_path = ""
        self.model_test_var = StringVar(value="YOLO (PyTorch)")

        # Preferences tab state
        self.weight_choice = StringVar(value=self.WEIGHT_INHERIT_LABEL)
        self.openvino_choice = StringVar(value=self.OPENVINO_INHERIT)
        self.effective_weight_var = StringVar()
        self.effective_openvino_var = StringVar()
        self.preferences_weight_dropdown: ttk.Combobox | None = None

        self._prefill_detector_parameters()

        dialog_title = (
            "Calibração e Preferências do Projeto"
            if self.scope_info.get("scope") == "project"
            else "Calibração e Diagnóstico"
        )

        super().__init__(parent, dialog_title)

        # Set application icon

        try:
            set_window_icon(self)
        except Exception:
            log.warning("icon.set.failed", exc_info=True)

    def body(self, master):
        """Create calibration dialog body with model and detection controls.

        Args:
            master: Parent widget for dialog body.

        Returns:
            The initial focus widget.
        """
        schedule_maximize(self)

        container = ttk.Frame(master, padding=0)
        container.pack(fill="both", expand=True, padx=5, pady=5)

        # Calibration section with collapsible frame
        calibration_collapsible = CollapsibleFrame(
            container,
            title="📐 Calibração e Diagnóstico",
            start_collapsed=False,
        )
        calibration_collapsible.pack(fill="both", expand=False, pady=(0, 5))
        self.calibration_section = calibration_collapsible.get_content_frame()

        # Preferences section - only show for project scope
        if self.scope == "project":
            preferences_collapsible = CollapsibleFrame(
                container,
                title="⚙️ Preferências do Projeto",
                start_collapsed=False,
            )
            preferences_collapsible.pack(fill="both", expand=False, pady=(0, 5))
            self.preferences_section = preferences_collapsible.get_content_frame()
        else:
            self.preferences_section = None

        # Note: We no longer need the separator as CollapsibleFrames provide visual separation
        self.preferences_separator = None

        self._refresh_scope_context()

        return self.calibration_section

    @staticmethod
    def _clear_frame(frame: ttk.Frame) -> None:
        try:
            if not frame.winfo_exists():
                return
            for child in frame.winfo_children():
                child.destroy()
        except tk.TclError:
            # Frame already destroyed
            log.debug("calibration_dialog.clear_frame.suppressed", exc_info=True)

    def _build_calibration_section(self) -> None:
        if not self.calibration_section:
            return

        self._clear_frame(self.calibration_section)
        self.scope_action_button = None

        scope_frame = ttk.LabelFrame(
            self.calibration_section,
            text="Contexto da Calibração",
            padding=10,
        )
        scope_frame.pack(fill="x", pady=(5, 0), padx=5)

        ttk.Label(
            scope_frame,
            textvariable=self.scope_label_var,
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            scope_frame,
            textvariable=self.scope_detail_var,
            wraplength=460,
            justify="left",
        ).pack(anchor="w", pady=(2, 0))

        action_text = self._get_scope_action_text(self.scope_info)
        if action_text:
            self.scope_action_button = ttk.Button(
                scope_frame,
                text=action_text,
                command=self._on_scope_primary_action,
            )
            self.scope_action_button.pack(anchor="e", pady=(8, 0))

        if self.scope == "global":
            self._build_global_calibration_ui(self.calibration_section)
        else:
            self._build_project_calibration_ui(self.calibration_section)

    def _build_preferences_section(self) -> None:
        if not self.preferences_section:
            return

        self._clear_frame(self.preferences_section)
        self.preferences_section.columnconfigure(1, weight=1)

        if not self.scope_info.get("project_loaded"):
            ttk.Label(
                self.preferences_section,
                text=(
                    "Abra um projeto para ajustar pesos e OpenVINO específicos. "
                    "As preferências aplicadas aqui não afetam o padrão global."
                ),
                wraplength=440,
                justify="left",
                foreground="#555555",
            ).grid(row=0, column=0, sticky="w", padx=12, pady=12)
            return

        defaults = self.controller.get_global_model_defaults()
        overrides = self._get_current_overrides()

        heading = ttk.Label(
            self.preferences_section,
            text="Preferências do Projeto",
            font=("Segoe UI", 11, "bold"),
        )
        heading.grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(8, 4))

        weights = self.controller.get_all_weight_names()
        display_values = [self.WEIGHT_INHERIT_LABEL, *weights]

        current_weight_override = overrides.get("active_weight")
        if current_weight_override and current_weight_override not in weights:
            display_values.append(current_weight_override)

        if current_weight_override:
            self.weight_choice.set(current_weight_override)
        else:
            self.weight_choice.set(self.WEIGHT_INHERIT_LABEL)

        openvino_override = overrides.get("use_openvino")
        if openvino_override is None:
            self.openvino_choice.set(self.OPENVINO_INHERIT)
        elif bool(openvino_override):
            self.openvino_choice.set(self.OPENVINO_ON)
        else:
            self.openvino_choice.set(self.OPENVINO_OFF)

        row = 1
        ttk.Label(
            self.preferences_section,
            text=("Defina overrides deste projeto. Ao herdar, o estado global é reutilizado."),
            wraplength=440,
            justify="left",
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 8))
        row += 1

        ttk.Label(
            self.preferences_section,
            text="Peso específico deste projeto:",
        ).grid(row=row, column=0, sticky="w", padx=12)
        self.preferences_weight_dropdown = ttk.Combobox(
            self.preferences_section,
            state="readonly",
            values=display_values,
            textvariable=self.weight_choice,
        )
        self.preferences_weight_dropdown.grid(row=row, column=1, sticky="ew", padx=(0, 12))
        self.preferences_weight_dropdown.bind(
            "<<ComboboxSelected>>", lambda *_: self._update_preferences_preview()
        )
        row += 1

        openvino_frame = ttk.LabelFrame(self.preferences_section, text="OpenVINO", padding=8)
        openvino_frame.grid(row=row, column=0, columnspan=2, padx=12, pady=(12, 4), sticky="ew")
        openvino_frame.columnconfigure(0, weight=1)

        inherit_radio = ttk.Radiobutton(
            openvino_frame,
            text="Herdar configuração global",
            value=self.OPENVINO_INHERIT,
            variable=self.openvino_choice,
            command=self._update_preferences_preview,
        )
        inherit_radio.grid(row=0, column=0, sticky="w")
        ToolTip(
            inherit_radio, "Usa exatamente a configuração global do OpenVINO para este projeto."
        )

        force_on_radio = ttk.Radiobutton(
            openvino_frame,
            text="Forçar ativado",
            value=self.OPENVINO_ON,
            variable=self.openvino_choice,
            command=self._update_preferences_preview,
        )
        force_on_radio.grid(row=1, column=0, sticky="w", pady=(2, 0))
        ToolTip(force_on_radio, "Sempre usa OpenVINO neste projeto, independente do padrão global.")

        force_off_radio = ttk.Radiobutton(
            openvino_frame,
            text="Forçar desativado",
            value=self.OPENVINO_OFF,
            variable=self.openvino_choice,
            command=self._update_preferences_preview,
        )
        force_off_radio.grid(row=2, column=0, sticky="w", pady=(2, 0))
        ToolTip(
            force_off_radio,
            "Impede o uso do OpenVINO neste projeto, mesmo se estiver ativo globalmente.",
        )

        ttk.Label(
            openvino_frame,
            text=(
                "Escolha como aplicar OpenVINO neste projeto:\n"
                "• Herdar: segue o estado global atual.\n"
                "• Forçar ativado: sempre usa OpenVINO aqui.\n"
                "• Forçar desativado: mantém PyTorch mesmo que o global esteja ativo."
            ),
            justify="left",
            font=("TkDefaultFont", 9),
            foreground="#555555",
        ).grid(row=3, column=0, sticky="w", pady=(6, 0))

        row += 1
        preview = ttk.LabelFrame(self.preferences_section, text="Resultado Efetivo", padding=8)
        preview.grid(row=row, column=0, columnspan=2, padx=12, pady=(10, 6), sticky="ew")
        preview.columnconfigure(1, weight=1)

        ttk.Label(preview, text="Peso utilizado:").grid(row=0, column=0, sticky="w")
        ttk.Label(preview, textvariable=self.effective_weight_var).grid(row=0, column=1, sticky="w")
        ttk.Label(preview, text="OpenVINO:").grid(row=1, column=0, sticky="w")
        ttk.Label(preview, textvariable=self.effective_openvino_var).grid(
            row=1, column=1, sticky="w"
        )

        row += 1
        defaults_frame = ttk.LabelFrame(self.preferences_section, text="Padrões Globais", padding=8)
        defaults_frame.grid(row=row, column=0, columnspan=2, padx=12, pady=(6, 4), sticky="ew")
        ttk.Label(
            defaults_frame, text=f"Peso global: {defaults.get('active_weight') or 'Nenhum'}"
        ).pack(anchor="w")
        ttk.Label(
            defaults_frame,
            text=(
                "OpenVINO global: " + ("Ativado" if defaults.get("use_openvino") else "Desativado")
            ),
        ).pack(anchor="w", pady=(4, 0))

        row += 1
        actions = ttk.Frame(self.preferences_section)
        actions.grid(row=row, column=0, columnspan=2, sticky="e", padx=12, pady=(10, 12))
        ttk.Button(
            actions, text="Salvar Preferências", command=self._save_project_preferences
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            actions, text="Recarregar do Projeto", command=self._restore_project_preferences
        ).pack(side="left")

        self._update_preferences_preview()

    def _get_current_overrides(self) -> dict:
        project_data = getattr(self.project_manager, "project_data", {}) or {}
        return project_data.get("model_overrides", {}) or {}

    def _get_preferences_overrides(self) -> tuple[str | None, bool | None]:
        weight_selection = self.weight_choice.get()
        if weight_selection == self.WEIGHT_INHERIT_LABEL:
            weight_override = None
        else:
            weight_override = weight_selection

        openvino_selection = self.openvino_choice.get()
        if openvino_selection == self.OPENVINO_INHERIT:
            openvino_override = None
        elif openvino_selection == self.OPENVINO_ON:
            openvino_override = True
        else:
            openvino_override = False

        return weight_override, openvino_override

    def _update_preferences_preview(self) -> None:
        if not self.scope_info.get("project_loaded"):
            return

        weight_override, openvino_override = self._get_preferences_overrides()
        resolved_weight, resolved_openvino = self.controller.resolve_project_model_settings(
            {
                "active_weight": weight_override,
                "use_openvino": openvino_override,
            }
        )

        self.effective_weight_var.set(resolved_weight or "Nenhum peso disponível")
        self.effective_openvino_var.set("Ativado" if resolved_openvino else "Desativado")

    def _save_project_preferences(self) -> None:
        if not self.scope_info.get("project_loaded"):
            return

        weight_override, openvino_override = self._get_preferences_overrides()

        try:
            self.controller.save_project_model_overrides(weight_override, openvino_override)
        except ValidationError as exc:  # pragma: no cover - defensive
            messagebox.showerror("Erro", str(exc))
            return

        messagebox.showinfo("Preferências atualizadas", "As preferências do projeto foram salvas.")
        self._refresh_scope_context()

    def _restore_project_preferences(self) -> None:
        overrides = self._get_current_overrides()

        weight_override = overrides.get("active_weight")
        if weight_override:
            self.weight_choice.set(weight_override)
        else:
            self.weight_choice.set(self.WEIGHT_INHERIT_LABEL)

        openvino_override = overrides.get("use_openvino")
        if openvino_override is None:
            self.openvino_choice.set(self.OPENVINO_INHERIT)
        elif bool(openvino_override):
            self.openvino_choice.set(self.OPENVINO_ON)
        else:
            self.openvino_choice.set(self.OPENVINO_OFF)

        if self.preferences_weight_dropdown:
            self.preferences_weight_dropdown.set(self.weight_choice.get())

        self._update_preferences_preview()

    def _build_global_calibration_ui(self, master):
        model_frame = ttk.LabelFrame(master, text="Configuração do Modelo", padding=10)
        model_frame.pack(fill="x", pady=5, padx=5)
        model_frame.columnconfigure(1, weight=1)

        ttk.Label(model_frame, text="Peso Ativo:").grid(row=0, column=0, sticky="w", padx=5, pady=3)
        self.weights_dropdown = ttk.Combobox(
            model_frame, textvariable=self.active_weight_var, state="readonly"
        )
        self.weights_dropdown.grid(row=0, column=1, sticky="ew", padx=5, pady=3)
        self.weights_dropdown.bind("<<ComboboxSelected>>", self._on_weight_selected_local)
        self._populate_weights_dropdown()

        btn_frame = ttk.Frame(model_frame)
        btn_frame.grid(row=1, column=1, sticky="w", padx=5, pady=3)
        ttk.Button(
            btn_frame,
            text="Carregar Novo Peso...",
            command=self._load_new_weight_local,
        ).pack(side="left", padx=(0, 5))
        ttk.Button(btn_frame, text="Gerenciar Pesos...", command=self._manage_weights_local).pack(
            side="left"
        )

        self.openvino_checkbox = ttk.Checkbutton(
            model_frame,
            text="Otimizar com OpenVINO (para hardware Intel)",
            variable=self.use_openvino_var,
            command=self._on_openvino_toggled_local,
        )
        self.openvino_checkbox.grid(row=2, column=0, columnspan=2, sticky="w", padx=5, pady=(8, 2))

        self.openvino_status_label = ttk.Label(
            model_frame,
            textvariable=self.openvino_status_var,
            font=("Segoe UI", 8),
        )
        self.openvino_status_label.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="w",
            padx=10,
            pady=(0, 5),
        )

        self.use_openvino_var.set(self.controller.use_openvino)
        self.update_openvino_status_label(self.controller.get_openvino_status())

        diag_frame = ttk.LabelFrame(
            master,
            text="Diagnóstico de Desempenho do Modelo",
            padding=10,
        )
        diag_frame.pack(fill="x", pady=10, padx=5)

        video_frame = ttk.Frame(diag_frame)
        video_frame.pack(fill="x", padx=10, pady=5)
        ttk.Button(
            video_frame,
            text="Selecionar Vídeo...",
            command=self._select_diagnostic_video,
        ).pack(side="left")
        ttk.Label(video_frame, textvariable=self.video_path_label_var).pack(side="left", padx=5)

        self._create_detector_params_section(
            diag_frame,
            include_model_test=True,
            include_frame_count=True,
        )

        actions_frame = ttk.Frame(diag_frame)
        actions_frame.pack(fill="x", padx=10, pady=(0, 5))
        ttk.Button(
            actions_frame,
            text="Aplicar Parâmetros",
            command=lambda: self._apply_detector_parameters(scope_override="global"),
        ).pack(side="left", expand=True, fill="x")
        ttk.Button(
            actions_frame,
            text="Restaurar Padrões",
            command=lambda: self._restore_detector_defaults(scope_override="global"),
        ).pack(side="left", expand=True, fill="x", padx=(8, 0))

        ttk.Button(
            diag_frame,
            text="Testar Modelo em Vídeo...",
            command=self._run_diagnostic_test,
        ).pack(fill="x", padx=10, pady=5)

    def _build_project_calibration_ui(self, master):
        project_frame = ttk.LabelFrame(
            master,
            text="Parâmetros de Detecção do Projeto",
            padding=10,
        )
        project_frame.pack(fill="x", pady=10, padx=5)

        ttk.Label(
            project_frame,
            text=(
                "Os valores abaixo foram calibrados ao criar o projeto. "
                "Qualquer ajuste será aplicado somente a este projeto e aos pesos carregados nele."
            ),
            wraplength=460,
            justify="left",
            foreground="#4a4a4a",
        ).pack(anchor="w", padx=5, pady=(0, 6))

        self._create_detector_params_section(
            project_frame,
            include_model_test=False,
            include_frame_count=False,
        )

        actions_frame = ttk.Frame(project_frame)
        actions_frame.pack(fill="x", padx=10, pady=(8, 0))

        ttk.Button(
            actions_frame,
            text="Salvar no Projeto",
            command=lambda: self._apply_detector_parameters(scope_override="project"),
        ).pack(side="left", expand=True, fill="x")
        ttk.Button(
            actions_frame,
            text="Recarregar Valores Salvos",
            command=self._reload_project_parameters,
        ).pack(side="left", expand=True, fill="x", padx=8)
        ttk.Button(
            actions_frame,
            text="Restaurar Padrões Globais",
            command=lambda: self._restore_detector_defaults(scope_override="project"),
        ).pack(side="left", expand=True, fill="x")

    def _create_detector_params_section(
        self,
        parent,
        *,
        include_model_test: bool,
        include_frame_count: bool,
    ) -> None:
        params_frame = ttk.Frame(parent, padding=5)
        params_frame.pack(fill="x", padx=10, pady=5)

        # Configure columns: Label | Help | Entry
        params_frame.columnconfigure(1, weight=0)  # Help icon column
        params_frame.columnconfigure(2, weight=1)  # Entry column (expands)
        params_frame.columnconfigure(4, weight=0)  # Second column help
        params_frame.columnconfigure(5, weight=1)  # Second column entry

        row_idx = 0
        if include_frame_count:
            ttk.Label(params_frame, text="Nº Frames (Teste):").grid(
                row=row_idx, column=0, sticky="w", padx=(5, 2), pady=2
            )
            create_help_label(
                params_frame,
                "Quantidade de frames do vídeo a serem processados no teste de diagnóstico.\n"
                "Use um valor baixo (ex: 100) para testes rápidos.",
            ).grid(row=row_idx, column=1, padx=2)

            ttk.Entry(params_frame, textvariable=self.frames_to_analyze_var, width=8).grid(
                row=row_idx, column=2, sticky="w", padx=5
            )
            row_idx += 1

        # Confidence Threshold
        ttk.Label(params_frame, text="Limiar Confiança:").grid(
            row=row_idx, column=0, sticky="w", padx=(5, 2), pady=2
        )
        create_help_label(
            params_frame,
            "Limiar de Confiança (Confidence Threshold)\n\n"
            "Probabilidade mínima (0.0 a 1.0) para considerar uma detecção válida.\n"
            "• Aumente (ex: 0.50) se houver muitos 'falsos positivos' (ruído/fantasmas).\n"
            "• Diminua (ex: 0.15) se o peixe não estiver sendo detectado em alguns frames.\n"
            "• Padrão recomendado: 0.25",
        ).grid(row=row_idx, column=1, padx=2)

        ttk.Entry(params_frame, textvariable=self.confidence_threshold_var, width=8).grid(
            row=row_idx, column=2, sticky="w", padx=5
        )

        # NMS Threshold
        ttk.Label(params_frame, text="Limiar NMS:").grid(
            row=row_idx, column=3, sticky="w", padx=(15, 2), pady=2
        )
        create_help_label(
            params_frame,
            "Limiar NMS (Non-Maximum Suppression)\n\n"
            "Controla a remoção de caixas duplicadas para o mesmo objeto.\n"
            "• Valores baixos (ex: 0.4) fundem caixas sobrepostas agressivamente.\n"
            "• Valores altos (ex: 0.7) permitem mais sobreposição.\n"
            "• Padrão recomendado: 0.50",
        ).grid(row=row_idx, column=4, padx=2)

        ttk.Entry(params_frame, textvariable=self.nms_threshold_var, width=8).grid(
            row=row_idx, column=5, sticky="w", padx=5
        )

        row_idx += 1

        # ByteTrack Toggle
        bytetrack_check = ttk.Checkbutton(
            params_frame,
            text="Usar ByteTrack (Rastreamento Avançado)",
            variable=self.use_bytetrack_var,
            command=self._toggle_bytetrack_options,
        )
        bytetrack_check.grid(row=row_idx, column=0, columnspan=6, sticky="w", padx=5, pady=(15, 5))
        row_idx += 1

        self.bytetrack_hint_var = StringVar()
        self.bytetrack_hint_label = ttk.Label(
            params_frame,
            textvariable=self.bytetrack_hint_var,
            font=("Segoe UI", 8, "italic"),
            foreground="#555555",
            wraplength=450,
            justify="left",
        )
        self.bytetrack_hint_label.grid(
            row=row_idx, column=0, columnspan=6, sticky="w", padx=10, pady=(0, 10)
        )
        row_idx += 1

        # Tracking Params (Grouped)
        self.tracking_params_frame = ttk.Frame(params_frame)
        self.tracking_params_frame.grid(row=row_idx, column=0, columnspan=6, sticky="ew")
        self.tracking_params_frame.columnconfigure(1, weight=0)
        self.tracking_params_frame.columnconfigure(2, weight=1)
        self.tracking_params_frame.columnconfigure(4, weight=0)
        self.tracking_params_frame.columnconfigure(5, weight=1)

        # --- Row 1: Track Thresh | Match Thresh ---
        t_row = 0

        # Track Thresh
        ttk.Label(self.tracking_params_frame, text="Track Thresh:").grid(
            row=t_row, column=0, sticky="w", padx=(5, 2)
        )
        create_help_label(
            self.tracking_params_frame,
            "Track Threshold (Rastreamento)\n\n"
            "Confiança mínima para INICIAR ou MANTER um rastro.\n"
            "• Define quão 'certo' o detector deve estar para criar um ID novo.\n"
            "• Aumente para evitar rastros de lixo/ruído.\n"
            "• Diminua para manter o ID de peixes difíceis de detectar.\n"
            "• Padrão recomendado: 0.25",
        ).grid(row=t_row, column=1, padx=2)

        self.track_entry = ttk.Entry(
            self.tracking_params_frame, textvariable=self.track_threshold_var, width=8
        )
        self.track_entry.grid(row=t_row, column=2, sticky="w", padx=5)

        # Match Thresh
        ttk.Label(self.tracking_params_frame, text="Match Thresh:").grid(
            row=t_row, column=3, sticky="w", padx=(15, 2)
        )
        create_help_label(
            self.tracking_params_frame,
            "Match Threshold\n\n"
            "Tolerância para associar uma nova detecção a um rastro existente.\n"
            "• Valores altos (ex: 0.8+) são mais permissivos (bom para movimentos rápidos).\n"
            "• Valores baixos (<0.5) são restritivos "
            "(evita troca de identidade, mas pode perder o rastro).\n"
            "• Padrão recomendado: 0.95",
        ).grid(row=t_row, column=4, padx=2)

        self.match_entry = ttk.Entry(
            self.tracking_params_frame, textvariable=self.match_threshold_var, width=8
        )
        self.match_entry.grid(row=t_row, column=5, sticky="w", padx=5)

        t_row += 1

        # --- Row 2: Track Buffer | Max Dist ---

        # Track Buffer
        ttk.Label(self.tracking_params_frame, text="Track Buffer:").grid(
            row=t_row, column=0, sticky="w", padx=(5, 2), pady=5
        )
        create_help_label(
            self.tracking_params_frame,
            "Track Buffer (Memória)\n\n"
            "Quantos frames o sistema 'lembra' do peixe após ele sumir (oclusão/falha).\n"
            "• Aumente (ex: 120) se o peixe some por muito tempo.\n"
            "• Diminua para deletar rastros perdidos rapidamente.\n"
            "• Padrão: 90 frames (~3s a 30fps)",
        ).grid(row=t_row, column=1, padx=2)

        self.buffer_entry = ttk.Entry(
            self.tracking_params_frame, textvariable=self.track_buffer_var, width=8
        )
        self.buffer_entry.grid(row=t_row, column=2, sticky="w", padx=5)

        # Max Dist
        ttk.Label(self.tracking_params_frame, text="Dist. Máx (px):").grid(
            row=t_row, column=3, sticky="w", padx=(15, 2)
        )
        create_help_label(
            self.tracking_params_frame,
            "Distância Máxima (pixels)\n\n"
            "O quanto o centro do peixe pode se mover entre frames processados.\n"
            "• Impede associações impossíveis (teletransporte).\n"
            "• Aumente se o peixe é rápido ou se a taxa de frames é baixa.\n"
            "• Diminua se houver trocas de ID entre peixes distantes.\n"
            "• Padrão: 400.0 px",
        ).grid(row=t_row, column=4, padx=2)

        self.dist_entry = ttk.Entry(
            self.tracking_params_frame, textvariable=self.max_center_dist_var, width=8
        )
        self.dist_entry.grid(row=t_row, column=5, sticky="w", padx=5)

        t_row += 1

        # --- Row 3: IoU Thresh ---

        # IoU Thresh
        ttk.Label(self.tracking_params_frame, text="IoU Thresh:").grid(
            row=t_row, column=0, sticky="w", padx=(5, 2)
        )
        create_help_label(
            self.tracking_params_frame,
            "IoU Threshold (Rastreamento)\n\n"
            "Sobreposição mínima (Intersection over Union) para associar caixas.\n"
            "• Padrão: 0.05 (baixa exigência).\n"
            "• Aumente (ex: 0.3) para exigir que o peixe mantenha quase a mesma posição.\n"
            "• Diminua para permitir movimentos bruscos que mudam a área da caixa.",
        ).grid(row=t_row, column=1, padx=2)

        self.iou_entry = ttk.Entry(
            self.tracking_params_frame, textvariable=self.iou_threshold_var, width=8
        )
        self.iou_entry.grid(row=t_row, column=2, sticky="w", padx=5)

        row_idx += 1

        if include_model_test:
            ttk.Label(params_frame, text="Modelo(s) a Testar:").grid(
                row=row_idx, column=0, sticky="w", padx=5, pady=(15, 2)
            )
            self.model_test_dropdown = ttk.Combobox(
                params_frame,
                textvariable=self.model_test_var,
                state="readonly",
                values=["YOLO (PyTorch)", "OpenVINO", "Ambos"],
                width=15,
            )
            self.model_test_dropdown.grid(
                row=row_idx, column=1, columnspan=2, sticky="w", padx=5, pady=(15, 2)
            )
        else:
            self.model_test_dropdown = None

        self._toggle_bytetrack_options()

    def _toggle_bytetrack_options(self) -> None:
        """Enable/Disable tracking inputs based on checkbox."""
        # Guard: widgets may not exist during initialization
        if not hasattr(self, "track_entry") or self.track_entry is None:
            return

        enabled = self.use_bytetrack_var.get()
        state = "normal" if enabled else "disabled"
        for widget in [
            self.track_entry,
            self.match_entry,
            self.buffer_entry,
            self.dist_entry,
            self.iou_entry,
        ]:
            try:
                widget.configure(state=state)
            except Exception:
                log.debug("calibration_dialog.widget_state_config.suppressed", exc_info=True)

        if not enabled:
            self.bytetrack_hint_var.set(
                "ℹ️ ByteTrack desativado. Usando rastreamento simples (Híbrido) "
                "que utiliza apenas 'Distância Máxima' e 'IoU Threshold' para manter o ID."
            )
            # Distance and IoU are used by Simple Tracker
            for widget in [self.dist_entry, self.iou_entry]:
                try:
                    widget.configure(state="normal")
                except Exception:
                    log.debug("calibration_dialog.widget_reenable.suppressed", exc_info=True)
        else:
            self.bytetrack_hint_var.set(
                "💡 ByteTrack ativo (Filtro de Kalman). Recomendado para maior estabilidade."
            )

    def _prefill_detector_parameters(self) -> None:
        resolved_params, project_params = self._collect_prefill_detector_params()
        if not resolved_params:
            return

        self._set_parameter_fields(resolved_params)

        if project_params and self.scope_info.get("scope") == "project":
            project_name = self.scope_info.get("project_name")
            label = (
                f"Escopo: Projeto ({project_name}) - Overrides Locais"
                if project_name
                else ("Escopo: Projeto - Overrides Locais")
            )
            self.scope_label_var.set(label)
            self.scope_detail_var.set(
                "Os parâmetros exibidos correspondem às preferências deste projeto. "
                "Ajustes aplicados aqui atualizam apenas este projeto."
            )

    def _collect_prefill_detector_params(self) -> tuple[dict[str, Any], dict[str, Any]]:
        def _extract_params(source: dict | None) -> dict[str, Any]:
            mapping = {
                "confidence_threshold": "confidence_threshold",
                "conf_threshold": "confidence_threshold",
                "nms_threshold": "nms_threshold",
                "track_threshold": "track_threshold",
                "match_threshold": "match_threshold",
                "track_buffer": "track_buffer",
                "max_center_distance": "max_center_distance",
                "iou_threshold": "iou_threshold",
                "use_bytetrack": "use_bytetrack",
            }

            resolved: dict[str, Any] = {}
            if not source:
                return resolved

            for key, target in mapping.items():
                if key not in source:
                    continue
                try:
                    if target == "use_bytetrack":
                        resolved[target] = bool(source[key])
                    elif target == "track_buffer":
                        resolved[target] = int(source[key])
                    else:
                        resolved[target] = float(source[key])
                except (TypeError, ValueError):
                    log.warning(
                        "ui.calibration.prefill.invalid_param",
                        key=key,
                        value=source[key],
                    )
            return resolved

        project_data = getattr(self.controller.project_manager, "project_data", {}) or {}
        overrides = project_data.get("model_overrides") or {}

        project_params = _extract_params(overrides.get("detector_parameters"))
        if not project_params:
            project_params = _extract_params(project_data.get("detector_config"))
        if not project_params:
            project_params = _extract_params(project_data.get("detector_state"))

        try:
            params = self.controller.get_current_detector_parameters()
        except Exception:
            log.debug("calibration.get_detector_params.fallback")
            params = {}

        resolved_params = _extract_params(params)
        if project_params:
            resolved_params.update(project_params)

        return resolved_params, project_params

    def _set_parameter_fields(self, values: dict[str, Any]) -> None:
        field_map = {
            "confidence_threshold": self.confidence_threshold_var,
            "nms_threshold": self.nms_threshold_var,
            "track_threshold": self.track_threshold_var,
            "match_threshold": self.match_threshold_var,
            "track_buffer": self.track_buffer_var,
            "max_center_distance": self.max_center_dist_var,
            "iou_threshold": self.iou_threshold_var,
        }

        for key, var in field_map.items():
            raw_value = values.get(key)
            if raw_value is None:
                continue
            try:
                if key == "track_buffer":
                    var.set(str(int(raw_value)))
                else:
                    var.set(
                        f"{float(raw_value):.2f}"
                        if isinstance(raw_value, float)
                        else str(raw_value)
                    )
            except (TypeError, ValueError):
                log.warning("ui.calibration.prefill.coerce_failed", key=key, value=raw_value)

        if "use_bytetrack" in values:
            self.use_bytetrack_var.set(bool(values["use_bytetrack"]))
            self._toggle_bytetrack_options()

    def _reload_project_parameters(self) -> None:
        _, project_params = self._collect_prefill_detector_params()
        if not project_params:
            messagebox.showinfo(
                "Sem overrides",
                "Este projeto ainda não possui overrides salvos. "
                "Valores globais atuais serão mantidos.",
            )
            return

        self._set_parameter_fields(project_params)

    def _apply_detector_parameters(self, scope_override: str | None = None) -> None:
        scope = scope_override or self.scope
        try:
            conf = float(self.confidence_threshold_var.get())
            nms = float(self.nms_threshold_var.get())

            use_bytetrack = self.use_bytetrack_var.get()
            track_thresh = float(self.track_threshold_var.get())
            match_thresh = float(self.match_threshold_var.get())
            track_buffer = int(self.track_buffer_var.get())
            max_dist = float(self.max_center_dist_var.get())
            iou_thresh = float(self.iou_threshold_var.get())
        except (TypeError, ValueError):
            messagebox.showerror(
                "Erro",
                "Insira valores numéricos válidos para os parâmetros do detector.",
            )
            return

        for label, value in (
            ("limiar de confiança", conf),
            ("limiar NMS", nms),
            ("track threshold", track_thresh),
            ("match threshold", match_thresh),
            ("IoU threshold", iou_thresh),
        ):
            if not 0.0 < value < 1.0:
                messagebox.showerror(
                    "Erro",
                    f"O {label} deve estar entre 0 e 1.",
                )
                return

        if track_buffer < 1:
            messagebox.showerror("Erro", "Track Buffer deve ser pelo menos 1 frame.")
            return
        if max_dist <= 0:
            messagebox.showerror("Erro", "Distância Máxima deve ser maior que 0.")
            return

        try:
            updated = self.controller.update_detector_parameters(
                {
                    "confidence_threshold": conf,
                    "nms_threshold": nms,
                    "use_bytetrack": use_bytetrack,
                    "track_threshold": track_thresh,
                    "match_threshold": match_thresh,
                    "track_buffer": track_buffer,
                    "max_center_distance": max_dist,
                    "iou_threshold": iou_thresh,
                    "scope": scope,
                }
            )
        except ValidationError as exc:  # pragma: no cover - defensive
            messagebox.showerror("Erro", str(exc))
            return

        if updated:
            messagebox.showinfo(
                "Parâmetros Atualizados",
                "As configurações do detector foram aplicadas com sucesso.",
            )
        else:
            messagebox.showwarning(
                "Sem alterações",
                "Os parâmetros informados já estavam em uso.",
            )

    def _restore_detector_defaults(self, scope_override: str | None = None) -> None:
        scope = scope_override or self.scope
        try:
            restored = self.controller.restore_detector_defaults(scope=scope)
        except Exception as exc:  # pragma: no cover - defensive
            messagebox.showerror("Erro", str(exc))
            return

        if restored:
            resolved_params, _ = self._collect_prefill_detector_params()
            self._set_parameter_fields(resolved_params)
            messagebox.showinfo(
                "Parâmetros do Detector",
                "Parâmetros padrão restaurados.",
            )

    def _populate_weights_dropdown(self):
        if not self.weights_dropdown:
            return
        weights_list = self.controller.get_all_weight_names()
        self.weights_dropdown["values"] = weights_list
        if not weights_list:
            self.active_weight_var.set("Nenhum peso encontrado.")
            self.weights_dropdown.config(state="disabled")
        else:
            self.weights_dropdown.config(state="readonly")
            current_weight = self.controller.active_weight_name
            if current_weight in weights_list:
                self.active_weight_var.set(current_weight)
            elif weights_list:
                self.active_weight_var.set(weights_list[0])

    def _on_weight_selected_local(self, event=None):
        selected_weight = self.active_weight_var.get()
        self.controller.ui_event_bus.publish_event(
            Events.MODEL_SET_WEIGHT, {"name": selected_weight, "dialog": self}
        )

    def _on_openvino_toggled_local(self):
        self.controller.ui_event_bus.publish_event(
            Events.MODEL_SET_OPENVINO,
            {"use_openvino": self.use_openvino_var.get(), "dialog": self},
        )

    def update_openvino_status_label(self, status: str):
        """Update the OpenVINO status label with current status.

        Args:
            status: Status string to display.
        """
        self.openvino_status_var.set(status)
        if not self.openvino_status_label:
            return

    def _load_new_weight_local(self):
        if not self.weights_dropdown:
            return
        self.controller.ui_event_bus.publish_event(Events.UI_REQUEST_WEIGHT_FILE, {})
        self._populate_weights_dropdown()

    def _manage_weights_local(self):
        if not self.weights_dropdown:
            return

        def refresh_callback():
            self._populate_weights_dropdown()

        ManageWeightsDialog(self.master, self.controller, refresh_callback)

    def _select_diagnostic_video(self):
        path = filedialog.askopenfilename(
            title="Selecione o Vídeo para Diagnóstico",
            filetypes=[("Arquivos de vídeo", "*.mp4 *.avi *.mov")],
        )
        if path:
            self.diagnostic_video_path = path
            self.video_path_label_var.set(os.path.basename(path))

    def _run_diagnostic_test(self):
        if not self.diagnostic_video_path:
            messagebox.showerror("Erro", "Por favor, selecione um arquivo de vídeo.")
            return

        try:
            frames = int(self.frames_to_analyze_var.get())
            if frames <= 0:
                messagebox.showerror("Erro", "O número de frames deve ser um inteiro positivo.")
                return
        except ValueError:
            messagebox.showerror("Erro", "O número de frames deve ser um número inteiro.")
            return

        try:
            conf = float(self.confidence_threshold_var.get())
            if not 0.0 <= conf <= 1.0:
                messagebox.showerror(
                    "Erro", "O limiar de confiança deve ser um número entre 0.0 e 1.0."
                )
                return
        except ValueError:
            messagebox.showerror("Erro", "O limiar de confiança deve ser um número válido.")
            return

        config = {
            "video_path": self.diagnostic_video_path,
            "frames_to_analyze": int(self.frames_to_analyze_var.get()),
            "confidence_threshold": float(self.confidence_threshold_var.get()),
            "model_to_test": self.model_test_var.get(),
            "parent_dialog": self,
        }

        self.controller.ui_event_bus.publish_event(Events.MODEL_RUN_DIAGNOSTIC, {"config": config})

    def buttonbox(self):
        """Create custom button box with calibration action buttons."""
        box = ttk.Frame(self)
        w = ttk.Button(box, text="Fechar", width=10, command=self.ok, default="active")
        w.pack(side="left", padx=5, pady=5)
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)
        box.pack()

    def _get_scope_action_text(self, scope_info: dict) -> str | None:
        if not scope_info.get("project_loaded"):
            return None
        if scope_info.get("scope") == "global":
            return "Copiar globais para o projeto"
        return "Salvar calibração neste projeto"

    def _refresh_scope_context(self) -> None:
        self.scope_info = self.controller.get_calibration_scope_info()
        self.scope = self.scope_info.get("scope", self.scope)
        self.scope_label_var.set(self.scope_info["label"])
        self.scope_detail_var.set(self.scope_info["detail"])

        if self.calibration_section:
            self._build_calibration_section()

        if self.preferences_section:
            project_ready = self.scope == "project" and self.scope_info.get("project_loaded")
            if project_ready:
                # Preferences section is managed by CollapsibleFrame, just rebuild content
                self._build_preferences_section()
            else:
                self._clear_frame(self.preferences_section)

        if self.scope_action_button:
            action_text = self._get_scope_action_text(self.scope_info)
            if action_text:
                self.scope_action_button.config(text=action_text, state="normal")
            else:
                self.scope_action_button.config(state="disabled")

    def _on_scope_primary_action(self) -> None:
        if not self.scope_info.get("project_loaded"):
            return

        project_name = self.scope_info.get("project_name") or "projeto"
        if self.scope_info.get("scope") == "global":
            self.controller.ui_event_bus.publish_event(Events.CALIBRATION_COPY_TO_PROJECT, {})
            result = True
            if result:
                messagebox.showinfo(
                    "Projeto atualizado",
                    f"Os padrões globais foram copiados para o projeto {project_name}.",
                )
        else:
            self.controller.ui_event_bus.publish_event(Events.CALIBRATION_SAVE_TO_PROJECT, {})
            result = True
            if result:
                messagebox.showinfo(
                    "Overrides salvos",
                    f"A calibração atual foi salva como override para o projeto {project_name}.",
                )

        self._populate_weights_dropdown()
        self.use_openvino_var.set(self.controller.use_openvino)
        self._refresh_scope_context()
