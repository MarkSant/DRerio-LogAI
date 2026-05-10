"""Reusable diagnostics panel for global and project model workflows."""

from __future__ import annotations

import os
from tkinter import BooleanVar, StringVar, filedialog, messagebox, ttk
from typing import Any

import structlog
from pydantic import ValidationError

from zebtrack.ui import payloads
from zebtrack.ui.event_bus_v2 import Event, UIEvents
from zebtrack.ui.payloads import ModelRunDiagnosticPayload, ModelSetWeightPayload
from zebtrack.ui.wizard.tooltip import create_help_label

log = structlog.get_logger()


class ModelDiagnosticsPanel(ttk.Frame):
    """Focused diagnostics controls reusable across dialogs and tabs."""

    SLOT_SEPARATOR = ":"

    def __init__(
        self,
        parent,
        controller,
        *,
        scope: str = "global",
        parent_dialog: Any | None = None,
    ) -> None:
        super().__init__(parent, padding=10)
        self.controller = controller
        self.project_manager = controller.project_manager
        self.scope = scope
        self.parent_dialog = parent_dialog

        self.active_weight_var = StringVar(master=self)
        self.frames_to_analyze_var = StringVar(master=self, value="10")
        self.confidence_threshold_var = StringVar(master=self, value="0.25")
        self.nms_threshold_var = StringVar(master=self, value="0.50")
        self.use_bytetrack_var = BooleanVar(master=self, value=True)
        self.track_threshold_var = StringVar(master=self, value="0.25")
        self.match_threshold_var = StringVar(master=self, value="0.95")
        self.track_buffer_var = StringVar(master=self, value="90")
        self.max_center_dist_var = StringVar(master=self, value="400.0")
        self.iou_threshold_var = StringVar(master=self, value="0.05")
        self.video_path_label_var = StringVar(master=self, value="Nenhum vídeo selecionado.")
        self.model_test_var = StringVar(master=self, value="YOLO (PyTorch)")
        self.project_weight_summary_var = StringVar(master=self)
        self.project_weight_options: dict[str, str] = {}

        self.diagnostic_video_path = ""
        self.weights_dropdown: ttk.Combobox | None = None
        self.model_test_dropdown: ttk.Combobox | None = None
        self.bytetrack_hint_var = StringVar(master=self)
        self.bytetrack_hint_label: ttk.Label | None = None
        self.track_entry: ttk.Entry | None = None
        self.match_entry: ttk.Entry | None = None
        self.buffer_entry: ttk.Entry | None = None
        self.dist_entry: ttk.Entry | None = None
        self.iou_entry: ttk.Entry | None = None

        self._prefill_detector_parameters()
        self._build()

    def refresh_weight_options(self) -> None:
        """Refresh the global weight dropdown after catalog changes elsewhere."""
        if self.scope == "global":
            self._populate_weights_dropdown()
            return
        self._refresh_project_weight_summary()
        self._populate_project_weights_dropdown()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)

        title = "Diagnóstico Global" if self.scope == "global" else "Diagnóstico do Projeto"
        ttk.Label(self, text=title, font=("Segoe UI", 11, "bold")).pack(anchor="w")

        if self.scope == "global":
            ttk.Label(
                self,
                text=(
                    "Use este painel para validar pesos, ajustar parâmetros do detector "
                    "e executar testes rápidos em vídeo fora do contexto de um projeto."
                ),
                justify="left",
                wraplength=760,
                foreground="#555555",
            ).pack(anchor="w", pady=(2, 10))
            self._build_weight_selector()
        else:
            self._refresh_project_weight_summary()
            ttk.Label(
                self,
                text=(
                    "Ajustes feitos aqui afetam apenas os parâmetros do detector deste projeto. "
                    "Escolha abaixo qual peso efetivo do projeto deseja diagnosticar."
                ),
                justify="left",
                wraplength=760,
                foreground="#555555",
            ).pack(anchor="w", pady=(2, 2))
            self._build_project_weight_selector()
            ttk.Label(
                self,
                textvariable=self.project_weight_summary_var,
                justify="left",
                wraplength=760,
            ).pack(anchor="w", pady=(0, 10))

        self._build_video_selector()
        self._create_detector_params_section(include_model_test=True, include_frame_count=True)
        self._build_actions()

        ttk.Button(
            self,
            text="Testar Modelo em Vídeo...",
            command=self._run_diagnostic_test,
        ).pack(fill="x", pady=(6, 0))

    def _build_weight_selector(self) -> None:
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(0, 6))
        row.columnconfigure(1, weight=1)

        ttk.Label(row, text="Peso para diagnóstico:").grid(row=0, column=0, sticky="w")
        self.weights_dropdown = ttk.Combobox(
            row,
            textvariable=self.active_weight_var,
            state="readonly",
        )
        self.weights_dropdown.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self.weights_dropdown.bind("<<ComboboxSelected>>", self._on_weight_selected_local)

        ttk.Label(
            self,
            text=(
                "O peso escolhido aqui é aplicado temporariamente como peso ativo para o teste. "
                "A configuração global permanente continua sendo controlada pela janela de "
                "Configuração Global de Modelos."
            ),
            font=("Segoe UI", 8),
            foreground="#555555",
            wraplength=760,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        self._populate_weights_dropdown()

    def _build_project_weight_selector(self) -> None:
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(0, 6))
        row.columnconfigure(1, weight=1)

        ttk.Label(row, text="Peso do projeto para diagnóstico:").grid(
            row=0,
            column=0,
            sticky="w",
        )
        self.weights_dropdown = ttk.Combobox(
            row,
            textvariable=self.active_weight_var,
            state="readonly",
        )
        self.weights_dropdown.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self._populate_project_weights_dropdown()

    def _build_video_selector(self) -> None:
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(0, 6))
        row.columnconfigure(1, weight=1)

        ttk.Button(
            row,
            text="Selecionar Vídeo...",
            command=self._select_diagnostic_video,
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            row,
            textvariable=self.video_path_label_var,
            wraplength=700,
            justify="left",
        ).grid(row=0, column=1, sticky="ew", padx=(8, 0))

    def _build_actions(self) -> None:
        actions_frame = ttk.Frame(self)
        actions_frame.pack(fill="x", pady=(6, 0))

        if self.scope == "project":
            for col in range(3):
                actions_frame.columnconfigure(col, weight=1, uniform="diag_project_actions")

            ttk.Button(
                actions_frame,
                text="Salvar no Projeto",
                command=self._apply_detector_parameters,
            ).grid(row=0, column=0, sticky="ew")
            ttk.Button(
                actions_frame,
                text="Recarregar Valores Salvos",
                command=self._reload_project_parameters,
            ).grid(row=0, column=1, sticky="ew", padx=8)
            ttk.Button(
                actions_frame,
                text="Restaurar Padrões Globais",
                command=self._restore_detector_defaults,
            ).grid(row=0, column=2, sticky="ew")
            return

        actions_frame.columnconfigure(0, weight=1, uniform="diag_global_actions")
        actions_frame.columnconfigure(1, weight=1, uniform="diag_global_actions")
        ttk.Button(
            actions_frame,
            text="Aplicar Parâmetros",
            command=self._apply_detector_parameters,
        ).grid(row=0, column=0, sticky="ew")
        ttk.Button(
            actions_frame,
            text="Restaurar Padrões",
            command=self._restore_detector_defaults,
        ).grid(row=0, column=1, sticky="ew", padx=(8, 0))

    def _create_detector_params_section(
        self,
        *,
        include_model_test: bool,
        include_frame_count: bool,
    ) -> None:
        params_frame = ttk.Frame(self, padding=5)
        params_frame.pack(fill="x", pady=5)

        params_frame.columnconfigure(0, weight=0)
        params_frame.columnconfigure(1, weight=0)
        params_frame.columnconfigure(2, weight=1)
        params_frame.columnconfigure(3, weight=0)
        params_frame.columnconfigure(4, weight=0)
        params_frame.columnconfigure(5, weight=1)

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
                row=row_idx, column=2, sticky="ew", padx=5
            )
            row_idx += 1

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
            row=row_idx, column=2, sticky="ew", padx=5
        )

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
            row=row_idx, column=5, sticky="ew", padx=5
        )

        row_idx += 1

        ttk.Checkbutton(
            params_frame,
            text="Usar ByteTrack (Rastreamento Avançado)",
            variable=self.use_bytetrack_var,
            command=self._toggle_bytetrack_options,
        ).grid(row=row_idx, column=0, columnspan=6, sticky="w", padx=5, pady=(15, 5))
        row_idx += 1

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

        tracking_frame = ttk.Frame(params_frame)
        tracking_frame.grid(row=row_idx, column=0, columnspan=6, sticky="ew")
        tracking_frame.columnconfigure(0, weight=0)
        tracking_frame.columnconfigure(1, weight=0)
        tracking_frame.columnconfigure(2, weight=1)
        tracking_frame.columnconfigure(3, weight=0)
        tracking_frame.columnconfigure(4, weight=0)
        tracking_frame.columnconfigure(5, weight=1)

        t_row = 0
        ttk.Label(tracking_frame, text="Track Thresh:").grid(
            row=t_row, column=0, sticky="w", padx=(5, 2)
        )
        create_help_label(
            tracking_frame,
            "Track Threshold (Rastreamento)\n\n"
            "Confiança mínima para INICIAR ou MANTER um rastro.\n"
            "• Define quão 'certo' o detector deve estar para criar um ID novo.\n"
            "• Aumente para evitar rastros de lixo/ruído.\n"
            "• Diminua para manter o ID de peixes difíceis de detectar.\n"
            "• Padrão recomendado: 0.25",
        ).grid(row=t_row, column=1, padx=2)
        self.track_entry = ttk.Entry(tracking_frame, textvariable=self.track_threshold_var, width=8)
        self.track_entry.grid(row=t_row, column=2, sticky="ew", padx=5)

        ttk.Label(tracking_frame, text="Match Thresh:").grid(
            row=t_row, column=3, sticky="w", padx=(15, 2)
        )
        create_help_label(
            tracking_frame,
            "Match Threshold\n\n"
            "Tolerância para associar uma nova detecção a um rastro existente.\n"
            "• Valores altos (ex: 0.8+) são mais permissivos (bom para movimentos rápidos).\n"
            "• Valores baixos (<0.5) são restritivos "
            "(evita troca de identidade, mas pode perder o rastro).\n"
            "• Padrão recomendado: 0.95",
        ).grid(row=t_row, column=4, padx=2)
        self.match_entry = ttk.Entry(tracking_frame, textvariable=self.match_threshold_var, width=8)
        self.match_entry.grid(row=t_row, column=5, sticky="ew", padx=5)

        t_row += 1
        ttk.Label(tracking_frame, text="Track Buffer:").grid(
            row=t_row, column=0, sticky="w", padx=(5, 2), pady=5
        )
        create_help_label(
            tracking_frame,
            "Track Buffer (Memória)\n\n"
            "Quantos frames o sistema 'lembra' do peixe após ele sumir (oclusão/falha).\n"
            "• Aumente (ex: 120) se o peixe some por muito tempo.\n"
            "• Diminua para deletar rastros perdidos rapidamente.\n"
            "• Padrão: 90 frames (~3s a 30fps)",
        ).grid(row=t_row, column=1, padx=2)
        self.buffer_entry = ttk.Entry(tracking_frame, textvariable=self.track_buffer_var, width=8)
        self.buffer_entry.grid(row=t_row, column=2, sticky="ew", padx=5)

        ttk.Label(tracking_frame, text="Dist. Máx (px):").grid(
            row=t_row, column=3, sticky="w", padx=(15, 2)
        )
        create_help_label(
            tracking_frame,
            "Distância Máxima (pixels)\n\n"
            "O quanto o centro do peixe pode se mover entre frames processados.\n"
            "• Impede associações impossíveis (teletransporte).\n"
            "• Aumente se o peixe é rápido ou se a taxa de frames é baixa.\n"
            "• Diminua se houver trocas de ID entre peixes distantes.\n"
            "• Padrão: 400.0 px",
        ).grid(row=t_row, column=4, padx=2)
        self.dist_entry = ttk.Entry(tracking_frame, textvariable=self.max_center_dist_var, width=8)
        self.dist_entry.grid(row=t_row, column=5, sticky="ew", padx=5)

        t_row += 1
        ttk.Label(tracking_frame, text="IoU Thresh:").grid(
            row=t_row, column=0, sticky="w", padx=(5, 2)
        )
        create_help_label(
            tracking_frame,
            "IoU Threshold (Rastreamento)\n\n"
            "Sobreposição mínima (Intersection over Union) para associar caixas.\n"
            "• Padrão: 0.05 (baixa exigência).\n"
            "• Aumente (ex: 0.3) para exigir que o peixe mantenha quase a mesma posição.\n"
            "• Diminua para permitir movimentos bruscos que mudam a área da caixa.",
        ).grid(row=t_row, column=1, padx=2)
        self.iou_entry = ttk.Entry(tracking_frame, textvariable=self.iou_threshold_var, width=8)
        self.iou_entry.grid(row=t_row, column=2, sticky="ew", padx=5)

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
                row=row_idx, column=1, columnspan=5, sticky="ew", padx=5, pady=(15, 2)
            )

        self._toggle_bytetrack_options()

    def _toggle_bytetrack_options(self) -> None:
        if not self.track_entry:
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
            if widget is None:
                continue
            widget.configure(state=state)

        if not enabled:
            self.bytetrack_hint_var.set(
                "ℹ️ ByteTrack desativado. Usando rastreamento simples (Híbrido) que utiliza "
                "apenas 'Distância Máxima' e 'IoU Threshold' para manter o ID."
            )
            for widget in [self.dist_entry, self.iou_entry]:
                if widget is not None:
                    widget.configure(state="normal")
            return

        self.bytetrack_hint_var.set(
            "💡 ByteTrack ativo (Filtro de Kalman). Recomendado para maior estabilidade."
        )

    def _prefill_detector_parameters(self) -> None:
        resolved_params, _ = self._collect_prefill_detector_params()
        if resolved_params:
            self._set_parameter_fields(resolved_params)

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
                        "ui.model_diagnostics.prefill.invalid_param",
                        key=key,
                        value=source[key],
                    )
            return resolved

        project_data = getattr(self.project_manager, "project_data", {}) or {}
        overrides = project_data.get("model_overrides") or {}

        project_params = _extract_params(overrides.get("detector_parameters"))
        if not project_params:
            project_params = _extract_params(project_data.get("detector_config"))
        if not project_params:
            project_params = _extract_params(project_data.get("detector_state"))

        try:
            params = self.controller.hardware_vm.get_current_detector_parameters()
        except Exception:
            log.debug("model_diagnostics_panel.get_detector_params.fallback", exc_info=True)
            params = {}

        resolved_params = _extract_params(params)
        if self.scope == "project" and project_params:
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
                log.warning(
                    "ui.model_diagnostics.prefill.coerce_failed",
                    key=key,
                    value=raw_value,
                )

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
                parent=self,
            )
            return

        self._set_parameter_fields(project_params)

    def _apply_detector_parameters(self) -> None:
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
                parent=self,
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
                messagebox.showerror("Erro", f"O {label} deve estar entre 0 e 1.", parent=self)
                return

        if track_buffer < 1:
            messagebox.showerror("Erro", "Track Buffer deve ser pelo menos 1 frame.", parent=self)
            return
        if max_dist <= 0:
            messagebox.showerror("Erro", "Distância Máxima deve ser maior que 0.", parent=self)
            return

        try:
            updated = self.controller.hardware_vm.update_detector_parameters(
                {
                    "confidence_threshold": conf,
                    "nms_threshold": nms,
                    "use_bytetrack": use_bytetrack,
                    "track_threshold": track_thresh,
                    "match_threshold": match_thresh,
                    "track_buffer": track_buffer,
                    "max_center_distance": max_dist,
                    "iou_threshold": iou_thresh,
                    "scope": self.scope,
                }
            )
        except ValidationError as exc:
            messagebox.showerror("Erro", str(exc), parent=self)
            return

        if updated:
            success_message = (
                "As configurações do detector foram salvas para este projeto."
                if self.scope == "project"
                else "As configurações do detector foram aplicadas com sucesso."
            )
            messagebox.showinfo("Parâmetros Atualizados", success_message, parent=self)
        else:
            messagebox.showwarning(
                "Sem alterações",
                "Os parâmetros informados já estavam em uso.",
                parent=self,
            )

    def _restore_detector_defaults(self) -> None:
        try:
            restored = self.controller.hardware_vm.restore_detector_defaults(scope=self.scope)
        except Exception as exc:
            messagebox.showerror("Erro", str(exc), parent=self)
            return

        if restored:
            resolved_params, _ = self._collect_prefill_detector_params()
            self._set_parameter_fields(resolved_params)
            messagebox.showinfo(
                "Parâmetros do Detector",
                "Parâmetros padrão restaurados.",
                parent=self,
            )

    def _populate_weights_dropdown(self) -> None:
        if not self.weights_dropdown:
            return
        weights_list = self.controller.hardware_vm.get_all_weight_names()
        self.weights_dropdown["values"] = weights_list
        if not weights_list:
            self.active_weight_var.set("Nenhum peso encontrado.")
            self.weights_dropdown.config(state="disabled")
            return

        self.weights_dropdown.config(state="readonly")
        current_weight = self.controller.hardware_vm.active_weight_name
        if current_weight in weights_list:
            self.active_weight_var.set(current_weight)
        else:
            self.active_weight_var.set(weights_list[0])

    @classmethod
    def _slot_key(cls, method: str, target: str) -> str:
        return f"{method}{cls.SLOT_SEPARATOR}{target}"

    def _get_project_slot_entries(self) -> list[dict[str, str | None]]:
        summary_getter = getattr(self.controller.hardware_vm, "get_default_weights_summary", None)
        if not callable(summary_getter):
            return []

        overrides = getattr(self.project_manager, "project_data", {}) or {}
        model_overrides = overrides.get("model_overrides") or {}
        slot_weights = model_overrides.get("slot_weights") or {}
        normalized_slot_weights: dict[str, str] = {}
        if isinstance(slot_weights, dict):
            for key, value in slot_weights.items():
                if isinstance(key, str) and isinstance(value, str) and value.strip():
                    normalized_slot_weights[key] = value.strip()

        legacy_weight = model_overrides.get("active_weight")
        entries: list[dict[str, str | None]] = []
        for label, method, target, global_weight in summary_getter(scope="project"):
            slot_key = self._slot_key(method, target)
            if target == "zebrafish" and isinstance(legacy_weight, str) and legacy_weight.strip():
                normalized_slot_weights.setdefault(slot_key, legacy_weight.strip())
            project_override = normalized_slot_weights.get(slot_key)
            entries.append(
                {
                    "key": slot_key,
                    "label": label,
                    "effective_weight": project_override or global_weight,
                    "project_override": project_override,
                }
            )
        return entries

    def _populate_project_weights_dropdown(self) -> None:
        if not self.weights_dropdown:
            return

        self.project_weight_options = {}
        for entry in self._get_project_slot_entries():
            effective_weight = entry.get("effective_weight")
            if not effective_weight:
                continue
            display = f"{entry['label']}: {effective_weight}"
            self.project_weight_options[display] = effective_weight

        values = list(self.project_weight_options.keys())
        self.weights_dropdown["values"] = values
        if not values:
            self.weights_dropdown.config(state="disabled")
            self.active_weight_var.set("Nenhum peso efetivo disponível.")
            return

        self.weights_dropdown.config(state="readonly")
        current_selection = self.active_weight_var.get()
        if current_selection in self.project_weight_options:
            return
        self.active_weight_var.set(values[0])

    def _refresh_project_weight_summary(self) -> None:
        entries = self._get_project_slot_entries()
        try:
            _resolved_weight, resolved_openvino = (
                self.controller.project_vm.resolve_project_model_settings({})
            )
        except Exception:
            resolved_openvino = False

        lines = ["Pesos efetivos deste projeto:"]
        for entry in entries:
            label = entry.get("label") or "Slot"
            effective_weight = entry.get("effective_weight") or "Nenhum"
            if entry.get("project_override"):
                lines.append(f"{label}: {effective_weight} (override do projeto)")
            else:
                lines.append(f"{label}: {effective_weight} (padrão global)")
        lines.append(f"OpenVINO: {'Ativado' if resolved_openvino else 'Desativado'}")
        self.project_weight_summary_var.set("\n".join(lines))

    def _on_weight_selected_local(self, _event=None) -> None:
        selected_weight = self.active_weight_var.get()
        self._publish_event(
            UIEvents.MODEL_SET_WEIGHT,
            ModelSetWeightPayload(name=selected_weight, dialog=None),
        )

    def _select_diagnostic_video(self) -> None:
        path = filedialog.askopenfilename(
            title="Selecione o Vídeo para Diagnóstico",
            filetypes=[("Arquivos de vídeo", "*.mp4 *.avi *.mov")],
            parent=self,
        )
        if not path:
            return

        self.diagnostic_video_path = path
        self.video_path_label_var.set(os.path.basename(path))

    def _run_diagnostic_test(self) -> None:
        if not self.diagnostic_video_path:
            messagebox.showerror("Erro", "Por favor, selecione um arquivo de vídeo.", parent=self)
            return

        try:
            frames = int(self.frames_to_analyze_var.get())
            if frames <= 0:
                messagebox.showerror(
                    "Erro",
                    "O número de frames deve ser um inteiro positivo.",
                    parent=self,
                )
                return
        except ValueError:
            messagebox.showerror(
                "Erro",
                "O número de frames deve ser um número inteiro.",
                parent=self,
            )
            return

        try:
            conf = float(self.confidence_threshold_var.get())
            if not 0.0 <= conf <= 1.0:
                messagebox.showerror(
                    "Erro",
                    "O limiar de confiança deve ser um número entre 0.0 e 1.0.",
                    parent=self,
                )
                return
        except ValueError:
            messagebox.showerror(
                "Erro",
                "O limiar de confiança deve ser um número válido.",
                parent=self,
            )
            return

        config = {
            "video_path": self.diagnostic_video_path,
            "frames_to_analyze": frames,
            "confidence_threshold": conf,
            "model_to_test": self.model_test_var.get(),
        }
        if self.scope == "project":
            selected_weight = self.project_weight_options.get(self.active_weight_var.get())
            if not selected_weight:
                messagebox.showerror(
                    "Erro",
                    "Selecione um dos pesos efetivos do projeto para diagnóstico.",
                    parent=self,
                )
                return
            config["active_weight_name"] = selected_weight
        if self.parent_dialog is not None:
            config["parent_dialog"] = self.parent_dialog

        self._publish_event(
            UIEvents.MODEL_RUN_DIAGNOSTIC,
            ModelRunDiagnosticPayload(config=config),
        )

    def _publish_event(self, event_type: UIEvents, payload: payloads.EventPayload) -> None:
        bus = getattr(self.controller, "ui_event_bus", None)
        if bus is None:
            log.error("model_diagnostics_panel.no_event_bus", event=event_type.name)
            return
        bus.publish(Event(type=event_type, data=payload))
