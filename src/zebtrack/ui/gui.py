"""
Este módulo define a interface gráfica principal (GUI) para a aplicação Zebtrack.
"""

import copy
import os
import queue
import re
import subprocess
import sys
import threading
import time
from collections import Counter
from pathlib import Path
from tkinter import (
    BooleanVar,
    Button,
    Canvas,
    Checkbutton,
    Entry,
    Frame,
    Label,
    Menu,
    OptionMenu,
    StringVar,
    Text,
    filedialog,
    messagebox,
    simpledialog,
    ttk,
)
from tkinter import font as tkfont
from typing import Any, Callable, ClassVar

import cv2
import numpy as np
import serial.tools.list_ports
import structlog
import yaml
from PIL import Image, ImageTk
from pydantic import ValidationError

try:
    import ttkbootstrap as ttkb
except ImportError:  # pragma: no cover - optional dependency fallback
    ttkb = None

# Import custom modules
import zebtrack.settings as settings_module
from zebtrack.core.detector import ZoneData
from zebtrack.core.processing_mode import ProcessingMode, ProcessingReport
from zebtrack.io.arduino import Arduino
from zebtrack.io.camera import Camera
from zebtrack.settings import settings
from zebtrack.ui.components import VideoDisplayWidget, ZoneControlsWidget
from zebtrack.ui.event_bus import CallableEvent, EventBus, EventType, NamedEvent
from zebtrack.ui.events import Events
from zebtrack.ui.window_utils import (
    reset_geometry_if_not_maximized,
    schedule_maximize,
    set_geometry_if_not_maximized,
)
from zebtrack.utils import polygon_centroid, snap_point_to_axes

log = structlog.get_logger()


STATUS_SYMBOLS = {
    "arena": "\U0001f3df",  # 🏟
    "rois": "\U0001f3af",  # 🎯
    "trajectory": "\U0001f9ed",  # 🧭
    "summary": "\u03a3",  # Σ
}

PROJECT_STATUS_META: dict[str, tuple[str, str]] = {
    "pending": ("⏳", "Pendentes"),
    "processing": ("🔁", "Processando"),
    "processed": ("📦", "Com dados"),
    "complete": ("✅", "Concluídos"),
    "failed": ("⚠️", "Com falha"),
}

PROJECT_STATUS_WIDGET_ORDER: tuple[str, ...] = (
    "total",
    "pending",
    "processing",
    "processed",
    "complete",
    "failed",
    "others",
)


class CalibrationDialog(simpledialog.Dialog):
    """Dialog for model calibration and diagnostics."""

    def __init__(self, parent, controller):
        self.controller = controller
        # Still need this for some callbacks like _manage_weights_clicked
        self.view = controller.view

        # Local Tkinter variables for this dialog
        self.active_weight_var = StringVar()
        self.use_openvino_var = BooleanVar()
        self.openvino_status_var = StringVar()
        self.scope_info = controller.get_calibration_scope_info()
        self.scope_label_var = StringVar(value=self.scope_info["label"])
        self.scope_detail_var = StringVar(value=self.scope_info["detail"])
        self.scope_action_button = None

        # --- Vars for diagnostic ---
        self.frames_to_analyze_var = StringVar(value="10")
        self.confidence_threshold_var = StringVar(value="0.25")
        self.nms_threshold_var = StringVar(value="0.50")
        self.track_threshold_var = StringVar(value="0.25")
        self.match_threshold_var = StringVar(value="0.15")
        self.video_path_label_var = StringVar(value="Nenhum vídeo selecionado.")
        self.diagnostic_video_path = ""
        self.model_test_var = StringVar(value="YOLO (PyTorch)")

        self._prefill_detector_parameters()

        super().__init__(parent, "Calibração e Diagnóstico")

    def body(self, master):
        schedule_maximize(self)
        scope_frame = ttk.LabelFrame(master, text="Contexto da Calibração", padding=10)
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

        # --- Frame for model configuration ---
        model_frame = ttk.LabelFrame(master, text="Configuração do Modelo", padding=10)
        model_frame.pack(fill="x", pady=5, padx=5)
        model_frame.columnconfigure(1, weight=1)

        # --- Row 0: Weight Selection ---
        ttk.Label(model_frame, text="Peso Ativo:").grid(row=0, column=0, sticky="w", padx=5, pady=3)
        self.weights_dropdown = ttk.Combobox(
            model_frame, textvariable=self.active_weight_var, state="readonly"
        )
        self.weights_dropdown.grid(row=0, column=1, sticky="ew", padx=5, pady=3)
        self.weights_dropdown.bind("<<ComboboxSelected>>", self._on_weight_selected_local)
        self._populate_weights_dropdown()

        # --- Row 1: Weight Management Buttons ---
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

        # --- Row 2: OpenVINO Toggle ---
        self.openvino_checkbox = ttk.Checkbutton(
            model_frame,
            text="Otimizar com OpenVINO (para hardware Intel)",
            variable=self.use_openvino_var,
            command=self._on_openvino_toggled_local,
        )
        self.openvino_checkbox.grid(row=2, column=0, columnspan=2, sticky="w", padx=5, pady=(8, 2))

        # --- Row 3: OpenVINO Status ---
        self.openvino_status_label = ttk.Label(
            model_frame, textvariable=self.openvino_status_var, font=("Segoe UI", 8)
        )
        self.openvino_status_label.grid(
            row=3, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 5)
        )

        # Set initial state from controller
        self.use_openvino_var.set(self.controller.use_openvino)
        self.update_openvino_status_label(self.controller.get_openvino_status())

        # --- Frame for diagnostics ---
        diag_frame = ttk.LabelFrame(master, text="Diagnóstico de Desempenho do Modelo", padding=10)
        diag_frame.pack(fill="x", pady=10, padx=5)

        # --- Video Selection ---
        video_frame = ttk.Frame(diag_frame)
        video_frame.pack(fill="x", padx=10, pady=5)
        ttk.Button(
            video_frame,
            text="Selecionar Vídeo...",
            command=self._select_diagnostic_video,
        ).pack(side="left")
        ttk.Label(video_frame, textvariable=self.video_path_label_var).pack(side="left", padx=5)

        # --- Parameters ---
        params_frame = ttk.Frame(diag_frame, padding=5)
        params_frame.pack(fill="x", padx=10, pady=5)
        params_frame.columnconfigure(2, weight=1)

        ttk.Label(params_frame, text="Nº de Frames para Analisar:").grid(
            row=0, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(params_frame, textvariable=self.frames_to_analyze_var, width=10).grid(
            row=0, column=1, sticky="w", padx=5
        )

        ttk.Label(params_frame, text="Limiar de Confiança:").grid(
            row=1, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(params_frame, textvariable=self.confidence_threshold_var, width=10).grid(
            row=1, column=1, sticky="w", padx=5
        )
        ttk.Label(
            params_frame,
            text=(
                "Aceita apenas detecções com confiança acima desse valor. "
                "Reduza para detectar mais (com risco de falsos positivos) ou "
                "aumente para filtrar ruídos."
            ),
            wraplength=280,
            justify="left",
            foreground="#555555",
            font=("Segoe UI", 9),
        ).grid(row=1, column=2, sticky="w", padx=(10, 0))

        ttk.Label(params_frame, text="Limiar NMS (IoU):").grid(
            row=2, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(params_frame, textvariable=self.nms_threshold_var, width=10).grid(
            row=2, column=1, sticky="w", padx=5
        )
        ttk.Label(
            params_frame,
            text=(
                "Remove caixas muito sobrepostas. Valores menores mantêm apenas a "
                "caixa mais confiante; valores maiores permitem múltiplas caixas "
                "sobre o mesmo animal."
            ),
            wraplength=280,
            justify="left",
            foreground="#555555",
            font=("Segoe UI", 9),
        ).grid(row=2, column=2, sticky="w", padx=(10, 0))

        ttk.Label(params_frame, text="ByteTrack - Track Thresh:").grid(
            row=3, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(params_frame, textvariable=self.track_threshold_var, width=10).grid(
            row=3, column=1, sticky="w", padx=5
        )
        ttk.Label(
            params_frame,
            text=(
                "Confiança mínima para manter uma trilha existente ativa. "
                "Reduza para seguir animais mais ruidosos; aumente para evitar "
                "rastros instáveis."
            ),
            wraplength=280,
            justify="left",
            foreground="#555555",
            font=("Segoe UI", 9),
        ).grid(row=3, column=2, sticky="w", padx=(10, 0))

        ttk.Label(params_frame, text="ByteTrack - Match Thresh:").grid(
            row=4, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(params_frame, textvariable=self.match_threshold_var, width=10).grid(
            row=4, column=1, sticky="w", padx=5
        )
        ttk.Label(
            params_frame,
            text=(
                "Limite utilizado para ligar novas detecções às trilhas atuais na "
                "segunda etapa do ByteTrack. Ajuste para controlar quantas "
                "reassociações acontecem."
            ),
            wraplength=280,
            justify="left",
            foreground="#555555",
            font=("Segoe UI", 9),
        ).grid(row=4, column=2, sticky="w", padx=(10, 0))

        # --- Model Selection for Diagnostic ---
        ttk.Label(params_frame, text="Modelo(s) a Testar:").grid(
            row=5, column=0, sticky="w", padx=5, pady=2
        )
        self.model_test_dropdown = ttk.Combobox(
            params_frame,
            textvariable=self.model_test_var,
            state="readonly",
            values=["YOLO (PyTorch)", "OpenVINO", "Ambos"],
            width=15,
        )
        self.model_test_dropdown.grid(row=5, column=1, sticky="w", padx=5)

        actions_frame = ttk.Frame(diag_frame)
        actions_frame.pack(fill="x", padx=10, pady=(0, 5))
        ttk.Button(
            actions_frame,
            text="Aplicar Parâmetros",
            command=self._apply_detector_parameters,
        ).pack(side="left", expand=True, fill="x")
        ttk.Button(
            actions_frame,
            text="Restaurar Padrões",
            command=self._restore_detector_defaults,
        ).pack(side="left", expand=True, fill="x", padx=(8, 0))

        ttk.Button(
            diag_frame,
            text="Testar Modelo em Vídeo...",
            command=self._run_diagnostic_test,
        ).pack(fill="x", padx=10, pady=5)

    def _prefill_detector_parameters(self) -> None:
        try:
            params = self.controller.get_current_detector_parameters()
        except Exception:
            params = {}

        if not params:
            return

        conf = params.get("confidence_threshold")
        if conf is not None:
            self.confidence_threshold_var.set(f"{conf:.2f}")

        nms = params.get("nms_threshold")
        if nms is not None:
            self.nms_threshold_var.set(f"{nms:.2f}")

        track_thresh = params.get("track_threshold")
        if track_thresh is not None:
            self.track_threshold_var.set(f"{track_thresh:.2f}")

        match_thresh = params.get("match_threshold")
        if match_thresh is not None:
            self.match_threshold_var.set(f"{match_thresh:.2f}")

    def _apply_detector_parameters(self) -> None:
        try:
            conf = float(self.confidence_threshold_var.get())
            nms = float(self.nms_threshold_var.get())
            track_thresh = float(self.track_threshold_var.get())
            match_thresh = float(self.match_threshold_var.get())
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
        ):
            if not 0.0 < value < 1.0:
                messagebox.showerror(
                    "Erro",
                    f"O {label} deve estar entre 0 e 1.",
                )
                return

        try:
            updated = self.controller.update_detector_parameters(
                {
                    "confidence_threshold": conf,
                    "nms_threshold": nms,
                    "track_threshold": track_thresh,
                    "match_threshold": match_thresh,
                }
            )
        except ValueError as exc:
            messagebox.showerror("Erro", str(exc))
            return

        if updated:
            self.confidence_threshold_var.set(f"{conf:.2f}")
            messagebox.showinfo(
                "Parâmetros do Detector",
                "Parâmetros atualizados com sucesso.",
            )
        else:
            messagebox.showinfo(
                "Parâmetros do Detector",
                "Nenhuma alteração necessária.",
            )

    def _restore_detector_defaults(self) -> None:
        try:
            defaults = self.controller.get_factory_detector_parameters()
        except ValueError as exc:
            messagebox.showerror("Erro", str(exc))
            return

        self.confidence_threshold_var.set(f"{defaults.get('confidence_threshold', 0.25):.2f}")
        self.nms_threshold_var.set(f"{defaults.get('nms_threshold', 0.5):.2f}")
        self.track_threshold_var.set(f"{defaults.get('track_threshold', 0.25):.2f}")
        self.match_threshold_var.set(f"{defaults.get('match_threshold', 0.15):.2f}")

        try:
            self.controller.update_detector_parameters(defaults, reset_overrides=True)
        except ValueError as exc:
            messagebox.showerror("Erro", str(exc))
            return

        messagebox.showinfo(
            "Parâmetros do Detector",
            "Parâmetros padrão restaurados.",
        )

    def _populate_weights_dropdown(self):
        """(Re)populates the weights dropdown in the dialog."""
        weights_list = self.controller.get_all_weight_names()
        self.weights_dropdown["values"] = weights_list
        if not weights_list:
            self.active_weight_var.set("Nenhum peso encontrado.")
            self.weights_dropdown.config(state="disabled")
        else:
            self.weights_dropdown.config(state="readonly")
            # Set to the controller's current weight
            current_weight = self.controller.active_weight_name
            if current_weight in weights_list:
                self.active_weight_var.set(current_weight)
            elif weights_list:
                self.active_weight_var.set(weights_list[0])

    def _on_weight_selected_local(self, event=None):
        """Callback when user selects a new weight from the dropdown."""
        selected_weight = self.active_weight_var.get()
        self.publish_event(Events.MODEL_SET_WEIGHT, {"name": selected_weight, "dialog": self})

    def _on_openvino_toggled_local(self):
        """Callback when user toggles the OpenVINO checkbox."""
        self.publish_event(
            Events.MODEL_SET_OPENVINO,
            {"use_openvino": self.use_openvino_var.get(), "dialog": self},
        )

    def update_openvino_status_label(self, status: str):
        """Updates the status label with the given text."""
        self.openvino_status_var.set(status)

    def _load_new_weight_local(self):
        """Handles the 'Load New Weight' button click."""
        # This can call the view's method as it's just a file dialog
        self.view._load_new_weight_clicked()
        # Repopulate this dialog's dropdown after the controller has the new weight
        self._populate_weights_dropdown()
        # Status is updated by the controller when the weight is set.

    def _manage_weights_local(self):
        """Opens the weight management dialog and provides a callback to refresh."""

        # The callback will be called by the ManageWeightsDialog upon closing
        def refresh_callback():
            self._populate_weights_dropdown()
            # The controller will handle the status update when a new weight is selected
            # or the default is changed.

        ManageWeightsDialog(self.parent, self.controller, refresh_callback)

    def _select_diagnostic_video(self):
        path = filedialog.askopenfilename(
            title="Selecione o Vídeo para Diagnóstico",
            filetypes=[("Arquivos de vídeo", "*.mp4 *.avi *.mov")],
        )
        if path:
            self.diagnostic_video_path = path
            self.video_path_label_var.set(os.path.basename(path))

    def _run_diagnostic_test(self):
        # --- Validation ---
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

        # --- Config Build ---
        model_to_test = self.model_test_var.get()

        config = {
            "video_path": self.diagnostic_video_path,
            "frames_to_analyze": int(self.frames_to_analyze_var.get()),
            "confidence_threshold": float(self.confidence_threshold_var.get()),
            "model_to_test": model_to_test,
        }

        self.publish_event(Events.MODEL_RUN_DIAGNOSTIC, {"config": config})
        self.destroy()

    def buttonbox(self):
        # Override to have only a close button
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
        self.scope_label_var.set(self.scope_info["label"])
        self.scope_detail_var.set(self.scope_info["detail"])
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
            self.publish_event(Events.CALIBRATION_COPY_TO_PROJECT, {})
            result = True  # Assume success for now
            if result:
                messagebox.showinfo(
                    "Projeto atualizado",
                    (f"Os padrões globais foram copiados para o projeto {project_name}."),
                )
        else:
            self.publish_event(Events.CALIBRATION_SAVE_TO_PROJECT, {})
            result = True  # Assume success for now
            if result:
                messagebox.showinfo(
                    "Overrides salvos",
                    (f"A calibração atual foi salva como override para o projeto {project_name}."),
                )

        self._populate_weights_dropdown()
        self.use_openvino_var.set(self.controller.use_openvino)
        self._refresh_scope_context()


class ProjectModelOverridesDialog(simpledialog.Dialog):
    """Dialog for configuring per-project model overrides."""

    WEIGHT_INHERIT_LABEL = "Herdar (padrão global)"
    OPENVINO_INHERIT = "inherit"
    OPENVINO_ON = "on"
    OPENVINO_OFF = "off"

    def __init__(self, parent, controller):
        self.controller = controller
        self.project_manager = controller.project_manager

        self.weight_choice = StringVar()
        self.openvino_choice = StringVar()
        self.effective_weight_var = StringVar()
        self.effective_openvino_var = StringVar()
        self.result = None

        super().__init__(parent, "Preferências do Projeto")

    def body(self, master):
        schedule_maximize(self)
        master.columnconfigure(1, weight=1)

        ttk.Label(
            master,
            text=(
                "Ajuste o peso e o uso do OpenVINO apenas para este projeto. "
                "Ao herdar, as configurações globais serão utilizadas."
            ),
            wraplength=420,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 8))

        defaults = self.controller.get_global_model_defaults()
        overrides = (
            getattr(self.project_manager, "project_data", {}).get("model_overrides", {}) or {}
        )

        weights = self.controller.get_all_weight_names()
        display_values = [self.WEIGHT_INHERIT_LABEL, *weights]

        current_weight_override = overrides.get("active_weight")
        if current_weight_override and current_weight_override not in weights:
            # Keep legacy override visible even if missing, appending to the list
            display_values.append(current_weight_override)

        if current_weight_override:
            self.weight_choice.set(current_weight_override)
        else:
            self.weight_choice.set(self.WEIGHT_INHERIT_LABEL)

        ttk.Label(master, text="Peso específico deste projeto:").grid(
            row=1, column=0, sticky="w", padx=10
        )
        self.weight_dropdown = ttk.Combobox(
            master,
            state="readonly",
            values=display_values,
            textvariable=self.weight_choice,
        )
        self.weight_dropdown.grid(row=1, column=1, sticky="ew", padx=(0, 10))

        openvino_override = overrides.get("use_openvino")
        if openvino_override is None:
            self.openvino_choice.set(self.OPENVINO_INHERIT)
        elif bool(openvino_override):
            self.openvino_choice.set(self.OPENVINO_ON)
        else:
            self.openvino_choice.set(self.OPENVINO_OFF)

        openvino_frame = ttk.LabelFrame(master, text="OpenVINO", padding=8)
        openvino_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=(12, 4), sticky="ew")
        openvino_frame.columnconfigure(0, weight=1)

        ttk.Radiobutton(
            openvino_frame,
            text="Herdar configuração global",
            value=self.OPENVINO_INHERIT,
            variable=self.openvino_choice,
            command=self._update_preview,
        ).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(
            openvino_frame,
            text="Forçar ativado",
            value=self.OPENVINO_ON,
            variable=self.openvino_choice,
            command=self._update_preview,
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        ttk.Radiobutton(
            openvino_frame,
            text="Forçar desativado",
            value=self.OPENVINO_OFF,
            variable=self.openvino_choice,
            command=self._update_preview,
        ).grid(row=2, column=0, sticky="w", pady=(2, 0))

        preview = ttk.LabelFrame(master, text="Resultado Efetivo", padding=8)
        preview.grid(row=3, column=0, columnspan=2, padx=10, pady=(10, 6), sticky="ew")
        preview.columnconfigure(1, weight=1)

        ttk.Label(preview, text="Peso utilizado:").grid(row=0, column=0, sticky="w")
        ttk.Label(preview, textvariable=self.effective_weight_var).grid(row=0, column=1, sticky="w")
        ttk.Label(preview, text="OpenVINO:").grid(row=1, column=0, sticky="w")
        ttk.Label(preview, textvariable=self.effective_openvino_var).grid(
            row=1, column=1, sticky="w"
        )

        defaults_frame = ttk.LabelFrame(master, text="Padrões Globais", padding=8)
        defaults_frame.grid(row=4, column=0, columnspan=2, padx=10, pady=(6, 4), sticky="ew")
        ttk.Label(
            defaults_frame,
            text=f"Peso global: {defaults.get('active_weight') or 'Nenhum'}",
        ).pack(anchor="w")
        ttk.Label(
            defaults_frame,
            text=(
                "OpenVINO global: " + ("Ativado" if defaults.get("use_openvino") else "Desativado")
            ),
        ).pack(anchor="w", pady=(4, 0))

        self.weight_dropdown.bind("<<ComboboxSelected>>", lambda *_: self._update_preview())
        self._update_preview()

        return self.weight_dropdown

    def _get_override_values(self) -> tuple[str | None, bool | None]:
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

    def _update_preview(self):
        weight_override, openvino_override = self._get_override_values()
        resolved_weight, resolved_openvino = self.controller.resolve_project_model_settings(
            {
                "active_weight": weight_override,
                "use_openvino": openvino_override,
            }
        )

        self.effective_weight_var.set(resolved_weight or "Nenhum peso disponível")
        self.effective_openvino_var.set("Ativado" if resolved_openvino else "Desativado")

    def apply(self):
        weight_override, openvino_override = self._get_override_values()
        self.result = self.controller.save_project_model_overrides(
            weight_override, openvino_override
        )

    def buttonbox(self):
        box = ttk.Frame(self)
        ttk.Button(box, text="Cancelar", command=self.cancel).pack(side="right", padx=6)
        ttk.Button(box, text="Salvar", command=self.ok, default="active").pack(side="right", padx=6)
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)
        box.pack(pady=10)


class ManageWeightsDialog(simpledialog.Dialog):
    """Dialog to manage the available weights."""

    def __init__(
        self,
        parent,
        controller,
        refresh_callback: Callable[..., Any] | None = None,
    ):
        self.controller = controller
        self.refresh_callback = refresh_callback
        super().__init__(parent, "Gerenciar Pesos de Detecção")

    def body(self, master):
        schedule_maximize(self)
        self.listbox = ttk.Treeview(
            master, columns=("name", "is_default"), show="headings", height=5
        )
        self.listbox.heading("name", text="Nome do Peso")
        self.listbox.heading("is_default", text="Padrão")
        self.listbox.column("is_default", width=60, anchor="center")
        self.listbox.pack(padx=5, pady=5, fill="both", expand=True)

        self.populate_list()

        button_frame = ttk.Frame(master)
        button_frame.pack(pady=5)

        ttk.Button(button_frame, text="Definir como Padrão", command=self.set_default).pack(
            side="left", padx=5
        )
        ttk.Button(button_frame, text="Excluir Selecionado", command=self.delete).pack(
            side="left", padx=5
        )

    def populate_list(self):
        for item in self.listbox.get_children():
            self.listbox.delete(item)

        weights = self.controller.get_all_weight_names()
        default_name, _ = self.controller.weight_manager.get_default_weight()

        for name in sorted(weights):
            is_default_str = "Sim" if name == default_name else ""
            self.listbox.insert("", "end", values=(name, is_default_str))

    def get_selected_item_name(self):
        selected = self.listbox.selection()
        if not selected:
            messagebox.showwarning("Nenhuma Seleção", "Por favor, selecione um peso primeiro.")
            return None
        return self.listbox.item(selected[0])["values"][0]

    def set_default(self):
        name = self.get_selected_item_name()
        if name:
            self.controller.weight_manager.set_default_weight(name)
            self.populate_list()
            # No longer need to update the main GUI dropdown directly

    def delete(self):
        name = self.get_selected_item_name()
        if name:
            if messagebox.askyesno(
                "Confirmar Exclusão", f"Tem certeza que deseja excluir '{name}'?"
            ):
                self.publish_event(Events.MODEL_DELETE_WEIGHT, {"name": name})
                self.populate_list()

    def destroy(self):
        # Override destroy to call the callback if it exists
        if self.refresh_callback:
            self.refresh_callback()
        super().destroy()

    def buttonbox(self):
        # Override to have only a close button
        box = ttk.Frame(self)
        w = ttk.Button(box, text="Fechar", width=10, command=self.ok, default="active")
        w.pack(side="left", padx=5, pady=5)
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)
        box.pack()


class PendingVideosDialog(simpledialog.Dialog):
    """Dialog para revisar vídeos pendentes em formato hierárquico."""

    TAG_STYLES: ClassVar[dict[str, dict[str, str]]] = {
        "ready_full": {"background": "#d4edda", "foreground": "#1e4620"},
        "ready_partial": {"background": "#fff3cd", "foreground": "#5c470b"},
        "ready_missing": {"background": "#f8d7da", "foreground": "#842029"},
    }

    def __init__(
        self,
        parent,
        hierarchy_builder,
        ready_with_trajectory: list[dict],
        ready_with_zones: list[dict],
        arena_only: list[dict],
        without_arena: list[dict],
    ):
        self.hierarchy_builder = hierarchy_builder
        self.ready_with_trajectory = ready_with_trajectory or []
        self.ready_with_zones = ready_with_zones or []
        self.arena_only = arena_only or []
        self.without_arena = without_arena or []
        self.include_arena_only_var = BooleanVar(value=False)
        self.result = {"confirmed": False, "include_arena_only": False}
        super().__init__(parent, "Processar Vídeos Pendentes")

    def body(self, master):
        master.columnconfigure(0, weight=1)
        master.rowconfigure(1, weight=1)

        ttk.Label(
            master,
            text=("Revise a lista hierárquica e confirme os itens que deseja processar."),
            wraplength=560,
            justify="left",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 6))

        container = ttk.Frame(master)
        container.grid(row=1, column=0, sticky="nsew", padx=12)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)

        columns = ("status", "arquivo")
        self.tree = ttk.Treeview(
            container,
            columns=columns,
            show="tree headings",
            height=15,
            selectmode="none",
        )
        self.tree.heading("#0", text="Hierarquia")
        self.tree.heading("status", text="Dados")
        self.tree.heading("arquivo", text="Arquivo")
        self.tree.column("#0", width=260, stretch=True)
        self.tree.column("status", width=180, anchor="center", stretch=False)
        self.tree.column("arquivo", width=220, stretch=True)

        vsb = ttk.Scrollbar(container, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(container, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        for tag, style in self.TAG_STYLES.items():
            self.tree.tag_configure(tag, **style)
        self.tree.tag_configure("ready_optional", foreground="#5f4b00")

        self._populate_tree()

        legend = ttk.Frame(master)
        legend.grid(row=2, column=0, sticky="w", padx=12, pady=(8, 4))
        ttk.Label(legend, text="Legenda:").pack(side="left", padx=(0, 6))
        self._add_legend_chip(legend, "#d4edda", "#1e4620", "Pronto")
        self._add_legend_chip(legend, "#fff3cd", "#5c470b", "Parcial")
        self._add_legend_chip(legend, "#f8d7da", "#842029", "Ignorado")

        if self.arena_only:
            ttk.Checkbutton(
                master,
                text=(
                    f"Incluir {len(self.arena_only)} vídeo(s) com apenas arena no processamento."
                ),
                variable=self.include_arena_only_var,
            ).grid(row=3, column=0, sticky="w", padx=12, pady=(0, 12))
        else:
            ttk.Frame(master).grid(row=3, column=0, pady=(0, 12))

        return self.tree

    def buttonbox(self):
        box = ttk.Frame(self)
        box.pack(pady=(0, 12))
        ttk.Button(box, text="Cancelar", command=self.cancel).pack(side="right", padx=6)
        ttk.Button(box, text="Processar", command=self.ok, default="active").pack(
            side="right", padx=6
        )
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)

    def apply(self):
        self.result = {
            "confirmed": True,
            "include_arena_only": bool(self.include_arena_only_var.get())
            if self.arena_only
            else False,
        }

    def cancel(self, event=None):
        self.result = {"confirmed": False, "include_arena_only": False}
        super().cancel(event)

    def _populate_tree(self) -> None:
        hierarchy = self.hierarchy_builder() if callable(self.hierarchy_builder) else []

        readiness_map: dict[str, tuple[str, ...]] = {}

        def _assign(entries: list[dict], *tags: str):
            for info in entries or []:
                path = info.get("path")
                if path:
                    readiness_map[path] = tuple(tags)

        _assign(self.ready_with_trajectory, "ready_full")
        _assign(self.ready_with_zones, "ready_partial")
        _assign(self.arena_only, "ready_partial", "ready_optional")
        _assign(self.without_arena, "ready_missing")

        for group in hierarchy:
            group_node = self.tree.insert(
                "",
                "end",
                text=group.get("label", ""),
                values=(
                    group.get("status_label", ""),
                    group.get("filename_display", ""),
                ),
                open=True,
            )
            for day in group.get("children", []):
                day_node = self.tree.insert(
                    group_node,
                    "end",
                    text=day.get("label", ""),
                    values=(day.get("status_label", ""), ""),
                    open=False,
                )
                for video in day.get("children", []):
                    path = video.get("path")
                    tags = readiness_map.get(path, ()) if path else ()
                    self.tree.insert(
                        day_node,
                        "end",
                        text=video.get("label", ""),
                        values=(
                            video.get("status_label", ""),
                            video.get("filename", ""),
                        ),
                        tags=tags,
                    )

    @staticmethod
    def _add_legend_chip(parent, background: str, foreground: str, text: str) -> None:
        chip = ttk.Frame(parent)
        chip.pack(side="left", padx=4)
        swatch = Frame(
            chip,
            width=14,
            height=14,
            bg=background,
            highlightbackground="#c0c0c0",
            highlightthickness=1,
        )
        swatch.pack(side="left", padx=(0, 4))
        swatch.pack_propagate(False)
        ttk.Label(chip, text=text, foreground=foreground).pack(side="left")


class CreateProjectDialog(simpledialog.Dialog):
    """A custom dialog to gather all new project information."""

    def __init__(self, parent):
        self.project_path = None
        self.result = None
        super().__init__(parent, "Criar Novo Projeto")

    def body(self, master):
        schedule_maximize(self)
        self.project_name_var = StringVar()
        self.num_aquariums_var = StringVar(value="1")
        self.animals_per_aquarium_var = StringVar(value="1")
        self.aquarium_width_var = StringVar(value="10.0")
        self.aquarium_height_var = StringVar(value="10.0")
        self.project_type_var = StringVar(value="pre-recorded")
        self.video_files = []
        self.video_list_var = StringVar(value="Nenhum vídeo selecionado.")
        self.use_timed_recording_var = BooleanVar(value=False)
        self.recording_duration_var = StringVar(value="5")
        self.use_countdown_var = BooleanVar(value=False)
        self.countdown_duration_var = StringVar(value="5")

        # Vars for live project experimental design
        self.total_days_var = StringVar(value="1")
        self.subjects_per_group_var = StringVar(value="1")
        self.num_groups_var = StringVar(value="1")
        self.group_name_vars = [StringVar() for _ in range(6)]

        # Frame interval configuration variables
        self.analysis_interval_var = StringVar(value="10")
        self.display_interval_var = StringVar(value="10")

        # Detection method configuration variables
        self.aquarium_method_var = StringVar(value="seg")  # Default from settings
        self.animal_method_var = StringVar(value="det")  # Default from settings

        # --- Project Name ---
        Label(master, text="Nome do Projeto:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        Entry(master, textvariable=self.project_name_var, width=40).grid(
            row=0, column=1, columnspan=2, sticky="ew", padx=5
        )

        # --- Base Path ---
        Label(master, text="Pasta do Projeto:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.path_entry = Entry(master, text="", width=40)
        self.path_entry.grid(row=1, column=1, columnspan=2, sticky="ew", padx=5)
        Button(master, text="Procurar...", command=self._select_path).grid(row=1, column=3, padx=5)

        # --- Calibration ---
        Label(master, text="Número de Aquários:").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        Entry(master, textvariable=self.num_aquariums_var, width=10).grid(
            row=2, column=1, sticky="w", padx=5
        )

        Label(master, text="Animais por Aquário:").grid(row=3, column=0, sticky="w", padx=5, pady=2)
        Entry(master, textvariable=self.animals_per_aquarium_var, width=10).grid(
            row=3, column=1, sticky="w", padx=5
        )

        Label(master, text="Largura do Aquário (cm):").grid(
            row=4, column=0, sticky="w", padx=5, pady=2
        )
        Entry(master, textvariable=self.aquarium_width_var, width=10).grid(
            row=4, column=1, sticky="w", padx=5
        )

        Label(master, text="Altura do Aquário (cm):").grid(
            row=5, column=0, sticky="w", padx=5, pady=2
        )
        Entry(master, textvariable=self.aquarium_height_var, width=10).grid(
            row=5, column=1, sticky="w", padx=5
        )

        # --- Frame Intervals ---
        Label(master, text="Intervalo de Análise (frames):").grid(
            row=6, column=0, sticky="w", padx=5, pady=2
        )
        Entry(master, textvariable=self.analysis_interval_var, width=10).grid(
            row=6, column=1, sticky="w", padx=5
        )

        Label(master, text="Intervalo de Exibição (frames):").grid(
            row=7, column=0, sticky="w", padx=5, pady=2
        )
        Entry(master, textvariable=self.display_interval_var, width=10).grid(
            row=7, column=1, sticky="w", padx=5
        )

        # --- Detection Methods ---
        Label(master, text="Método para Aquário:").grid(row=8, column=0, sticky="w", padx=5, pady=2)
        aquarium_method_combo = ttk.Combobox(
            master,
            textvariable=self.aquarium_method_var,
            values=["seg", "det"],
            state="readonly",
            width=8,
        )
        aquarium_method_combo.grid(row=8, column=1, sticky="w", padx=5)

        Label(master, text="Método para Animais:").grid(row=9, column=0, sticky="w", padx=5, pady=2)
        animal_method_combo = ttk.Combobox(
            master,
            textvariable=self.animal_method_var,
            values=["seg", "det"],
            state="readonly",
            width=8,
        )
        animal_method_combo.grid(row=9, column=1, sticky="w", padx=5)

        # --- Project Type & Videos ---
        Label(master, text="Tipo de Projeto:").grid(row=10, column=0, sticky="w", padx=5, pady=2)
        ttk.Radiobutton(
            master,
            text="Pré-gravado",
            variable=self.project_type_var,
            value="pre-recorded",
            command=self._update_project_type_options,
        ).grid(row=10, column=1, sticky="w", padx=5)
        ttk.Radiobutton(
            master,
            text="Ao Vivo",
            variable=self.project_type_var,
            value="live",
            command=self._update_project_type_options,
        ).grid(row=10, column=2, sticky="w", padx=5)

        # Video/Folder selection buttons
        video_selection_frame = Frame(master)
        video_selection_frame.grid(row=11, column=0, columnspan=2, sticky="w", padx=5, pady=5)

        self.video_files_button = Button(
            video_selection_frame,
            text="Selecionar Vídeos...",
            command=self._select_video_files,
        )
        self.video_files_button.pack(side="left", padx=(0, 5))

        self.video_folder_button = Button(
            video_selection_frame,
            text="Selecionar Pasta...",
            command=self._select_video_folder,
        )
        self.video_folder_button.pack(side="left")

        Label(master, textvariable=self.video_list_var, wraplength=400).grid(
            row=11, column=2, columnspan=2, sticky="w", padx=5
        )

        # --- Live Recording Options ---
        self.live_options_frame = Frame(master)
        self.live_options_frame.grid(row=12, column=0, columnspan=4, sticky="ew", padx=5)
        Checkbutton(
            self.live_options_frame,
            text="Usar gravação com tempo?",
            variable=self.use_timed_recording_var,
            command=self._update_project_type_options,
        ).pack(side="left")
        self.duration_entry = Entry(
            self.live_options_frame, textvariable=self.recording_duration_var, width=5
        )
        self.duration_entry.pack(side="left", padx=5)
        Label(self.live_options_frame, text="minutos").pack(side="left", padx=(0, 10))

        # Countdown options
        Checkbutton(
            self.live_options_frame,
            text="Usar contagem regressiva?",
            variable=self.use_countdown_var,
            command=self._update_project_type_options,
        ).pack(side="left")
        self.countdown_entry = Entry(
            self.live_options_frame, textvariable=self.countdown_duration_var, width=5
        )
        self.countdown_entry.pack(side="left", padx=5)
        Label(self.live_options_frame, text="segundos").pack(side="left")

        # --- Live Project Experimental Design ---
        self.live_project_frame = ttk.LabelFrame(
            master, text="Design Experimental (Projeto ao Vivo)", padding=10
        )
        self.live_project_frame.grid(row=13, column=0, columnspan=4, sticky="ew", padx=5, pady=5)
        # Widgets inside live_project_frame
        ttk.Label(self.live_project_frame, text="Total de Dias do Experimento:").grid(
            row=0, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(self.live_project_frame, textvariable=self.total_days_var, width=10).grid(
            row=0, column=1, sticky="w", padx=5
        )
        ttk.Label(self.live_project_frame, text="Cobaias por Grupo:").grid(
            row=1, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(self.live_project_frame, textvariable=self.subjects_per_group_var, width=10).grid(
            row=1, column=1, sticky="w", padx=5
        )
        ttk.Label(self.live_project_frame, text="Número de Grupos:").grid(
            row=2, column=0, sticky="w", padx=5, pady=2
        )
        num_groups_entry = ttk.Entry(
            self.live_project_frame, textvariable=self.num_groups_var, width=10
        )
        num_groups_entry.grid(row=2, column=1, sticky="w", padx=5)
        self.num_groups_var.trace_add("write", self._on_num_groups_change)
        self.group_names_frame = ttk.LabelFrame(
            self.live_project_frame, text="Nomes dos Grupos", padding=5
        )
        self.group_names_frame.grid(row=3, column=0, columnspan=4, sticky="ew", padx=5, pady=5)
        self.group_name_entries = []
        for i in range(6):
            row, col = divmod(i, 2)
            ttk.Label(self.group_names_frame, text=f"Grupo {i + 1}:").grid(
                row=row, column=col * 2, sticky="w", padx=5, pady=2
            )
            entry = ttk.Entry(
                self.group_names_frame, textvariable=self.group_name_vars[i], width=20
            )
            entry.grid(row=row, column=col * 2 + 1, sticky="ew", padx=5)
            self.group_name_entries.append(entry)

        self._update_project_type_options()  # Set initial state
        self._on_num_groups_change()  # Set initial state for group names
        return self.path_entry  # initial focus

    def _select_path(self):
        path = filedialog.askdirectory(title="Selecione uma Pasta Principal para o Projeto")
        if path:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, path)

    def _select_video_files(self):
        """Select individual video files."""
        files = filedialog.askopenfilenames(
            title="Selecione os Arquivos de Vídeo",
            filetypes=[("Arquivos de vídeo", "*.mp4 *.avi *.mov")],
        )
        if files:
            # Initialize if needed
            if not hasattr(self, "video_paths") or not isinstance(self.video_paths, list):
                self.video_paths = []

            # Add new files to the list (avoid duplicates)
            for f in files:
                if f not in self.video_paths:
                    self.video_paths.append(f)

            self._update_video_selection_display()

    def _select_video_folder(self):
        """Select a folder containing videos."""
        folder = filedialog.askdirectory(title="Selecione uma Pasta Contendo Vídeos")
        if folder:
            # Initialize if needed
            if not hasattr(self, "video_paths") or not isinstance(self.video_paths, list):
                self.video_paths = []

            # Add folder to the list (avoid duplicates)
            if folder not in self.video_paths:
                self.video_paths.append(folder)

            self._update_video_selection_display()

    def _update_video_selection_display(self):
        """Update the display showing selected videos/folders."""
        if not hasattr(self, "video_paths") or not self.video_paths:
            self.video_list_var.set("Nenhum vídeo/pasta selecionado.")
            return

        # Count files and folders
        files = [p for p in self.video_paths if os.path.isfile(p)]
        folders = [p for p in self.video_paths if os.path.isdir(p)]

        parts = []
        if files:
            parts.append(f"{len(files)} arquivo(s)")
        if folders:
            parts.append(f"{len(folders)} pasta(s)")

        if parts:
            self.video_list_var.set(" + ".join(parts) + " selecionado(s).")
        else:
            self.video_list_var.set("Seleção contém caminhos inválidos.")

    def _on_num_groups_change(self, *args):
        try:
            num_groups = int(self.num_groups_var.get())
        except (ValueError, TypeError):
            num_groups = 0
        if not 0 <= num_groups <= 6:
            num_groups = 0  # Treat invalid numbers as 0
            # Optionally show a warning or clear the field
        for i, entry in enumerate(self.group_name_entries):
            if i < num_groups:
                entry.config(state="normal")
            else:
                entry.config(state="disabled")
                self.group_name_vars[i].set("")  # Clear disabled fields

    def _update_project_type_options(self):
        """Shows/hides options based on the selected project type."""
        if self.project_type_var.get() == "pre-recorded":
            self.video_files_button.config(state="normal")
            self.video_folder_button.config(state="normal")
            self.live_options_frame.grid_remove()
            self.live_project_frame.grid_remove()
        else:  # Live
            self.video_files_button.config(state="disabled")
            self.video_folder_button.config(state="disabled")
            self.video_list_var.set("Não aplicável para projetos ao vivo.")
            self.live_options_frame.grid()
            self.live_project_frame.grid()  # Show the new frame
            if self.use_timed_recording_var.get():
                self.duration_entry.config(state="normal")
            else:
                self.duration_entry.config(state="disabled")

            if self.use_countdown_var.get():
                self.countdown_entry.config(state="normal")
            else:
                self.countdown_entry.config(state="disabled")

    def validate(self):
        # Run a sequence of focused validators. Each returns (ok, message)
        validators = [
            self._validate_base_path_and_name,
            self._validate_video_selection_if_prerecorded,
            self._validate_calibration_numbers,
            self._validate_live_settings_if_needed,
            self._validate_intervals,
        ]

        for validator in validators:
            ok, msg = validator()
            if not ok:
                messagebox.showerror("Erro", msg)
                return 0

        return 1

    # ---------------------- helper validators ------------------------
    def _validate_base_path_and_name(self) -> tuple[bool, str]:
        base_path = self.path_entry.get()
        if not base_path or not os.path.isdir(base_path):
            return False, "Por favor, selecione uma pasta principal válida."

        project_name = self.project_name_var.get()
        if not project_name.strip():
            return False, "O nome do projeto não pode estar vazio."

        self.project_path = os.path.join(base_path, project_name)
        if os.path.exists(self.project_path) and os.listdir(self.project_path):
            return False, "Uma pasta de projeto com este nome já existe e não está vazia."

        return True, ""

    def _validate_video_selection_if_prerecorded(self) -> tuple[bool, str]:
        if self.project_type_var.get() != "pre-recorded":
            return True, ""

        if not hasattr(self, "video_paths") or not self.video_paths:
            return False, (
                "Por favor, selecione pelo menos um arquivo de vídeo ou pasta para "
                "análise pré-gravada."
            )

        return True, ""

    def _validate_calibration_numbers(self) -> tuple[bool, str]:
        try:
            num_aquariums = int(self.num_aquariums_var.get())
            animals_per_aquarium = int(self.animals_per_aquarium_var.get())
            float(self.aquarium_width_var.get())
            float(self.aquarium_height_var.get())
            if num_aquariums <= 0 or animals_per_aquarium <= 0:
                raise ValueError
        except ValueError:
            return False, "Os valores devem ser positivos."

        return True, ""

    def _validate_live_settings_if_needed(self) -> tuple[bool, str]:
        if self.project_type_var.get() != "live":
            return True, ""

        try:
            total_days = int(self.total_days_var.get())
            subjects_per_group = int(self.subjects_per_group_var.get())
            num_groups = int(self.num_groups_var.get())
            if total_days <= 0 or subjects_per_group <= 0 or num_groups <= 0:
                raise ValueError
            if not 1 <= num_groups <= 6:
                return False, "O número de grupos deve ser entre 1 e 6."
            for i in range(num_groups):
                if not self.group_name_vars[i].get().strip():
                    return False, f"O nome do Grupo {i + 1} não pode estar vazio."
        except (ValueError, TypeError):
            return False, (
                "Os parâmetros do design experimental devem ser números positivos válidos."
            )

        if self.use_timed_recording_var.get():
            try:
                duration = float(self.recording_duration_var.get())
                if duration <= 0:
                    raise ValueError
            except ValueError:
                return False, "A duração da gravação deve ser um número positivo."

        if self.use_countdown_var.get():
            try:
                countdown = int(self.countdown_duration_var.get())
                if countdown <= 0:
                    raise ValueError
            except ValueError:
                return False, "A duração da contagem regressiva deve ser um inteiro positivo."

        return True, ""

    def _validate_intervals(self) -> tuple[bool, str]:
        try:
            analysis_interval = int(self.analysis_interval_var.get())
            display_interval = int(self.display_interval_var.get())
            if analysis_interval <= 0 or display_interval <= 0:
                raise ValueError
        except ValueError:
            return False, (
                "Os intervalos de análise e exibição devem ser números inteiros positivos."
            )

        return True, ""

    def apply(self):
        duration = 0
        if self.use_timed_recording_var.get():
            try:
                # Duration in minutes, convert to seconds for internal use
                duration = float(self.recording_duration_var.get()) * 60
            except ValueError:
                pass  # Should be caught by validate

        countdown_duration = 0
        if self.use_countdown_var.get():
            try:
                countdown_duration = int(self.countdown_duration_var.get())
            except ValueError:
                pass

        # Use video_paths if available, fallback to empty list
        video_paths = getattr(self, "video_paths", [])

        num_aquariums = int(self.num_aquariums_var.get())
        animals_per_aquarium = int(self.animals_per_aquarium_var.get())

        self.result = {
            "project_path": self.project_path,
            "project_type": self.project_type_var.get(),
            "video_files": video_paths,  # Now can contain files AND folders
            "num_aquariums": num_aquariums,
            "animals_per_aquarium": animals_per_aquarium,
            "aquarium_width_cm": float(self.aquarium_width_var.get()),
            "aquarium_height_cm": float(self.aquarium_height_var.get()),
            "use_timed_recording": self.use_timed_recording_var.get(),
            "recording_duration_s": duration,
            "use_countdown": self.use_countdown_var.get(),
            "countdown_duration_s": countdown_duration,
            "analysis_interval_frames": int(self.analysis_interval_var.get()),
            "display_interval_frames": int(self.display_interval_var.get()),
            "aquarium_method": self.aquarium_method_var.get(),
            "animal_method": self.animal_method_var.get(),
            "use_single_subject_tracker": animals_per_aquarium == 1,
            # Initialize new keys to None
            "experiment_days": None,
            "subjects_per_group": None,
            "num_groups": None,
            "group_names": None,
        }

        if self.project_type_var.get() == "live":
            num_groups = int(self.num_groups_var.get())
            self.result["experiment_days"] = int(self.total_days_var.get())
            self.result["subjects_per_group"] = int(self.subjects_per_group_var.get())
            self.result["num_groups"] = num_groups
            self.result["group_names"] = [
                self.group_name_vars[i].get().strip() for i in range(num_groups)
            ]


class LiveConfigDialog(simpledialog.Dialog):
    """A dialog to configure live analysis settings (camera and Arduino)."""

    def __init__(self, parent):
        self.result = None
        self.available_cameras = {}
        self.available_ports = {}
        super().__init__(parent, "Configuração da Análise ao Vivo")

    def body(self, master):
        # --- Detect devices first ---
        self._detect_devices()

        # --- Tkinter Variables ---
        self.camera_var = StringVar()
        self.use_arduino_var = BooleanVar(value=True)
        self.arduino_port_var = StringVar()

        # --- Camera Selection ---
        Label(master, text="Selecionar Câmera:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        camera_names = list(self.available_cameras.keys())
        if not camera_names:
            camera_names = ["Nenhuma câmera encontrada"]
        self.camera_menu = OptionMenu(master, self.camera_var, *camera_names)
        self.camera_menu.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        if self.available_cameras:
            self.camera_var.set(next(iter(self.available_cameras.keys())))
        else:
            self.camera_menu.config(state="disabled")

        # --- Arduino Selection ---
        self.arduino_check = Checkbutton(
            master,
            text="Usar Arduino",
            variable=self.use_arduino_var,
            command=self._toggle_arduino_menu,
        )
        self.arduino_check.grid(row=1, column=0, columnspan=2, sticky="w", padx=5, pady=5)

        Label(master, text="Porta Arduino:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        port_names = list(self.available_ports.keys())
        if not port_names:
            port_names = ["Nenhuma porta encontrada"]
        self.arduino_menu = OptionMenu(master, self.arduino_port_var, *port_names)
        self.arduino_menu.grid(row=2, column=1, sticky="ew", padx=5, pady=5)

        if self.available_ports:
            self.arduino_port_var.set(next(iter(self.available_ports.keys())))

        self._toggle_arduino_menu()  # Set initial state
        return self.camera_menu  # Initial focus

    def _detect_devices(self):
        """Detects available cameras and serial ports."""
        # Detect cameras
        log.info("device_detection.camera.start")
        for i in range(10):  # Check up to 10 indices
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                self.available_cameras[f"Câmera {i}"] = i
                cap.release()
        log.info("device_detection.camera.found", cameras=self.available_cameras)

        # Detect serial ports
        try:
            log.info("device_detection.ports.start")
            baud_rate = (
                getattr(getattr(settings, "arduino", None), "baud_rate", 9600) if settings else 9600
            )
            handshake_ports, fallback_ports = Arduino.scan_available_ports(baud_rate=baud_rate)

            def _add_port(info, *, handshake: bool) -> None:
                device_id = getattr(info, "device", None)
                if not device_id:
                    return
                description = getattr(info, "description", device_id)
                suffix = " [Arduino]" if handshake else ""
                if handshake_ports and not handshake:
                    suffix = " [sem handshake]"
                label = f"{description} ({device_id}){suffix}"
                self.available_ports[label] = device_id

            for port in handshake_ports:
                _add_port(port, handshake=True)

            if handshake_ports:
                for port in fallback_ports:
                    _add_port(port, handshake=False)
            else:
                if not handshake_ports and not fallback_ports:
                    fallback_ports = []
                if not fallback_ports:
                    # Ensure we still list raw ports if probe yielded nothing
                    try:
                        fallback_ports = list(serial.tools.list_ports.comports())
                    except Exception:  # pragma: no cover - already logged above
                        fallback_ports = []
                for port in fallback_ports:
                    _add_port(port, handshake=False)

            log.info(
                "device_detection.ports.found",
                ports=self.available_ports,
                recognized=len(handshake_ports),
            )
        except Exception as e:
            log.warning("device_detection.ports.error", error=str(e))
            self.available_ports = {}

    def _toggle_arduino_menu(self):
        """Enable or disable the Arduino port dropdown based on the checkbox."""
        if self.use_arduino_var.get() and self.available_ports:
            self.arduino_menu.config(state="normal")
        else:
            self.arduino_menu.config(state="disabled")
            if not self.available_ports:
                self.use_arduino_var.set(False)

    def validate(self):
        """Validate the inputs before closing the dialog."""
        if not self.available_cameras:
            messagebox.showerror(
                "Erro",
                "Nenhuma câmera detectada. Não é possível iniciar uma sessão ao vivo.",
            )
            return 0
        if self.use_arduino_var.get() and not self.available_ports:
            messagebox.showerror(
                "Erro",
                "O Arduino está ativado, mas nenhuma porta serial foi "
                "encontrada. Por favor, verifique a conexão ou desative a "
                "opção 'Usar Arduino'.",
            )
            return 0
        return 1

    def apply(self):
        """Process the data and set the result."""
        use_arduino = self.use_arduino_var.get()
        selected_port_key = self.arduino_port_var.get()
        self.result = {
            "camera_index": self.available_cameras.get(self.camera_var.get()),
            "use_arduino": use_arduino,
            "arduino_port": self.available_ports.get(selected_port_key) if use_arduino else None,
        }


class ApplicationGUI:
    """
    A classe principal que gerencia a interface gráfica (a "Visão").
    """

    DEFAULT_CANVAS_WIDTH = 800
    DEFAULT_CANVAS_HEIGHT = 600

    def __init__(self, root, controller, event_bus: EventBus | None = None):
        """
        Inicializa a ApplicationGUI.
        """
        self.root = root
        self.controller = controller
        self.event_bus = event_bus
        self._event_bus_after_id: int | None = None
        self._event_bus_poll_interval_ms = 50
        self._event_bus_handlers: dict[EventType, Callable[[Any], None]] = {}
        self.root.title("Controlador Zebtrack")
        self.root.protocol("WM_DELETE_WINDOW", self.controller.on_close)

        self._ttkbootstrap_style = None
        self._ttkbootstrap_theme = None
        self._initialize_theme()

        # Dynamic widgets / state variables
        self.welcome_frame = None
        self.notebook = None
        self.main_controls_frame = None
        self.zone_tab_frame = None
        self.zone_summary_frame: ttk.LabelFrame | None = None
        self.zone_summary_cards: dict[str, dict[str, StringVar]] = {}
        self.pipeline_tab_frame: ttk.Frame | None = None
        self.pipeline_video_tree: ttk.Treeview | None = None
        self.pipeline_video_vars: dict[str, dict[str, StringVar]] = {}
        self.pipeline_selection_label: ttk.Label | None = None
        self.pipeline_action_buttons: dict[str, ttk.Button] = {}
        self.drawing_instruction_label = None
        self.current_drawing_type = None
        self.status_var = StringVar()
        self.pending_single_video_path = None
        self.pending_single_video_config = None
        self.start_single_analysis_btn = None
        self._zone_prompt_history: set[str] = set()

        # Model management state (reflected across welcome + project views)
        self._available_weight_names: list[str] = []
        self._active_weight_display_var = StringVar(value="Peso ativo: Nenhum peso selecionado.")
        self._openvino_display_var = StringVar(value="OpenVINO: Desativado.")
        self._openvino_enabled = False
        self._openvino_status_message = "Desativado."

        # ROI Tab Widgets
        self.roi_listbox = None
        self.run_analysis_btn = None
        # Note: roi_template_combobox is now a @property that delegates to zone_controls

        # ROI Inclusion Rule Variables
        self.roi_inclusion_rule_var = StringVar(
            value=settings.roi_inclusion_rule if settings else "bbox_intersects"
        )
        self.roi_buffer_radius_var = StringVar(
            value=str(settings.roi_buffer_radius_value if settings else 0.5)
        )
        self.roi_overlap_ratio_var = StringVar(
            value=str(settings.roi_min_bbox_overlap_ratio if settings else 0.10)
        )
        self.roi_template_var = StringVar(value="")
        self._roi_templates_cache: list[dict[str, Any]] = []

        self.config_tab_frame: ttk.Frame | None = None
        self.config_fps_var = StringVar(
            value=str(self._extract_setting(settings, ("video_processing", "fps"), 30))
        )
        self.config_processing_interval_var = StringVar(
            value=str(
                self._extract_setting(
                    settings,
                    ("video_processing", "processing_interval"),
                    10,
                )
            )
        )
        self.config_processing_offset_var = StringVar(
            value=str(
                self._extract_setting(
                    settings,
                    ("video_processing", "processing_offset"),
                    0,
                )
            )
        )
        self.config_flush_interval_var = StringVar(
            value=str(
                self._extract_setting(
                    settings,
                    ("recorder", "flush_interval_seconds"),
                    5.0,
                )
            )
        )
        self.config_flush_rows_var = StringVar(
            value=str(
                self._extract_setting(
                    settings,
                    ("recorder", "flush_row_threshold"),
                    500,
                )
            )
        )
        self.config_window_length_var = StringVar(
            value=str(
                self._extract_setting(
                    settings,
                    ("trajectory_smoothing", "window_length"),
                    7,
                )
            )
        )
        self.config_polyorder_var = StringVar(
            value=str(
                self._extract_setting(
                    settings,
                    ("trajectory_smoothing", "polyorder"),
                    3,
                )
            )
        )
        self._config_roi_rule_widgets: list[ttk.Combobox] = []

        # Progress + stats (created later)
        self.progress_frame: Frame | None = None
        self.progress_bar = None
        self.cancel_proc_btn: Button | None = None
        self.progress_labels: dict[str, StringVar] = {}
        self.video_label: Label | None = None
        self.analysis_tab_frame: ttk.Frame | None = None
        self.analysis_video_label: Label | None = None
        self.analysis_status_var = StringVar(value="Nenhuma análise em andamento.")
        self.analysis_status_label: ttk.Label | None = None
        (
            default_group,
            default_day,
            default_subject,
        ) = self._analysis_metadata_defaults()
        self.analysis_metadata_var = StringVar(value=self._default_analysis_metadata_text())
        self.analysis_group_var = StringVar(value=f"Grupo: {default_group}")
        self.analysis_day_var = StringVar(value=f"Dia: {default_day}")
        self.analysis_subject_var = StringVar(value=f"Indivíduo: {default_subject}")
        self.analysis_task_var = StringVar(value=self._default_analysis_task_text())
        self.analysis_metadata_label: ttk.Label | None = None
        self.analysis_task_label: ttk.Label | None = None
        self._active_processing_mode = ProcessingMode.MULTI_TRACK
        self.tracking_mode_var = StringVar(value="Modo de rastreamento: Multi-indivíduos")
        self.tracking_mode_label: ttk.Label | None = None
        self.analysis_profile_var = StringVar(value="Perfil de análise: default")
        self.analysis_profile_label: ttk.Label | None = None
        self.track_selector_var = StringVar(value="Todos")
        self.track_selector_widget: ttk.Combobox | None = None
        self.social_summary_var = StringVar(value="Interações sociais: aguardando dados.")
        self._available_track_options: tuple[str, ...] = ("Todos",)
        self._current_detections: list[tuple] = []
        self._last_analysis_frame = None
        self._analysis_overlay_image = None

        # User options
        self.processing_interval_var = StringVar(
            value=str(settings.video_processing.processing_interval)
        )
        self.show_preview_var = BooleanVar(value=True)

        # New frame interval controls (defaults to 10 as per requirements)
        self.analysis_interval_var = StringVar(value="10")
        self.display_interval_var = StringVar(value="10")

        # View toggle state for analysis/zone switching
        self.canvas_view_mode = "zones"  # "zones" or "analysis"
        self.analysis_active = False
        # toggle_view_btn is now a @property that delegates to zone_controls
        self.start_rec_btn: Button | None = None
        self.stop_rec_btn: Button | None = None
        self.process_video_btn: ttk.Button | None = None

        # Interactive arena editing state
        self.stabilization_frames_var = StringVar(value="10")
        self.interactive_polygon_item = None
        self.polygon_handles = []
        self.edited_polygon_points = []
        self._dragged_handle_index = None
        self._drag_offset = (0, 0)
        self.current_editing_zone = None  # Track what zone is being edited
        self.save_arena_btn = None
        self.discard_arena_btn = None
        # interactive_buttons_frame is now a @property that delegates to zone_controls

        # Zone tab video selector state
        # video_selector_tree is now a @property that delegates to zone_controls
        self.video_search_var = None
        self._video_selector_filter = ""
        self._pending_readiness_snapshot = {}

        # Project overview widgets/state
        self.project_overview_frame = None
        self.project_overview_tree = None
        self.project_status_vars = {}
        self._project_status_containers = {}
        self._overview_refresh_job = None
        self._pending_overview_status = None
        self._overview_status_append = False
        self._last_overview_counts = {}
        self._overview_video_index: dict[str, dict] = {}
        self._overview_context_menu: Menu | None = None
        self._overview_menu_font: tkfont.Font | None = None

        # Arduino dashboard state (live projects)
        self.arduino_dashboard_frame = None
        self.arduino_status_var = StringVar(value="Desconectado")
        self.arduino_status_indicator = None
        self.arduino_last_command_var = StringVar(value="-")
        self.arduino_log_text = None
        self.external_trigger_notice_var = StringVar(value="")
        self.external_trigger_notice_label = None
        self._external_notice_default_bg = None
        self._external_notice_default_fg = None

        self.set_active_weight_in_dropdown(self.controller.active_weight_name)
        self.update_openvino_checkbox(self.controller.use_openvino)
        self.update_openvino_status_display(self.controller.get_openvino_status())

        self._configure_styles()
        self._create_welcome_frame()

        if self.event_bus is not None:
            self._register_event_bus_handlers()
            self._schedule_event_bus_poll()

        # Subscribe to StateManager state changes for reactive UI updates
        self._subscribe_to_state_changes()

    def _subscribe_to_state_changes(self) -> None:
        """Subscribe to StateManager events for reactive UI updates."""
        from zebtrack.core.state_manager import StateCategory

        # Subscribe to recording state changes
        self.controller.state_manager.subscribe(
            StateCategory.RECORDING, self._on_recording_state_changed
        )

        # Subscribe to processing state changes
        self.controller.state_manager.subscribe(
            StateCategory.PROCESSING, self._on_processing_state_changed
        )

        # Subscribe to detector state changes
        self.controller.state_manager.subscribe(
            StateCategory.DETECTOR, self._on_detector_state_changed
        )

        # Subscribe to project state changes
        self.controller.state_manager.subscribe(
            StateCategory.PROJECT, self._on_project_state_changed
        )

        log.info(
            "gui.state_observers.subscribed",
            categories=["RECORDING", "PROCESSING", "DETECTOR", "PROJECT"],
        )

    def _on_recording_state_changed(self, category, key, old_value, new_value) -> None:
        """Handle recording state changes."""
        if key == "is_recording":
            # Schedule UI update on main thread
            self.root.after(0, self._update_recording_ui, new_value)
        elif key == "arduino_connected":
            # Schedule Arduino UI update on main thread
            self.root.after(0, self._update_arduino_ui, new_value)

    def _on_processing_state_changed(self, category, key, old_value, new_value) -> None:
        """Handle processing state changes."""
        if key == "is_processing":
            # Schedule UI update on main thread
            self.root.after(0, self._update_processing_ui, new_value)

    def _on_detector_state_changed(self, category, key, old_value, new_value) -> None:
        """Handle detector state changes."""
        if key == "detector_initialized":
            # Schedule UI update on main thread
            self.root.after(0, self._update_detector_ui, new_value)

    def _on_project_state_changed(self, category, key, old_value, new_value) -> None:
        """Handle project state changes."""
        if key == "project_path":
            # Schedule project UI update on main thread
            self.root.after(0, self._update_project_ui, new_value)

    def _update_recording_ui(self, is_recording: bool) -> None:
        """Update UI elements based on recording state."""
        if is_recording:
            log.debug("gui.recording_state.started")
            # Update recording button states if they exist
            if self.start_rec_btn:
                self.start_rec_btn.config(state="disabled")
            if self.stop_rec_btn:
                self.stop_rec_btn.config(state="normal")
        else:
            log.debug("gui.recording_state.stopped")
            # Update recording button states if they exist
            if self.start_rec_btn:
                self.start_rec_btn.config(state="normal")
            if self.stop_rec_btn:
                self.stop_rec_btn.config(state="disabled")

    def _update_processing_ui(self, is_processing: bool) -> None:
        """Update UI elements based on processing state."""
        if is_processing:
            log.debug("gui.processing_state.started")
            # Disable process button during processing
            if self.process_video_btn:
                self.process_video_btn.config(state="disabled")
        else:
            log.debug("gui.processing_state.stopped")
            # Re-enable process button after processing
            if self.process_video_btn:
                self.process_video_btn.config(state="normal")

    def _update_detector_ui(self, detector_initialized: bool) -> None:
        """Update UI elements based on detector state."""
        if detector_initialized:
            log.debug("gui.detector_state.initialized")
            # Detector is ready - UI elements can be enabled
        else:
            log.debug("gui.detector_state.uninitialized")
            # Detector not ready - disable dependent UI elements

    def _update_arduino_ui(self, arduino_connected: bool) -> None:
        """Update UI elements based on Arduino connection state."""
        if arduino_connected:
            log.debug("gui.arduino_state.connected")
            # Update Arduino status indicator if it exists
            if hasattr(self, "arduino_status_var"):
                self.arduino_status_var.set("Conectado")
            if hasattr(self, "arduino_status_indicator"):
                try:
                    self.arduino_status_indicator.config(style="success.TLabel")
                except Exception:
                    pass  # Ignore if widget doesn't exist yet
        else:
            log.debug("gui.arduino_state.disconnected")
            # Update Arduino status indicator if it exists
            if hasattr(self, "arduino_status_var"):
                self.arduino_status_var.set("Desconectado")
            if hasattr(self, "arduino_status_indicator"):
                try:
                    self.arduino_status_indicator.config(style="danger.TLabel")
                except Exception:
                    pass  # Ignore if widget doesn't exist yet

    def _update_project_ui(self, project_path) -> None:
        """Update UI elements based on project state."""
        if project_path:
            log.debug("gui.project_state.loaded", project_path=str(project_path))
            # Project loaded - update window title or status
        else:
            log.debug("gui.project_state.closed")
            # Project closed - show welcome screen

    def _build_status_icon_legend(self, *, include_summary: bool = False) -> str:
        """Compose a compact legend string for the status glyphs."""
        legend_parts = [
            f"{STATUS_SYMBOLS['arena']} ✓ Arena",
            f"{STATUS_SYMBOLS['rois']} ✓ ROIs",
            f"{STATUS_SYMBOLS['trajectory']} ✓ Trajetória",
        ]
        if include_summary:
            legend_parts.append(f"{STATUS_SYMBOLS['summary']} ✓ Sumário")
        legend_parts.append("✗ Ausente")
        return "Legenda: " + " | ".join(legend_parts)

    # --- Event bus helpers -------------------------------------------------

    def _register_event_bus_handlers(self) -> None:
        self._event_bus_handlers = {
            EventType.CALLABLE: self._handle_callable_event,
            EventType.NAMED: self._handle_named_event,
        }

    def _handle_callable_event(self, payload: CallableEvent) -> None:
        try:
            payload.execute()
        except Exception:
            log.warning("gui.event_bus.callable_failed", exc_info=True)

    def _handle_named_event(self, payload: NamedEvent) -> None:
        """Dispatch named events to controller subscribers."""
        try:
            if self.event_bus:
                self.event_bus.dispatch_named_event(payload)
        except Exception:
            log.warning(
                "gui.event_bus.named_event_failed",
                event_name=payload.event_name,
                exc_info=True,
            )

    def publish_event(self, event_name: str, data: dict[str, Any] | None = None) -> None:
        """Publish a named event to the controller via the event bus.

        Falls back to direct controller method call if event bus is not available.

        Args:
            event_name: Name of the event (from Events class)
            data: Optional event data dictionary
        """
        if self.event_bus:
            self.event_bus.publish_event(event_name, data or {})
        else:
            # Fallback to direct controller call (backward compatibility)
            # This path is only used when event bus is disabled
            log.debug("gui.publish_event.no_bus", event_name=event_name)

    def _schedule_event_bus_poll(self) -> None:
        if self.event_bus is None:
            return
        if self._event_bus_after_id is None:
            self._event_bus_after_id = self.root.after(
                self._event_bus_poll_interval_ms,
                self._poll_event_bus,
            )

    def _poll_event_bus(self) -> None:
        self._event_bus_after_id = None
        if self.event_bus is None:
            return

        events = self.event_bus.drain(max_items=50)
        processed = 0
        for event in events:
            handler = self._event_bus_handlers.get(event.type)
            if handler is None:
                log.warning(
                    "gui.event_bus.unhandled_event",
                    event_type=event.type.name,
                )
                continue
            try:
                handler(event.payload)
                processed += 1
            except Exception:
                log.warning(
                    "gui.event_bus.handler_error",
                    event_type=event.type.name,
                    exc_info=True,
                )

        if processed:
            log.debug("gui.event_bus.processed", count=processed)

        self._schedule_event_bus_poll()

    @staticmethod
    def _extract_setting(root: Any, path: tuple[str, ...], default: Any) -> Any:
        current = root
        for attr in path:
            if current is None:
                return default
            current = getattr(current, attr, None)
        return current if current is not None else default

    @staticmethod
    def _deep_merge_dicts(
        base: dict[str, Any],
        override: dict[str, Any],
    ) -> dict[str, Any]:
        result = copy.deepcopy(base)
        for key, value in override.items():
            if isinstance(value, dict) and key in result and isinstance(result[key], dict):
                result[key] = ApplicationGUI._deep_merge_dicts(result[key], value)
            else:
                result[key] = value
        return result

    def stop_event_bus_polling(self) -> None:
        if self._event_bus_after_id is not None:
            try:
                self.root.after_cancel(self._event_bus_after_id)
            except Exception:
                log.warning("gui.event_bus.stop_failed", exc_info=True)
            finally:
                self._event_bus_after_id = None

    @staticmethod
    def _get_zone_summary_helper_text() -> str:
        return (
            f"{STATUS_SYMBOLS['summary']} indica vídeos prontos para gerar "
            "trajetórias (arena e ROIs salvos). O valor mostra quantos ainda "
            "aguardam processamento."
        )

    def _cleanup_single_analysis_button(self):
        """Destroys the single analysis button if it exists."""
        if (
            hasattr(self, "start_single_analysis_btn")
            and self.start_single_analysis_btn is not None
        ):
            if self.start_single_analysis_btn.winfo_exists():
                self.start_single_analysis_btn.destroy()
            self.start_single_analysis_btn = None

    def _create_welcome_frame(self):
        """Creates the initial UI for project selection and model configuration."""
        self._cleanup_single_analysis_button()
        # CRITICAL: Force process all pending GUI events before cleanup
        # This ensures all scheduled callbacks are executed
        self.root.update_idletasks()

        # Reset + destroy analysis-related widgets
        self._reset_analysis_widgets()

        # Force final GUI update before creating welcome frame
        self.root.update_idletasks()

        reset_geometry_if_not_maximized(self.root)
        self.welcome_frame = ttk.Frame(self.root, padding="10")
        self.welcome_frame.pack(expand=True, fill="both")

        # --- Title ---
        ttk.Label(
            self.welcome_frame,
            text="Bem-vindo ao Controlador Zebtrack",
            font=("Helvetica", 16),
        ).pack(pady=(0, 15))

        # Project actions and model status widgets
        self._build_project_actions(self.welcome_frame)
        self._build_model_status(self.welcome_frame)

    def _reset_analysis_widgets(self) -> None:
        """Encapsula a limpeza e destruição de widgets da aba de análise."""
        # Break the cleanup into smaller helpers to reduce cognitive complexity
        self._reset_analysis_media()
        self._reset_analysis_progress_and_metadata()
        self._reset_roi_and_visual_frames()
        self._destroy_notebook_and_main_controls()
        self.analysis_tab_frame = None

    def _reset_analysis_media(self) -> None:
        """Reset media-related widgets such as analysis image overlays."""
        if hasattr(self, "analysis_video_label") and self.analysis_video_label:
            try:
                if self.analysis_video_label.winfo_exists():
                    self.analysis_video_label.configure(image="")
                    self._analysis_overlay_image = None
            except Exception:
                pass

    def _reset_analysis_progress_and_metadata(self) -> None:
        """Reset progress indicators and analysis metadata to defaults."""
        try:
            self.hide_progress_bar()
        except Exception:
            pass

        try:
            self.analysis_status_var.set("Nenhuma análise em andamento.")
        except Exception:
            pass

        try:
            self.analysis_task_var.set(self._default_analysis_task_text())
        except Exception:
            pass

        try:
            self._set_analysis_metadata_defaults()
        except Exception:
            pass

        if hasattr(self, "progress_labels") and self.progress_labels:
            for var in self.progress_labels.values():
                try:
                    var.set("-")
                except Exception:
                    pass

    def _reset_roi_and_visual_frames(self) -> None:
        """Handle ROI canvas and visualization frame teardown."""
        if hasattr(self, "roi_canvas") and self.roi_canvas:
            try:
                if self.roi_canvas.winfo_exists():
                    self.roi_canvas.pack_forget()
            except Exception:
                pass

        # Destroy viz_frame (parent frame)
        if hasattr(self, "viz_frame") and self.viz_frame:
            try:
                if self.viz_frame.winfo_exists():
                    self.viz_frame.destroy()
            except Exception:
                pass
            self.viz_frame = None

        # Clean up zone tab frame components
        if hasattr(self, "zone_tab_frame") and self.zone_tab_frame:
            try:
                if self.zone_tab_frame.winfo_exists():
                    self.zone_tab_frame.destroy()
            except Exception:
                pass
            self.zone_tab_frame = None
            self.zone_summary_frame = None
            self.zone_summary_cards = {}

    def _destroy_notebook_and_main_controls(self) -> None:
        """Destroy the main notebook and controls, clear project overview state."""
        if self.notebook:
            self.notebook.destroy()
            self.notebook = None
        if self.main_controls_frame:
            self.main_controls_frame.destroy()
            self.main_controls_frame = None
            self.arduino_dashboard_frame = None
            self.arduino_log_text = None
            self.arduino_status_indicator = None
            self.external_trigger_notice_label = None
            try:
                self.external_trigger_notice_var.set("")
            except Exception:
                pass
            try:
                self.arduino_status_var.set("Desconectado")
                self.arduino_last_command_var.set("-")
            except Exception:
                pass
            if self._overview_refresh_job is not None:
                try:
                    self.root.after_cancel(self._overview_refresh_job)
                except Exception:
                    pass
                self._overview_refresh_job = None
            self.project_overview_frame = None
            self.project_overview_tree = None
            self.project_status_vars.clear()
            self._project_status_containers.clear()
            self._last_overview_counts = {}

    def _build_project_actions(self, parent) -> None:
        """Create the project actions controls in the welcome frame."""
        project_actions_frame = ttk.LabelFrame(parent, text="Ações do Projeto", padding=10)
        project_actions_frame.pack(fill="x", pady=10, expand=True)

        ttk.Button(
            project_actions_frame,
            text="Calibração Global (Pesos e Diagnóstico)...",
            command=self._open_global_calibration_window,
        ).pack(fill="x", padx=10, pady=5)
        ttk.Button(
            project_actions_frame,
            text="Analisar Vídeo Único",
            command=self._on_analyze_single_video_clicked,
        ).pack(fill="x", padx=10, pady=5)
        ttk.Button(
            project_actions_frame,
            text="Criar Novo Projeto",
            command=self._create_project_workflow,
        ).pack(fill="x", padx=10, pady=5)
        ttk.Button(
            project_actions_frame,
            text="Abrir Projeto Existente",
            command=self._open_project_workflow,
        ).pack(fill="x", padx=10, pady=5)

    def _build_model_status(self, parent) -> None:
        """Create the model status display in the welcome frame."""
        model_status_frame = ttk.LabelFrame(parent, text="Estado do Modelo de Detecção", padding=10)
        model_status_frame.pack(fill="x", pady=10, expand=True)
        ttk.Label(
            model_status_frame,
            textvariable=self._active_weight_display_var,
        ).pack(anchor="w")
        ttk.Label(
            model_status_frame,
            textvariable=self._openvino_display_var,
        ).pack(anchor="w", pady=(4, 0))

    def _initialize_theme(self) -> None:
        """Apply a modern ttkbootstrap theme if the library is available."""
        if ttkb is None:
            log.debug("ui.theme.bootstrap_missing")
            return

        preferred_theme = getattr(settings, "ui_theme_name", None) or getattr(
            settings, "ui_theme", None
        )
        theme_name = preferred_theme or "cosmo"

        # ttkbootstrap changed its API in some versions and may no longer accept
        # the `master` keyword in Style.__init__.
        #
        # Behaviour:
        # - Older ttkbootstrap accepted `master=self.root` in Style(...)
        # - Newer releases removed that kwarg and raise TypeError if present
        #
        # Strategy: try the call that includes `master` first (compatible with
        # older ttkbootstrap), and on TypeError retry without `master`. This
        # keeps the code compatible across multiple installed versions. If you
        # prefer to enforce a single supported ttkbootstrap version, pin an
        # appropriate range in `pyproject.toml` (e.g. "ttkbootstrap~=1.1"),
        # and remove the fallback.
        #
        # We also log the installed ttkbootstrap version when falling back so
        # maintainers can identify mismatches in CI or user environments.
        # Resolve installed ttkbootstrap version for better logging. Try
        # importlib.metadata first (Python 3.8+), fallback to pkg_resources if
        # importlib.metadata is not available or package metadata is missing.
        # Detect installed ttkbootstrap version without importing pkg_resources
        # to avoid triggering setuptools/pkg_resources deprecation warnings.
        ttk_version = getattr(ttkb, "__version__", None)
        try:
            from importlib.metadata import PackageNotFoundError
            from importlib.metadata import version as _pkg_version

            try:
                ttk_version = _pkg_version("ttkbootstrap")
            except PackageNotFoundError:
                # leave ttk_version as ttkb.__version__ if present
                pass
        except Exception:
            # importlib.metadata not available or failed; keep ttkb.__version__
            pass

        if not ttk_version:
            ttk_version = "unknown"

        try:
            self._ttkbootstrap_style = ttkb.Style(theme=theme_name, master=self.root)
        except TypeError:
            # Older/newer mismatch: try without the master kwarg
            try:
                self._ttkbootstrap_style = ttkb.Style(theme=theme_name)
                log.warning(
                    "ui.theme.bootstrap_master_removed",
                    message=(
                        "ttkbootstrap.Style no longer accepts 'master'; "
                        "initialized Style without master keyword"
                    ),
                    ttkbootstrap_version=ttk_version,
                    theme=theme_name,
                )
            except Exception:
                log.warning(
                    "ui.theme.bootstrap_failed",
                    theme=theme_name,
                    exc_info=True,
                )
                self._ttkbootstrap_style = None
                self._ttkbootstrap_theme = None
                return
        except Exception:
            log.warning(
                "ui.theme.bootstrap_failed",
                theme=theme_name,
                exc_info=True,
            )
            self._ttkbootstrap_style = None
            self._ttkbootstrap_theme = None
            return

        # If we get here, _ttkbootstrap_style is set. Configure theme usage and
        # root background if the theme provides a frame background color.
        try:
            active_theme = self._ttkbootstrap_style.theme_use()
            self._ttkbootstrap_theme = active_theme

            frame_bg = self._ttkbootstrap_style.lookup("TFrame", "background")
            if frame_bg:
                self.root.configure(background=frame_bg)

            log.debug("ui.theme.bootstrap_applied", theme=active_theme)
        except Exception:
            # If anything goes wrong after creating the Style instance, log and
            # clear the style references so callers can fall back to ttk.
            log.warning(
                "ui.theme.bootstrap_failed_post_init",
                theme=theme_name,
                exc_info=True,
            )
            self._ttkbootstrap_style = None
            self._ttkbootstrap_theme = None

    def _configure_styles(self) -> None:
        """Configura estilos personalizados para os componentes ttk usados pela GUI."""
        style = ttk.Style(self.root)
        self._style = style

        try:
            style.theme_use()
        except Exception:  # pragma: no cover - defensive safeguard
            style.theme_use("default")

        base_background = (
            style.lookup("TNotebook", "background", None)
            or (
                self._ttkbootstrap_style.lookup("TFrame", "background")
                if self._ttkbootstrap_style is not None
                else None
            )
            or "#f6f7fb"
        )
        accent_background = (
            style.lookup("TNotebook.Tab", "background", None, ("selected",))
            or style.lookup("TFrame", "background", None)
            or "#ffffff"
        )
        tab_inactive = style.lookup("TNotebook.Tab", "background", None) or "#dce3ee"
        border_color = (
            style.lookup("TNotebook", "bordercolor", None)
            or style.lookup("TNotebook", "lightcolor", None)
            or "#c5ccd9"
        )
        text_active = style.lookup("TNotebook.Tab", "foreground", None, ("selected",)) or "#1d2733"
        text_inactive = style.lookup("TNotebook.Tab", "foreground", None) or "#4a5568"

        style.configure(
            "Zebtrack.TNotebook",
            background=base_background,
            borderwidth=0,
            tabmargins=(10, 6, 10, 0),
        )

        style.configure(
            "Zebtrack.TNotebook.Tab",
            background=tab_inactive,
            padding=(18, 10),
            font=("Segoe UI", 10, "bold"),
            foreground=text_inactive,
            bordercolor=border_color,
        )

        style.map(
            "Zebtrack.TNotebook.Tab",
            background=[("selected", accent_background), ("!selected", tab_inactive)],
            foreground=[("selected", text_active), ("!selected", text_inactive)],
            bordercolor=[("selected", "#4c6997"), ("!selected", border_color)],
        )

        style.configure(
            "Zebtrack.TNotebook.Tab",
            focuscolor="",
        )
        style.configure("Zebtrack.TNotebook", padding=(4, 4))

    def _open_global_calibration_window(self):
        with self.controller.global_calibration_session():
            CalibrationDialog(self.root, self.controller)

    def _open_project_calibration_window(self):
        if not getattr(self.controller.project_manager, "project_path", None):
            self.show_warning(
                "Nenhum Projeto",
                "Abra um projeto antes de ajustar a calibração específica.",
            )
            return

        CalibrationDialog(self.root, self.controller)
        self.update_openvino_checkbox(self.controller.use_openvino)
        self.set_active_weight_in_dropdown(self.controller.active_weight_name)
        self.update_openvino_status_display(self.controller.get_openvino_status())

    def _open_project_model_preferences(self):
        if not getattr(self.controller.project_manager, "project_path", None):
            self.show_warning(
                "Nenhum Projeto",
                "Abra um projeto antes de ajustar as preferências específicas.",
            )
            return

        dialog = ProjectModelOverridesDialog(self.root, self.controller)
        if dialog.result:
            self.update_openvino_checkbox(self.controller.use_openvino)
            self.set_active_weight_in_dropdown(self.controller.active_weight_name)
            self.update_openvino_status_display(self.controller.get_openvino_status())

    def _on_tab_changed(self, event):
        """
        Handle tab change event to ensure analysis overlay is hidden when not on
        analysis tab.
        """
        if not self.notebook:
            return

        current_tab = self.notebook.select()
        analysis_tab_id = str(self.analysis_tab_frame) if self.analysis_tab_frame else ""

        if self.analysis_active:
            self.canvas_view_mode = (
                "analysis" if analysis_tab_id and current_tab == analysis_tab_id else "zones"
            )
            if self.toggle_view_btn:
                if current_tab == analysis_tab_id:
                    self.toggle_view_btn.config(text="Ver Configuração de Zonas")
                else:
                    self.toggle_view_btn.config(text="Ver Análise em Progresso")

    def _create_main_control_frame(self):
        """Creates the main UI with tabs for controlling the app."""
        if self.welcome_frame:
            self.welcome_frame.destroy()
        reset_geometry_if_not_maximized(self.root)

        self.notebook = ttk.Notebook(self.root, style="Zebtrack.TNotebook")
        self.notebook.pack(expand=True, fill="both", padx=5, pady=5)

        # Bind tab change event to hide analysis overlay when switching tabs
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # Create the tabs
        self._create_main_controls_tab()
        if self.controller.project_manager.get_project_type() == "live":
            self._create_progress_grid_tab()
        self._create_roi_analysis_tab()
        self._create_configuration_tab()
        if self.controller.project_manager.get_project_type() == "pre-recorded":
            self._create_pipeline_processing_tab()
        self._create_analysis_tab()
        self._create_reports_tab()

        # Status frame below the notebook
        project_type_str = self.controller.project_manager.get_project_type()
        if project_type_str == "live":
            project_type_display = "Ao Vivo"
        elif project_type_str == "pre-recorded":
            project_type_display = "Pré-gravado"
        else:
            project_type_display = project_type_str

        status_text = (
            f"Projeto: {self.controller.project_manager.get_project_name()} "
            f"({project_type_display})"
        )
        self.status_var.set(status_text)
        status_frame = Frame(self.root)
        status_frame.pack(pady=5, fill="x", padx=10, side="bottom")
        Label(status_frame, textvariable=self.status_var).pack()

        # Ensure analysis UI starts hidden
        self.hide_progress_bar()

    def _create_configuration_tab(self) -> None:
        """Create the advanced configuration editor tab."""
        if not self.notebook:
            return

        self.config_tab_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.config_tab_frame, text="Config. Avançadas")
        self._config_roi_rule_widgets = []

        intro = (
            "Edite parâmetros avançados do config.yaml sem sair do aplicativo. "
            "As alterações são persistidas em config.local.yaml e recarregadas "
            "automaticamente por settings.load_settings()."
        )
        ttk.Label(
            self.config_tab_frame,
            text=intro,
            wraplength=560,
            justify="left",
        ).pack(fill="x", pady=(0, 12))

        config_path_hint = ttk.Label(
            self.config_tab_frame,
            text=(
                f"Arquivos monitorados: {Path('config.yaml').absolute()} → "
                f"{Path('config.local.yaml').absolute()}"
            ),
            wraplength=560,
            justify="left",
            font=("TkDefaultFont", 8),
        )
        config_path_hint.pack(fill="x", pady=(0, 12))

        # Video processing settings
        video_frame = ttk.LabelFrame(
            self.config_tab_frame,
            text="Processamento de Vídeo",
            padding=10,
        )
        video_frame.pack(fill="x", pady=6)
        video_frame.columnconfigure(1, weight=0)
        video_frame.columnconfigure(2, weight=1)

        ttk.Label(video_frame, text="FPS de saída (MP4):").grid(
            row=0, column=0, sticky="w", padx=(0, 6), pady=2
        )
        ttk.Entry(video_frame, textvariable=self.config_fps_var, width=8).grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(
            video_frame,
            text="Define a taxa de quadros do vídeo salvo em disco.",
            font=("TkDefaultFont", 8),
            wraplength=320,
        ).grid(row=0, column=2, sticky="w")

        ttk.Label(video_frame, text="Intervalo de processamento (N):").grid(
            row=1, column=0, sticky="w", padx=(0, 6), pady=2
        )
        ttk.Entry(video_frame, textvariable=self.config_processing_interval_var, width=8).grid(
            row=1, column=1, sticky="w"
        )
        ttk.Label(
            video_frame,
            text="Processa 1 frame a cada N frames originais.",
            font=("TkDefaultFont", 8),
            wraplength=320,
        ).grid(row=1, column=2, sticky="w")

        ttk.Label(video_frame, text="Offset inicial (frames):").grid(
            row=2, column=0, sticky="w", padx=(0, 6), pady=2
        )
        ttk.Entry(video_frame, textvariable=self.config_processing_offset_var, width=8).grid(
            row=2, column=1, sticky="w"
        )
        ttk.Label(
            video_frame,
            text="Garante que offset < intervalo para manter a cadência correta.",
            font=("TkDefaultFont", 8),
            wraplength=320,
        ).grid(row=2, column=2, sticky="w")

        # Trajectory smoothing settings
        smoothing_frame = ttk.LabelFrame(
            self.config_tab_frame,
            text="Suavização de Trajetória",
            padding=10,
        )
        smoothing_frame.pack(fill="x", pady=6)
        smoothing_frame.columnconfigure(2, weight=1)

        ttk.Label(smoothing_frame, text="Window length (ímpar):").grid(
            row=0, column=0, sticky="w", padx=(0, 6), pady=2
        )
        ttk.Entry(smoothing_frame, textvariable=self.config_window_length_var, width=8).grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(
            smoothing_frame,
            text="Usado pelo filtro Savitzky-Golay. Precisa ser ímpar e ≥ 3.",
            font=("TkDefaultFont", 8),
            wraplength=320,
        ).grid(row=0, column=2, sticky="w")

        ttk.Label(smoothing_frame, text="Polyorder:").grid(
            row=1, column=0, sticky="w", padx=(0, 6), pady=2
        )
        ttk.Entry(smoothing_frame, textvariable=self.config_polyorder_var, width=8).grid(
            row=1, column=1, sticky="w"
        )
        ttk.Label(
            smoothing_frame,
            text="Ordem do polinômio < window_length para evitar overfitting.",
            font=("TkDefaultFont", 8),
            wraplength=320,
        ).grid(row=1, column=2, sticky="w")

        # Recorder settings
        recorder_frame = ttk.LabelFrame(
            self.config_tab_frame,
            text="Recorder (Parquet/MP4)",
            padding=10,
        )
        recorder_frame.pack(fill="x", pady=6)
        recorder_frame.columnconfigure(2, weight=1)

        ttk.Label(recorder_frame, text="Flush automático (s):").grid(
            row=0, column=0, sticky="w", padx=(0, 6), pady=2
        )
        ttk.Entry(recorder_frame, textvariable=self.config_flush_interval_var, width=8).grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(
            recorder_frame,
            text="Define intervalo para descarregar buffers no Parquet.",
            font=("TkDefaultFont", 8),
            wraplength=320,
        ).grid(row=0, column=2, sticky="w")

        ttk.Label(recorder_frame, text="Limite de linhas por flush:").grid(
            row=1, column=0, sticky="w", padx=(0, 6), pady=2
        )
        ttk.Entry(recorder_frame, textvariable=self.config_flush_rows_var, width=8).grid(
            row=1, column=1, sticky="w"
        )
        ttk.Label(
            recorder_frame,
            text="Quando atingir este limite, os dados são gravados imediatamente.",
            font=("TkDefaultFont", 8),
            wraplength=320,
        ).grid(row=1, column=2, sticky="w")

        # ROI defaults
        roi_frame = ttk.LabelFrame(
            self.config_tab_frame,
            text="Parâmetros padrão de ROI",
            padding=10,
        )
        roi_frame.pack(fill="x", pady=6)
        roi_frame.columnconfigure(2, weight=1)

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
        config_roi_combo.bind("<<ComboboxSelected>>", self._on_roi_rule_change)
        self._config_roi_rule_widgets.append(config_roi_combo)
        ttk.Label(
            roi_frame,
            text="Selecione a lógica padrão aplicada ao carregar projetos.",
            font=("TkDefaultFont", 8),
            wraplength=320,
        ).grid(row=0, column=2, sticky="w")

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

        ttk.Label(
            roi_frame,
            text="Dica: use o painel de Zonas para testar combinações em tempo real.",
            font=("TkDefaultFont", 8),
            foreground="#555555",
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))

        actions_frame = ttk.Frame(self.config_tab_frame)
        actions_frame.pack(fill="x", pady=(12, 0))
        ttk.Button(
            actions_frame,
            text="Recarregar valores atuais",
            command=self._on_reset_global_config_form,
        ).pack(side="left")
        ttk.Button(
            actions_frame,
            text="Salvar em config.local.yaml",
            command=self._on_save_global_config,
        ).pack(side="right")

        ttk.Label(
            self.config_tab_frame,
            text=(
                "As validações avançadas (offset < intervalo, polyorder < janela, "
                "etc.) são aplicadas automaticamente ao salvar."
            ),
            wraplength=560,
            justify="left",
            font=("TkDefaultFont", 8),
        ).pack(fill="x", pady=(6, 0))

        self._reload_config_editor_values()

    def _reload_config_editor_values(self) -> None:
        """Refresh the configuration form with the latest loaded settings."""
        current = settings_module.settings
        if current is None:
            try:
                current = settings_module.load_settings()
                settings_module.settings = current
            except Exception as exc:  # pragma: no cover - defensive UI feedback
                self.show_error("Erro", f"Não foi possível carregar config.yaml: {exc}")
                return

        self.config_fps_var.set(
            str(self._extract_setting(current, ("video_processing", "fps"), 30))
        )
        self.config_processing_interval_var.set(
            str(
                self._extract_setting(
                    current,
                    ("video_processing", "processing_interval"),
                    10,
                )
            )
        )
        self.config_processing_offset_var.set(
            str(
                self._extract_setting(
                    current,
                    ("video_processing", "processing_offset"),
                    0,
                )
            )
        )
        self.config_flush_interval_var.set(
            str(
                self._extract_setting(
                    current,
                    ("recorder", "flush_interval_seconds"),
                    5.0,
                )
            )
        )
        self.config_flush_rows_var.set(
            str(
                self._extract_setting(
                    current,
                    ("recorder", "flush_row_threshold"),
                    500,
                )
            )
        )
        self.config_window_length_var.set(
            str(
                self._extract_setting(
                    current,
                    ("trajectory_smoothing", "window_length"),
                    7,
                )
            )
        )
        self.config_polyorder_var.set(
            str(
                self._extract_setting(
                    current,
                    ("trajectory_smoothing", "polyorder"),
                    3,
                )
            )
        )

        self.roi_inclusion_rule_var.set(
            self._extract_setting(
                current,
                ("roi_inclusion_rule",),
                self.roi_inclusion_rule_var.get(),
            )
        )
        self.roi_buffer_radius_var.set(
            str(
                self._extract_setting(
                    current,
                    ("roi_buffer_radius_value",),
                    float(self.roi_buffer_radius_var.get() or 0.5),
                )
            )
        )
        self.roi_overlap_ratio_var.set(
            str(
                self._extract_setting(
                    current,
                    ("roi_min_bbox_overlap_ratio",),
                    float(self.roi_overlap_ratio_var.get() or 0.1),
                )
            )
        )

        if getattr(self, "roi_rule_combo", None):
            try:
                self.roi_rule_combo.set(self.roi_inclusion_rule_var.get())
            except Exception:
                pass

        for combo in self._config_roi_rule_widgets:
            try:
                combo.set(self.roi_inclusion_rule_var.get())
            except Exception:
                pass

        self._on_roi_rule_change()

    def _on_reset_global_config_form(self) -> None:
        """Reset form fields to reflect current settings object."""
        self._reload_config_editor_values()
        self.show_info(
            "Valores recarregados",
            "Campos atualizados com os valores atuais do config.",
        )

    def _on_save_global_config(self) -> None:
        """Persist configuration overrides and reload global settings."""
        try:
            fps = int(self.config_fps_var.get().strip())
            processing_interval = int(self.config_processing_interval_var.get().strip())
            processing_offset = int(self.config_processing_offset_var.get().strip())
            flush_interval = float(self.config_flush_interval_var.get().strip())
            flush_rows = int(self.config_flush_rows_var.get().strip())
            window_length = int(self.config_window_length_var.get().strip())
            polyorder = int(self.config_polyorder_var.get().strip())
            buffer_radius = float(self.roi_buffer_radius_var.get().strip())
            overlap_ratio = float(self.roi_overlap_ratio_var.get().strip())
        except ValueError:
            self.show_error(
                "Erro de Validação",
                "Use apenas números válidos nos campos de configuração.",
            )
            return

        try:
            if fps <= 0:
                raise ValueError("FPS deve ser maior que 0.")
            if processing_interval <= 0:
                raise ValueError("O intervalo de processamento deve ser maior que 0.")
            if processing_offset < 0:
                raise ValueError("O offset deve ser maior ou igual a 0.")
            if flush_interval < 0:
                raise ValueError("O intervalo de flush deve ser >= 0.")
            if flush_rows < 1:
                raise ValueError("O limite de linhas para flush deve ser >= 1.")
            if window_length < 3 or window_length % 2 == 0:
                raise ValueError("Window length deve ser ímpar e pelo menos 3.")
            if polyorder < 1:
                raise ValueError("Polyorder deve ser pelo menos 1.")
        except ValueError as exc:
            self.show_error("Erro de Validação", str(exc))
            return

        update_payload: dict[str, Any] = {
            "video_processing": {
                "fps": fps,
                "processing_interval": processing_interval,
                "processing_offset": processing_offset,
            },
            "recorder": {
                "flush_interval_seconds": flush_interval,
                "flush_row_threshold": flush_rows,
            },
            "trajectory_smoothing": {
                "window_length": window_length,
                "polyorder": polyorder,
            },
            "roi_inclusion_rule": self.roi_inclusion_rule_var.get(),
            "roi_buffer_radius_value": buffer_radius,
            "roi_min_bbox_overlap_ratio": overlap_ratio,
        }

        active_settings = settings_module.settings
        if active_settings is None:
            try:
                active_settings = settings_module.load_settings()
                settings_module.settings = active_settings
            except Exception as exc:
                self.show_error("Erro", f"Não foi possível carregar config.yaml: {exc}")
                return

        merged = self._deep_merge_dicts(active_settings.model_dump(), update_payload)

        try:
            validated = settings_module.Settings.model_validate(merged)
        except ValidationError as exc:
            self.show_error("Erro de Validação", str(exc))
            return

        override_path = Path("config.local.yaml")
        try:
            if override_path.exists():
                with open(override_path, encoding="utf-8") as handle:
                    override_content = yaml.safe_load(handle) or {}
            else:
                override_content = {}

            merged_override = self._deep_merge_dicts(
                override_content,
                update_payload,
            )
            with open(override_path, "w", encoding="utf-8") as handle:
                yaml.safe_dump(
                    merged_override,
                    handle,
                    sort_keys=False,
                    allow_unicode=True,
                )
        except Exception as exc:
            self.show_error("Erro", f"Não foi possível salvar config.local.yaml: {exc}")
            return

        if settings_module.settings is None:
            settings_module.settings = validated
        else:
            for field_name in validated.model_fields:
                setattr(
                    settings_module.settings,
                    field_name,
                    getattr(validated, field_name),
                )

        self._reload_config_editor_values()
        self.show_info(
            "Configurações salvas",
            "Alterações registradas em config.local.yaml e aplicadas ao aplicativo.",
        )

    def _create_main_controls_tab(self):
        """Creates the tab with the main project controls."""
        self.main_controls_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.main_controls_frame, text="Controle Principal")

        project_type = self.controller.project_manager.get_project_type()
        self.process_video_btn = None

        controls_container = ttk.Frame(self.main_controls_frame)
        controls_container.pack(fill="x", pady=(0, 10))

        if project_type == "live":
            self.start_rec_btn = Button(
                controls_container,
                text="Iniciar Gravação",
                command=lambda: self.publish_event(Events.RECORDING_START, {}),
            )
            self.start_rec_btn.pack(side="left", padx=5)
            self.stop_rec_btn = Button(
                controls_container,
                text="Parar Gravação",
                command=lambda: self.publish_event(Events.RECORDING_STOP, {}),
                state="disabled",
            )
            self.stop_rec_btn.pack(side="left", padx=5)
        elif project_type == "pre-recorded":
            # Primary action: add/process new videos (legacy location)
            ttk.Button(
                controls_container,
                text="Adicionar e Processar Novos Vídeos/Pastas...",
                command=lambda: self.publish_event(Events.PROJECT_PROCESS_VIDEOS, {}),
            ).pack(side="left", padx=5)

            # Project-wide interval settings
            intervals_frame = ttk.LabelFrame(
                self.main_controls_frame, text="Intervalos de Processamento", padding=10
            )
            intervals_frame.pack(fill="x", pady=10, padx=10)

            # Analysis interval
            analysis_label_frame = ttk.Frame(intervals_frame)
            analysis_label_frame.pack(fill="x", pady=2)
            ttk.Label(analysis_label_frame, text="Intervalo de Análise (frames):").pack(side="left")
            ttk.Entry(analysis_label_frame, textvariable=self.analysis_interval_var, width=10).pack(
                side="right"
            )

            # Display interval
            display_label_frame = ttk.Frame(intervals_frame)
            display_label_frame.pack(fill="x", pady=2)
            ttk.Label(display_label_frame, text="Intervalo de Exibição (frames):").pack(side="left")
            ttk.Entry(display_label_frame, textvariable=self.display_interval_var, width=10).pack(
                side="right"
            )

        Button(
            controls_container,
            text="Fechar Projeto",
            command=lambda: self.publish_event(Events.PROJECT_CLOSE, {}),
        ).pack(side="right", padx=5)

        self._create_project_overview_panel(self.main_controls_frame)

        model_status_frame = ttk.LabelFrame(
            self.main_controls_frame,
            text="Estado do Modelo de Detecção",
            padding=10,
        )
        model_status_frame.pack(fill="x", pady=(10, 10))
        ttk.Label(
            model_status_frame,
            textvariable=self._active_weight_display_var,
        ).pack(anchor="w")
        ttk.Label(
            model_status_frame,
            textvariable=self._openvino_display_var,
        ).pack(anchor="w", pady=(4, 0))
        button_row = ttk.Frame(model_status_frame)
        button_row.pack(anchor="w", pady=(6, 0))
        ttk.Button(
            button_row,
            text="Calibração Global...",
            command=self._open_global_calibration_window,
        ).pack(side="left", padx=(0, 6))
        if getattr(self.controller.project_manager, "project_path", None):
            ttk.Button(
                button_row,
                text="Calibração do Projeto...",
                command=self._open_project_calibration_window,
            ).pack(side="left", padx=(0, 6))
        ttk.Button(
            button_row,
            text="Preferências deste Projeto...",
            command=self._open_project_model_preferences,
        ).pack(side="left")

        if project_type == "live":
            self.external_trigger_notice_label = Label(
                self.main_controls_frame,
                textvariable=self.external_trigger_notice_var,
                anchor="w",
                justify="left",
                wraplength=600,
                padx=10,
                pady=6,
            )
            self.external_trigger_notice_label.pack(fill="x", pady=(0, 8))
            self._external_notice_default_bg = self.external_trigger_notice_label.cget("background")
            self._external_notice_default_fg = self.external_trigger_notice_label.cget("foreground")

            self._build_arduino_dashboard(self.main_controls_frame)
            self.clear_external_trigger_notice()

        self._request_overview_refresh()

    def _create_project_overview_panel(self, parent: ttk.Frame) -> None:
        if not parent:
            return

        if self.project_overview_frame and self.project_overview_frame.winfo_exists():
            try:
                self.project_overview_frame.destroy()
            except Exception:
                pass

        self.project_overview_frame = ttk.LabelFrame(parent, text="Resumo do Projeto", padding=10)
        self.project_overview_frame.pack(fill="both", expand=True, pady=(10, 10))

        summary_frame = ttk.Frame(self.project_overview_frame)
        summary_frame.pack(fill="x", pady=(0, 8))

        self._project_status_containers.clear()

        for key in PROJECT_STATUS_WIDGET_ORDER:
            icon, label = self._get_status_meta(key)
            container = ttk.Frame(summary_frame)
            container.pack(side="left", padx=(0, 12))
            ttk.Label(container, text=f"{icon} {label}:", anchor="w").pack(side="left")
            var = self.project_status_vars.get(key)
            if not var:
                var = StringVar(value="0")
                self.project_status_vars[key] = var
            ttk.Label(
                container,
                textvariable=var,
                font=("Segoe UI", 10, "bold"),
            ).pack(side="left", padx=(4, 0))
            self._project_status_containers[key] = container

        tree_container = ttk.Frame(self.project_overview_frame)
        tree_container.pack(fill="both", expand=True)

        self.project_overview_tree = ttk.Treeview(
            tree_container,
            columns=("status", "data"),
            show="tree headings",
            height=10,
        )
        self.project_overview_tree.heading("#0", text="Estrutura do Projeto")
        self.project_overview_tree.heading("status", text="Status")
        self.project_overview_tree.heading("data", text="Dados")
        self.project_overview_tree.column("#0", width=320, stretch=True)
        self.project_overview_tree.column("status", width=180, anchor="w", stretch=False)
        self.project_overview_tree.column("data", width=260, anchor="w", stretch=True)

        scrollbar = ttk.Scrollbar(
            tree_container, orient="vertical", command=self.project_overview_tree.yview
        )
        self.project_overview_tree.configure(yscrollcommand=scrollbar.set)
        self.project_overview_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.project_overview_tree.tag_configure("status_pending", foreground="#92400e")
        self.project_overview_tree.tag_configure("status_processing", foreground="#b45309")
        self.project_overview_tree.tag_configure("status_processed", foreground="#0f5132")
        self.project_overview_tree.tag_configure("status_complete", foreground="#166534")
        self.project_overview_tree.tag_configure("status_failed", foreground="#b91c1c")

        self.project_overview_tree.bind(
            "<Double-Button-1>", self._on_project_overview_tree_double_click
        )
        self.project_overview_tree.bind("<Button-3>", self._on_project_overview_right_click)
        self.project_overview_tree.bind("<Control-Button-1>", self._on_project_overview_right_click)

    @staticmethod
    def _get_status_meta(status_key: str) -> tuple[str, str]:
        if status_key == "total":
            return "🧮", "Total"
        if status_key == "others":
            return "➕", "Outros"
        return PROJECT_STATUS_META.get(status_key, ("•", status_key.title()))

    def _request_overview_refresh(
        self,
        reason: str | None = None,
        *,
        append_summary: bool = False,
        immediate: bool = False,
    ) -> None:
        if reason is not None:
            self._pending_overview_status = reason
            self._overview_status_append = append_summary

        if self._overview_refresh_job is not None:
            try:
                self.root.after_cancel(self._overview_refresh_job)
            except Exception:
                pass
            self._overview_refresh_job = None

        if immediate:
            self._refresh_project_overview()
            return

        try:
            self._overview_refresh_job = self.root.after(150, self._refresh_project_overview)
        except Exception:
            self._refresh_project_overview()

    def refresh_project_views(
        self,
        reason: str | None = None,
        *,
        append_summary: bool = False,
        immediate: bool = False,
    ) -> None:
        """Refresh overview, pipeline, and reports panels in a single call."""

        log.info(
            "gui.project_refresh.dispatched",
            reason=reason,
            append_summary=append_summary,
            immediate=immediate,
        )

        self._request_overview_refresh(
            reason=reason,
            append_summary=append_summary,
            immediate=immediate,
        )

        if getattr(self, "pipeline_video_tree", None):
            self._refresh_pipeline_video_table()

        if getattr(self, "reports_tree", None):
            self.update_reports_tree()

    def _refresh_project_overview(self) -> None:
        self._overview_refresh_job = None

        controller = getattr(self, "controller", None)
        if not controller or not controller.project_manager:
            log.debug("gui.refresh_overview.no_controller_or_pm")
            return

        pm = controller.project_manager
        all_videos = pm.get_all_videos() or []

        log.debug(
            "gui.refresh_overview.start",
            video_count=len(all_videos),
            has_project_path=bool(pm.project_path),
        )

        # Allow display even when there's no project file
        # This enables single video workflow results to be shown
        if not all_videos and not pm.project_path:
            # No videos and no project - nothing to show
            log.debug("gui.refresh_overview.no_videos_and_no_project")
            return

        counts: Counter = Counter(
            (str(video.get("status") or "pending")).strip().lower() for video in all_videos
        )
        total = sum(counts.values())

        log.debug(
            "gui.refresh_overview.updating",
            total=total,
            counts=dict(counts),
        )

        self._update_project_overview_summary(counts, total)
        self._update_project_overview_tree(pm, all_videos)
        self._refresh_zone_indicators(all_videos)

        if self._pending_overview_status is not None:
            summary_line = self._compose_overview_status_line(total, counts)
            if summary_line:
                if self._overview_status_append and self._pending_overview_status:
                    message = f"{self._pending_overview_status} • {summary_line}"
                elif self._pending_overview_status:
                    message = f"{self._pending_overview_status} — {summary_line}"
                else:
                    message = summary_line
                self.set_status(message)
            self._pending_overview_status = None
            self._overview_status_append = False

    def _compose_overview_status_line(self, total: int, counts: Counter) -> str:
        if total <= 0:
            return "Nenhum vídeo cadastrado."

        parts: list[str] = [f"🧮 {total} vídeo(s)"]
        for key in ("pending", "processing", "processed", "complete", "failed"):
            value = counts.get(key, 0)
            if value:
                icon, _ = PROJECT_STATUS_META.get(key, ("•", key.title()))
                parts.append(f"{icon} {value}")

        others = sum(count for status, count in counts.items() if status not in PROJECT_STATUS_META)
        if others:
            parts.append(f"➕ {others}")

        return " • ".join(parts)

    def _update_project_overview_summary(self, counts: Counter, total: int) -> None:
        if not self.project_overview_frame or not self.project_overview_frame.winfo_exists():
            return

        known_statuses = set(PROJECT_STATUS_META.keys())
        others_count = sum(
            value for status, value in counts.items() if status not in known_statuses
        )

        for key in PROJECT_STATUS_WIDGET_ORDER:
            if key == "total":
                value = total
            elif key == "others":
                value = others_count
            else:
                value = counts.get(key, 0)

            var = self.project_status_vars.setdefault(key, StringVar(value="0"))
            var.set(str(value))

            container = self._project_status_containers.get(key)
            if not container:
                continue

            should_show = key == "total" or value > 0
            if should_show:
                if not container.winfo_ismapped():
                    container.pack(side="left", padx=(0, 12))
            else:
                if container.winfo_ismapped():
                    container.pack_forget()

    def _update_project_overview_tree(self, project_manager, all_videos: list[dict]) -> None:
        if not self.project_overview_tree or not self.project_overview_tree.winfo_exists():
            return

        for item in self.project_overview_tree.get_children():
            self.project_overview_tree.delete(item)

        self._overview_video_index = {}

        if not all_videos:
            return

        hierarchy = self._build_video_hierarchy_data(all_videos, "")

        for group_id, group_data in sorted(
            hierarchy.items(), key=lambda item: str(item[1]["display"]).lower()
        ):
            days_dict = group_data.get("days") or {}
            group_entries = [entry for videos in days_dict.values() for entry in videos or []]
            if not group_entries:
                continue

            group_counts: Counter = Counter(
                (str(entry.get("status") or "pending")).strip().lower() for entry in group_entries
            )
            status_summary = self._format_status_summary(group_counts)
            data_summary = self._summarize_batch_data(group_entries)

            group_node = self.project_overview_tree.insert(
                "",
                "end",
                text=f"🏷️ {group_data['display']}",
                values=(status_summary, data_summary),
                open=True,
            )

            for day_id, entries in sorted(
                days_dict.items(), key=lambda item: self._video_sort_key(item[0])
            ):
                entries = entries or []
                if not entries:
                    continue

                day_counts: Counter = Counter(
                    (str(entry.get("status") or "pending")).strip().lower() for entry in entries
                )
                day_status = self._format_status_summary(day_counts)
                day_data = self._summarize_batch_data(entries)
                sample_metadata = entries[0].get("metadata") if entries else None
                day_title = self._build_day_title(day_id, sample_metadata)

                day_node = self.project_overview_tree.insert(
                    group_node,
                    "end",
                    text=f"📅 {day_title}",
                    values=(day_status, day_data),
                    open=False,
                )

                for entry in sorted(
                    entries,
                    key=lambda item: self._video_sort_key(item.get("subject")),
                ):
                    path = entry.get("path") or ""
                    filename = entry.get("filename") or (
                        os.path.basename(path) if path else "(sem arquivo)"
                    )
                    metadata = entry.get("metadata") or {}
                    meta_snippet = self._format_video_metadata(metadata)

                    subject_label = self._format_subject_label(entry.get("subject"))
                    display_name = f"🐟 Sujeito {subject_label}"
                    if filename:
                        display_name = f"{display_name} ({filename})"
                    if meta_snippet:
                        display_name = f"{display_name} [{meta_snippet}]"

                    status_key = str(entry.get("status") or "pending").strip().lower()
                    status_display = self._format_status_label(status_key)
                    data_badges = self._format_data_badges(entry)

                    tags = tuple(tag for tag in (path, f"status_{status_key}") if tag)

                    self.project_overview_tree.insert(
                        day_node,
                        "end",
                        text=display_name,
                        values=(status_display, data_badges),
                        tags=tags,
                    )

                    if path:
                        self._overview_video_index[path] = dict(entry)

    def _format_status_label(self, status_key: str) -> str:
        icon, label = self._get_status_meta(status_key)
        return f"{icon} {label}"

    def _format_status_summary(self, counts: Counter) -> str:
        parts: list[str] = []
        for key in PROJECT_STATUS_META:
            value = counts.get(key, 0)
            if value:
                icon, _ = PROJECT_STATUS_META[key]
                parts.append(f"{icon} {value}")

        others = sum(count for status, count in counts.items() if status not in PROJECT_STATUS_META)
        if others:
            parts.append(f"➕ {others}")

        return " | ".join(parts) if parts else "-"

    @staticmethod
    def _format_status_ratio(symbol_key: str, completed: int, total: int) -> str:
        symbol = STATUS_SYMBOLS[symbol_key]
        safe_total = max(total, 0)
        clamped_completed = max(0, min(completed, safe_total)) if safe_total else 0
        if safe_total:
            return f"{symbol} {clamped_completed}/{safe_total}"
        return f"{symbol} 0/0"

    def _summarize_batch_data(self, videos: list[dict]) -> str:
        if not videos:
            return "-"

        total = len(videos)
        arena_count = sum(1 for video in videos if video.get("has_arena"))
        roi_count = sum(1 for video in videos if video.get("has_rois"))
        traj_count = sum(1 for video in videos if video.get("has_trajectory"))
        complete_count = sum(
            1
            for video in videos
            if video.get("has_complete_data")
            or (video.get("has_arena") and video.get("has_rois") and video.get("has_trajectory"))
        )

        return (
            f"{self._format_status_ratio('arena', arena_count, total)}  "
            f"{self._format_status_ratio('rois', roi_count, total)}  "
            f"{self._format_status_ratio('trajectory', traj_count, total)}  "
            f"{self._format_status_ratio('summary', complete_count, total)}"
        )

    def _format_data_badges(self, video: dict) -> str:
        has_arena = bool(video.get("has_arena"))
        has_rois = bool(video.get("has_rois"))
        has_trajectory = bool(video.get("has_trajectory"))
        has_complete = bool(video.get("has_complete_data")) or (
            has_arena and has_rois and has_trajectory
        )

        markers = [
            self._format_status_token(has_arena, "arena"),
            self._format_status_token(has_rois, "rois"),
            self._format_status_token(has_trajectory, "trajectory"),
            self._format_status_token(has_complete, "summary"),
        ]
        return "  ".join(markers)

    def _format_video_metadata(self, metadata: dict) -> str:
        if not metadata:
            return ""

        parts: list[str] = []
        group = metadata.get("group")
        if group not in (None, ""):
            parts.append(f"G:{group}")

        day = metadata.get("day")
        if day not in (None, ""):
            day_display = metadata.get("day_label") or self._format_day_display(day)
            parts.append(f"D:{day_display or day}")

        subject = metadata.get("subject")
        if subject not in (None, ""):
            parts.append(f"S:{self._format_subject_label(subject)}")

        return " ".join(parts)

    def _on_project_overview_tree_double_click(self, event) -> None:
        """Handle double-click events on the overview tree."""

        del event

        if not self.project_overview_tree:
            return

        item_id = self.project_overview_tree.focus()
        if not item_id:
            return

        tags = self.project_overview_tree.item(item_id, "tags") or ()
        if not tags:
            return

        video_path = tags[0]
        if not video_path or video_path.startswith("status_"):
            return

        if not os.path.exists(video_path):
            self.show_warning(
                "Arquivo não encontrado",
                f"O vídeo selecionado não foi localizado:\n{video_path}",
            )
            return

        success = self.load_video_frame_to_canvas(video_path, frame_number=0)
        if success:
            self._maybe_offer_zone_reuse(video_path)
            self.redraw_zones_from_project_data()
            message = f"Frame carregado: {os.path.basename(video_path)}"
            self.set_status(message)
            self._request_overview_refresh(reason=message, append_summary=True)
        else:
            self.show_error(
                "Erro ao Carregar",
                f"Não foi possível carregar o vídeo selecionado.\n{video_path}",
            )

    def _on_project_overview_right_click(self, event) -> None:
        tree = self.project_overview_tree
        if not tree or not tree.winfo_exists():
            return

        item_id = tree.identify_row(event.y)
        column_id = tree.identify_column(event.x)

        if not item_id or not column_id:
            return

        tree.selection_set(item_id)

        tags = tree.item(item_id, "tags") or ()
        video_path = None
        for tag in tags:
            if tag and not tag.startswith("status_"):
                video_path = tag
                break

        if not video_path:
            return

        asset = None
        if column_id == "#0":
            asset = "video"
        elif column_id == "#2":
            asset = self._resolve_overview_asset_from_click(item_id, event.x)

        if not asset:
            return

        self._show_overview_context_menu(event, video_path, asset)

    def _get_overview_badge_font(self) -> tkfont.Font:
        if self._overview_menu_font is None:
            tree = self.project_overview_tree
            font_name = tree.cget("font") if tree else ""
            try:
                if font_name:
                    self._overview_menu_font = tkfont.Font(font=font_name)
                else:
                    self._overview_menu_font = tkfont.nametofont("TkDefaultFont")
            except Exception:
                self._overview_menu_font = tkfont.nametofont("TkDefaultFont")

        return self._overview_menu_font

    def _resolve_overview_asset_from_click(self, item_id: str, event_x: int) -> str | None:
        tree = self.project_overview_tree
        if not tree or not tree.winfo_exists():
            return None

        bbox = tree.bbox(item_id, "#2")
        if not bbox:
            return None

        cell_x = event_x - bbox[0]
        if cell_x < 0:
            return None

        data_text = tree.set(item_id, "data")
        if not data_text:
            return None

        tokens = [token for token in data_text.split("  ") if token.strip()]
        assets = ("arena", "rois", "trajectory", "summary")
        font = self._get_overview_badge_font()
        cursor = 0

        for token, asset in zip(tokens, assets):
            segment = token.strip()
            if not segment:
                continue
            display = f"{segment}  "
            segment_width = font.measure(display)
            if cursor <= cell_x <= cursor + segment_width:
                return asset
            cursor += segment_width

        return None

    def _show_overview_context_menu(
        self,
        event,
        video_path: str,
        asset: str,
    ) -> None:
        tree = self.project_overview_tree
        if not tree or not tree.winfo_exists():
            return

        if self._overview_context_menu is None:
            self._overview_context_menu = Menu(tree, tearoff=0)

        labels = {
            "arena": "Apagar arena",
            "rois": "Apagar ROIs",
            "trajectory": "Apagar trajetória",
            "summary": "Apagar relatórios/sumários",
            "video": "Remover vídeo do projeto",
        }

        menu = self._overview_context_menu
        menu.delete(0, "end")
        menu.add_command(
            label=labels.get(asset, f"Remover {asset}"),
            command=lambda: self._handle_overview_asset_removal(video_path, asset),
        )

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _handle_overview_asset_removal(self, video_path: str, asset: str) -> None:
        allowed, reason = self.controller.can_remove_project_asset(video_path, asset)
        if not allowed:
            self.show_warning(
                "Ação indisponível",
                reason or "Não é possível remover o item selecionado neste momento.",
            )
            return

        basename = os.path.basename(video_path) or video_path
        prompts = {
            "arena": (
                "Remover arena",
                ("Deseja remover a arena deste vídeo? As ROIs associadas também serão limpas."),
            ),
            "rois": (
                "Remover ROIs",
                "Deseja remover todas as ROIs salvas para este vídeo?",
            ),
            "trajectory": (
                "Remover trajetória",
                "Deseja remover a trajetória gerada para este vídeo?",
            ),
            "summary": (
                "Remover relatórios",
                "Deseja remover os relatórios e sumários associados a este vídeo?",
            ),
            "video": (
                "Remover vídeo do projeto",
                (
                    "Deseja remover este vídeo do projeto? As arenas, ROIs e "
                    "trajetórias já removidas não poderão ser recuperadas "
                    "automaticamente."
                ),
            ),
        }

        title, message = prompts.get(
            asset,
            (
                "Remover item",
                "Confirma a remoção do item selecionado?",
            ),
        )

        confirm = messagebox.askyesno(
            title,
            f"{message}\n\nVídeo: {basename}",
            icon="warning",
        )
        if not confirm:
            return

        delete_files = True
        if asset == "video":
            delete_files = messagebox.askyesno(
                "Excluir arquivo do disco?",
                (
                    "Deseja também remover o arquivo de vídeo do disco? Essa ação "
                    "não poderá ser desfeita."
                ),
                icon="question",
            )

        if asset == "video":
            self.publish_event(
                Events.PROJECT_DELETE_ASSET,
                {
                    "video_path": video_path,
                    "asset": asset,
                    "delete_source": delete_files,
                },
            )
            success = True  # Assume success
        else:
            self.publish_event(
                Events.PROJECT_DELETE_ASSET, {"video_path": video_path, "asset": asset}
            )
            success = True  # Assume success

        if not success:
            self.show_error(
                "Remoção não realizada",
                (
                    "Não foi possível remover o item selecionado. Consulte os "
                    "logs para mais detalhes."
                ),
            )
            return

        status_labels = {
            "arena": "Arena removida",
            "rois": "ROIs removidas",
            "trajectory": "Trajetória removida",
            "summary": "Relatórios removidos",
            "video": "Vídeo removido do projeto",
        }

        status_message = f"{status_labels.get(asset, 'Item removido')} • {basename}"
        self.set_status(status_message)
        self.refresh_project_views(
            reason=status_message,
            append_summary=True,
            immediate=True,
        )

    def _build_arduino_dashboard(self, parent: Frame):
        """Creates the Arduino monitoring dashboard."""
        if self.arduino_dashboard_frame and self.arduino_dashboard_frame.winfo_exists():
            try:
                self.arduino_dashboard_frame.destroy()
            except Exception:
                pass

        self.arduino_dashboard_frame = ttk.LabelFrame(parent, text="Dashboard Arduino", padding=10)
        self.arduino_dashboard_frame.pack(fill="both", expand=False, pady=(0, 10))

        status_row = ttk.Frame(self.arduino_dashboard_frame)
        status_row.pack(fill="x", pady=2)

        self.arduino_status_indicator = Label(
            status_row,
            text="●",
            font=("Segoe UI", 12, "bold"),
        )
        self.arduino_status_indicator.pack(side="left")

        ttk.Label(
            status_row,
            textvariable=self.arduino_status_var,
        ).pack(side="left", padx=(6, 12))

        ttk.Label(status_row, text="Último comando:").pack(side="left")
        ttk.Label(
            status_row,
            textvariable=self.arduino_last_command_var,
        ).pack(side="left", padx=(6, 0))

        ttk.Separator(self.arduino_dashboard_frame, orient="horizontal").pack(fill="x", pady=(8, 6))

        ttk.Label(
            self.arduino_dashboard_frame,
            text="Eventos recentes:",
        ).pack(anchor="w")

        log_frame = ttk.Frame(self.arduino_dashboard_frame)
        log_frame.pack(fill="both", expand=True, pady=(4, 0))

        self.arduino_log_text = Text(
            log_frame,
            height=6,
            wrap="word",
            state="disabled",
            background="#1f2933",
            foreground="#f0f4f8",
        )
        self.arduino_log_text.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.arduino_log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.arduino_log_text.configure(yscrollcommand=scrollbar.set)

        controls_row = ttk.Frame(self.arduino_dashboard_frame)
        controls_row.pack(fill="x", pady=(6, 0))
        ttk.Button(controls_row, text="Limpar Log", command=self._clear_arduino_log).pack(
            side="right"
        )

        # Reset dashboard state
        self._clear_arduino_log()
        self.update_arduino_status_indicator(False, None)
        self.set_arduino_last_command("-")

    def _clear_arduino_log(self):
        if not self.arduino_log_text:
            return
        self.arduino_log_text.configure(state="normal")
        self.arduino_log_text.delete("1.0", "end")
        self.arduino_log_text.configure(state="disabled")

    def append_arduino_log(self, message: str):
        if not self.arduino_log_text:
            return

        timestamp = time.strftime("%H:%M:%S")
        entry = f"[{timestamp}] {message}\n"

        self.arduino_log_text.configure(state="normal")
        self.arduino_log_text.insert("end", entry)

        try:
            current_line = int(float(self.arduino_log_text.index("end-1c").split(".")[0]))
            max_lines = 300
            if current_line > max_lines:
                start_line = current_line - max_lines
                self.arduino_log_text.delete("1.0", f"{start_line}.0")
        except Exception:
            # If parsing fails, ignore trimming and keep log growing temporarily
            pass

        self.arduino_log_text.see("end")
        self.arduino_log_text.configure(state="disabled")

    def update_arduino_status_indicator(self, connected: bool, port: str | None):
        status_text = "Desconectado"
        if connected and port:
            status_text = f"Conectado ({port})"
        elif connected:
            status_text = "Conectado"

        try:
            self.arduino_status_var.set(status_text)
        except Exception:
            pass

        if self.arduino_status_indicator:
            color = "#16a34a" if connected else "#b91c1c"
            try:
                self.arduino_status_indicator.config(foreground=color)
            except Exception:
                pass

    def set_arduino_last_command(self, label_text: str):
        try:
            self.arduino_last_command_var.set(label_text or "-")
        except Exception:
            pass

    def show_external_trigger_notice(self, session_label: str, **details):
        if not self.external_trigger_notice_label:
            return

        day = details.get("day")
        group = details.get("group")
        cobaia = details.get("cobaia")
        port = details.get("port")

        descriptors = []
        if day is not None and group is not None and cobaia is not None:
            day_display = self._format_day_display(day) or day
            descriptors.append(f"Dia {day_display}, Grupo {group}, Sujeito {cobaia}")
        if port:
            descriptors.append(f"Porta {port}")

        message = f"Aguardando sinal externo para iniciar {session_label}."
        if descriptors:
            message += f" ({' • '.join(descriptors)})"

        self.external_trigger_notice_var.set(message)

        highlight_bg = "#FFF7ED"
        highlight_fg = "#92400e"
        try:
            self.external_trigger_notice_label.config(
                background=highlight_bg,
                foreground=highlight_fg,
            )
        except Exception:
            pass

    def clear_external_trigger_notice(self):
        if not self.external_trigger_notice_label:
            return

        self.external_trigger_notice_var.set("")

        try:
            bg = (
                self._external_notice_default_bg
                if self._external_notice_default_bg is not None
                else self.external_trigger_notice_label.cget("background")
            )
            fg = (
                self._external_notice_default_fg
                if self._external_notice_default_fg is not None
                else self.external_trigger_notice_label.cget("foreground")
            )
            self.external_trigger_notice_label.config(background=bg, foreground=fg)
        except Exception:
            pass

    def _create_roi_analysis_tab(self):
        """Creates the tab for ROI and detection zone configuration."""
        # This tab is now for defining detection zones (main polygon, ROI polygons)
        # and will replace the old ROI analysis functionality.
        self.roi_data = {}  # This will be repurposed for the new zone data
        self.drawing_mode = None
        self.current_polygon_points = []

        # Coordinate system for polygon alignment
        self._poly_pts_canvas = []  # Canvas coordinates for UI display
        self._poly_pts_video = []  # Video coordinates for saving
        self._bg_scale = 1.0  # Scaling factor from video to canvas
        self._bg_offset = (0, 0)  # Offset of image in canvas
        self._bg_img_size = (0, 0)  # Original image dimensions

        self.current_circle_center = None
        self._canvas_bg_image = None  # Keep a reference to the image

        # 1. Create the main frame for the tab and rename it
        self.zone_tab_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.zone_tab_frame, text="Configuração de Zonas")

        # 2. Create the PanedWindow for side-by-side panels
        main_pane = ttk.PanedWindow(self.zone_tab_frame, orient="horizontal")
        main_pane.pack(expand=True, fill="both")

        # 3. Create the control panel on the left with scrollable frame
        left_panel_frame = ttk.Frame(main_pane, padding=5, relief="groove", borderwidth=2)
        # Add left panel without invalid minsize parameter
        main_pane.add(left_panel_frame, weight=1)

        # Set initial sash position to 420 pixels for left panel width
        # Increased to ensure template "Aplicar" button is fully visible
        def _set_initial_sash():
            try:
                main_pane.sashpos(0, 420)
            except Exception:
                pass  # Sash position might fail if pane isn't fully realized yet

        main_pane.after(10, _set_initial_sash)

        # ✨ NEW: Create ZoneControlsWidget instead of inline controls
        self.zone_controls = ZoneControlsWidget(left_panel_frame, event_bus=self.event_bus)
        self.zone_controls.pack(fill="both", expand=True)

        # Keep reference to internal widgets for backward compatibility
        # TODO: Migrate code to use ZoneControlsWidget API instead
        self.zone_controls_frame = self.zone_controls.zone_controls_frame

        # 4. Create the visualization panel on the right
        self.viz_frame = ttk.Frame(main_pane, padding=5, relief="sunken", borderwidth=2)
        main_pane.add(self.viz_frame, weight=4)

        # Bind pane configure event to maintain minimum left panel width
        def _on_pane_configure(event=None):
            try:
                # Clamp left panel to minimum 380px width to show all buttons
                current_pos = main_pane.sashpos(0)
                if current_pos < 380:
                    main_pane.sashpos(0, 380)
            except Exception:
                pass  # Ignore errors during resize

        main_pane.bind("<Configure>", _on_pane_configure)

        # 5. ✨ NEW: Create VideoDisplayWidget instead of manual Canvas
        self.video_display = VideoDisplayWidget(
            self.viz_frame, event_bus=self.event_bus, width=800, height=600, bg="gray"
        )
        self.video_display.pack(expand=True, fill="both")

        # Keep reference to canvas for backward compatibility with drawing code
        # TODO: Migrate drawing logic to use VideoDisplayWidget API
        self._roi_canvas_widget = self.video_display.canvas

        # Bind canvas resize event for proper image scaling (keep existing behavior)
        self._roi_canvas_widget.bind("<Configure>", self._on_canvas_configure)

        # 6. ✨ REMOVED: _create_zone_control_widgets() is no longer needed
        # ZoneControlsWidget already creates all the necessary control widgets
        # The old method is kept below for reference but is no longer called

        # 7. ✨ NEW: Subscribe to events emitted by the components
        self._subscribe_zone_component_events()

    def _subscribe_zone_component_events(self):
        """
        Subscribe to events emitted by ZoneControlsWidget.

        This method connects component events to existing ApplicationGUI handlers,
        maintaining backward compatibility while using the new component architecture.
        """
        if not self.event_bus:
            return

        # Drawing action events
        self.event_bus.subscribe(
            "zone.auto_detect_clicked", lambda data: self._on_auto_detect_clicked()
        )

        self.event_bus.subscribe(
            "zone.draw_main_polygon", lambda data: self._start_main_arena_drawing()
        )

        self.event_bus.subscribe("zone.draw_roi", lambda data: self._start_roi_drawing())

        self.event_bus.subscribe("zone.toggle_view", lambda data: self._toggle_canvas_view())

        # Template events
        self.event_bus.subscribe("zone.template_apply", lambda data: self._on_apply_roi_template())

        self.event_bus.subscribe("zone.template_save", lambda data: self._on_save_roi_template())

        self.event_bus.subscribe(
            "zone.template_import",
            lambda data: self._on_import_and_apply_roi_template(),
        )

        # Video selector events
        self.event_bus.subscribe(
            "zone.video_double_click",
            lambda data: self._on_video_tree_double_click(None),
        )

        self.event_bus.subscribe(
            "zone.video_frame_load", lambda data: self._load_selected_video_frame()
        )

        self.event_bus.subscribe(
            "zone.video_refresh", lambda data: self._populate_video_selector_tree()
        )

        self.event_bus.subscribe(
            "zone.video_search_changed",
            lambda data: self._filter_video_tree(data.get("search_term", "")),
        )

        # Zone list events
        self.event_bus.subscribe(
            "zone.list_item_right_click",
            lambda data: self._on_zone_right_click(self._create_mock_event(data)),
        )

        self.event_bus.subscribe(
            "zone.list_item_double_click", lambda data: self._on_zone_double_click(None)
        )

        # Arena editing events
        self.event_bus.subscribe("zone.arena_save", lambda data: self._on_save_arena())

        self.event_bus.subscribe("zone.arena_discard", lambda data: self._on_discard_arena())

        # ROI configuration events
        self.event_bus.subscribe(
            "zone.roi_rule_changed", lambda data: self._on_roi_rule_change(None)
        )

        self.event_bus.subscribe(
            "zone.roi_settings_apply", lambda data: self._on_apply_roi_settings()
        )

    def _create_mock_event(self, data: dict):
        """Create a mock event object for backward compatibility with old event handlers."""

        class MockEvent:
            def __init__(self, data):
                self.x_root = data.get("x", 0)
                self.y_root = data.get("y", 0)
                self.x = data.get("x", 0)
                self.y = data.get("y", 0)

        return MockEvent(data)

    def _on_canvas_configure(self, event=None):
        """Handle canvas resize events to properly scale and center the image."""
        # Skip if this is not the main roi_canvas being resized
        if event and event.widget != self.roi_canvas:
            return

        if not hasattr(self, "_raw_bg_image") or not self._raw_bg_image:
            if hasattr(self, "_original_image") and self._original_image:
                self._raw_bg_image = self._original_image
            else:
                return

        # Get the current canvas dimensions
        canvas_width = self.roi_canvas.winfo_width()
        canvas_height = self.roi_canvas.winfo_height()

        if canvas_width <= 1 or canvas_height <= 1:
            return

        # Re-scale and center the background image using the new method
        try:
            self._draw_bg_image_to_canvas()
            # After updating the background, redraw any zones that exist
            if hasattr(self, "controller") and self.controller:
                self.redraw_zones_from_project_data()
        except Exception as e:
            log.warning("gui.canvas.configure_error", error=str(e))

    def _create_zone_control_widgets(self):
        """Create all the zone control widgets in the scrollable frame."""
        self._create_zone_summary_cards_section()

        # --- Drawing Actions ---
        actions_frame = ttk.LabelFrame(
            self.zone_controls_frame, text="Ações de Desenho", padding=10
        )
        actions_frame.pack(fill="x", pady=5)

        # --- Single Analysis Options ---
        self.single_analysis_options_frame = ttk.LabelFrame(
            self.zone_controls_frame,
            text="Opções de Análise de Vídeo Único",
            padding=10,
        )
        # This frame is packed on demand by setup_zone_configuration_for_video

        # ROI options
        self.roi_choice_var = StringVar(value="none")
        ttk.Label(self.single_analysis_options_frame, text="Opções de ROI:").pack(anchor="w")
        ttk.Radiobutton(
            self.single_analysis_options_frame,
            text="Não usar ROIs",
            variable=self.roi_choice_var,
            value="none",
        ).pack(anchor="w", padx=10)
        ttk.Radiobutton(
            self.single_analysis_options_frame,
            text="Desenhar ROIs manualmente",
            variable=self.roi_choice_var,
            value="manual",
        ).pack(anchor="w", padx=10)
        ttk.Radiobutton(
            self.single_analysis_options_frame,
            text="Usar ROIs de template",
            variable=self.roi_choice_var,
            value="template",
        ).pack(anchor="w", padx=10)

        # Frame intervals for analysis and display
        ttk.Label(self.single_analysis_options_frame, text="Intervalo de Análise (frames):").pack(
            anchor="w", pady=(10, 0)
        )
        ttk.Entry(
            self.single_analysis_options_frame,
            textvariable=self.analysis_interval_var,
            width=10,
        ).pack(anchor="w", padx=10)

        ttk.Label(self.single_analysis_options_frame, text="Intervalo de Exibição (frames):").pack(
            anchor="w", pady=(5, 0)
        )
        ttk.Entry(
            self.single_analysis_options_frame,
            textvariable=self.display_interval_var,
            width=10,
        ).pack(anchor="w", padx=10)

        # Button for automatic detection
        ttk.Button(
            actions_frame,
            text="Detectar Aquário (Auto)",
            command=self._on_auto_detect_clicked,
        ).pack(fill="x", pady=2)

        # New Entry for stabilization frames
        stabilization_frame = ttk.Frame(actions_frame)
        ttk.Label(stabilization_frame, text="Frames para Análise:").pack(side="left", padx=(0, 5))
        ttk.Entry(stabilization_frame, textvariable=self.stabilization_frames_var, width=5).pack(
            side="left"
        )
        stabilization_frame.pack(fill="x", pady=2, anchor="w")

        # Manual drawing buttons
        ttk.Button(
            actions_frame,
            text="Desenhar Polígono Principal",
            command=self._start_main_arena_drawing,
        ).pack(fill="x", pady=2)

        # ROI button - initially disabled until main arena is drawn
        self.draw_roi_button = ttk.Button(
            actions_frame,
            text="Desenhar Área de Interesse",
            command=self._start_roi_drawing,
            state="disabled",
        )
        self.draw_roi_button.pack(fill="x", pady=2)

        # View toggle button (initially hidden)
        self.toggle_view_btn = ttk.Button(
            actions_frame,
            text="Ver Análise em Progresso",
            command=self._toggle_canvas_view,
            state="disabled",
        )
        self.toggle_view_btn.pack(fill="x", pady=2)

        template_frame = ttk.LabelFrame(
            self.zone_controls_frame,
            text="Templates de ROI",
            padding=10,
        )
        template_frame.pack(fill="x", pady=5)

        template_selector = ttk.Frame(template_frame)
        template_selector.pack(fill="x", pady=(0, 6))

        ttk.Label(template_selector, text="Templates salvos:").pack(side="left", padx=(0, 5))
        self.roi_template_combobox = ttk.Combobox(
            template_selector,
            state="readonly",
            textvariable=self.roi_template_var,
            values=[],
            width=25,
        )
        self.roi_template_combobox.pack(side="left", fill="x", expand=True)

        ttk.Button(
            template_selector,
            text="Aplicar",
            command=self._on_apply_roi_template,
        ).pack(side="left", padx=4)

        template_actions = ttk.Frame(template_frame)
        template_actions.pack(fill="x")

        ttk.Button(
            template_actions,
            text="💾 Salvar Zonas Atuais",
            command=self._on_save_roi_template,
        ).pack(side="left", padx=(0, 4))
        ttk.Button(
            template_actions,
            text="📂 Importar e Aplicar Arquivo...",
            command=self._on_import_and_apply_roi_template,
        ).pack(side="left")

        ttk.Label(
            template_frame,
            text=(
                "Templates armazenam o polígono principal e todas as ROIs "
                "para reutilizar em outros vídeos do projeto."
            ),
            wraplength=280,
            style="Small.TLabel",
        ).pack(anchor="w", pady=(6, 0))

        self._refresh_roi_templates()

        # --- Video Selector ---
        video_selector_frame = ttk.LabelFrame(
            self.zone_controls_frame,
            text="📹 Selecionar Vídeo para Desenho",
            padding=10,
        )
        video_selector_frame.pack(fill="both", pady=5)

        search_frame = ttk.Frame(video_selector_frame)
        search_frame.pack(fill="x", pady=(0, 5))

        ttk.Label(search_frame, text="🔍 Buscar:").pack(side="left", padx=(0, 5))
        self.video_search_var = StringVar()
        self.video_search_var.trace_add("write", lambda *_: self._filter_video_tree())
        ttk.Entry(
            search_frame,
            textvariable=self.video_search_var,
            width=25,
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Button(
            search_frame,
            text="🔄",
            width=3,
            command=lambda: self._populate_video_selector_tree(),
        ).pack(side="left")

        tree_container = ttk.Frame(video_selector_frame)
        tree_container.pack(fill="both", expand=True)

        self.video_selector_tree = ttk.Treeview(
            tree_container,
            columns=("status", "filename"),
            show="tree headings",
            height=10,
            selectmode="browse",
        )
        self.video_selector_tree.heading("#0", text="Hierarquia")
        self.video_selector_tree.heading("status", text="Dados")
        self.video_selector_tree.heading("filename", text="Arquivo")

        self.video_selector_tree.column("#0", width=220, stretch=True)
        self.video_selector_tree.column(
            "status",
            width=120,
            anchor="center",
            stretch=False,
        )
        self.video_selector_tree.column("filename", width=180, stretch=True)

        scrollbar = ttk.Scrollbar(
            tree_container,
            orient="vertical",
            command=self.video_selector_tree.yview,
        )
        self.video_selector_tree.configure(yscrollcommand=scrollbar.set)
        self.video_selector_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.video_selector_tree.bind(
            "<Double-Button-1>",
            self._on_video_tree_double_click,
        )

        ttk.Button(
            video_selector_frame,
            text="📹 Carregar Frame do Vídeo Selecionado",
            command=self._load_selected_video_frame,
        ).pack(pady=(5, 0))

        legend_frame = ttk.Frame(video_selector_frame)
        legend_frame.pack(fill="x", pady=(5, 0))
        ttk.Label(
            legend_frame,
            text=self._build_status_icon_legend(),
            font=("TkDefaultFont", 8),
            foreground="gray",
        ).pack(anchor="w")

        self._populate_video_selector_tree()

        # --- Zone List ---
        zone_list_frame = ttk.LabelFrame(
            self.zone_controls_frame, text="Zonas Definidas", padding=10
        )
        zone_list_frame.pack(fill="x", pady=5)

        from zebtrack.ui.window_utils import create_scrollbar

        self.zone_listbox = ttk.Treeview(
            zone_list_frame,
            columns=("name", "type", "color"),
            show="headings",
            height=6,
        )
        self.zone_listbox.heading("name", text="Nome")
        self.zone_listbox.heading("type", text="Tipo")
        self.zone_listbox.heading("color", text="Cor")

        # Configure column widths
        self.zone_listbox.column("name", width=240, minwidth=160, stretch=True)
        self.zone_listbox.column("type", width=90, minwidth=80, stretch=False)
        self.zone_listbox.column("color", width=70, minwidth=60, stretch=False)

        self.zone_listbox.pack(side="left", fill="both", expand=True)

        # Scrollbar
        scrollbar = create_scrollbar(
            zone_list_frame, orient="vertical", command=self.zone_listbox.yview
        )
        self.zone_listbox.configure(yscrollcommand=scrollbar.set)

        # Bind events
        self.zone_listbox.bind("<Button-3>", self._on_zone_right_click)
        self.zone_listbox.bind("<Double-Button-1>", self._on_zone_double_click)

        # Menu de contexto para ROIs
        self.roi_context_menu = None
        self._create_roi_context_menu()

        scrollbar.pack(side="right", fill="y")

        # --- Interactive Buttons (initially hidden) ---
        # Positioned right after zone list, before ROI Inclusion Rule Panel
        self.interactive_buttons_frame = ttk.Frame(self.zone_controls_frame)
        self.save_arena_btn = ttk.Button(
            self.interactive_buttons_frame,
            text="✅ Salvar Edição",
            command=self._on_save_arena,
        )
        self.save_arena_btn.pack(side="left", fill="x", expand=True, padx=2)
        self.discard_arena_btn = ttk.Button(
            self.interactive_buttons_frame,
            text="❌ Descartar",
            command=self._on_discard_arena,
        )
        self.discard_arena_btn.pack(side="left", fill="x", expand=True, padx=2)
        # This frame is packed later when needed (via pack() in _enter_edit_mode)

        # --- ROI Inclusion Rule Panel ---
        self.roi_inclusion_frame = ttk.LabelFrame(
            self.zone_controls_frame, text="Regra de Inclusão em ROI", padding=10
        )
        self.roi_inclusion_frame.pack(fill="x", pady=5)

        # Rule selection combobox
        rule_frame = ttk.Frame(self.roi_inclusion_frame)
        rule_frame.pack(fill="x", pady=2)
        ttk.Label(rule_frame, text="Regra:").pack(side="left", padx=(0, 5))
        self.roi_rule_combo = ttk.Combobox(
            rule_frame,
            textvariable=self.roi_inclusion_rule_var,
            values=[
                "centroid_in",
                "centroid_in_on_buffered_roi",
                "bbox_intersects",
                "seg_overlap",
            ],
            state="readonly",
            width=30,
        )
        self.roi_rule_combo.pack(side="left", fill="x", expand=True)
        self.roi_rule_combo.bind("<<ComboboxSelected>>", self._on_roi_rule_change)

        # Parameter fields (shown/hidden based on rule)
        self.radius_frame = ttk.Frame(self.roi_inclusion_frame)
        ttk.Label(self.radius_frame, text="Raio de buffer (r):").pack(side="left", padx=(0, 5))
        self.radius_entry = ttk.Entry(
            self.radius_frame, textvariable=self.roi_buffer_radius_var, width=10
        )
        self.radius_entry.pack(side="left", padx=(0, 10))
        ttk.Label(
            self.radius_frame,
            text="Usado para dilatar a ROI. Interpretado em cm quando houver "
            "calibração (px/cm); caso contrário, em pixels.",
            font=("TkDefaultFont", 8),
        ).pack(side="left")

        self.overlap_frame = ttk.Frame(self.roi_inclusion_frame)
        ttk.Label(self.overlap_frame, text="Mín. fração de sobreposição (0–1):").pack(
            side="left", padx=(0, 5)
        )
        self.overlap_entry = ttk.Entry(
            self.overlap_frame, textvariable=self.roi_overlap_ratio_var, width=10
        )
        self.overlap_entry.pack(side="left", padx=(0, 10))
        self.overlap_help_label = ttk.Label(
            self.overlap_frame,
            text="A detecção é considerada dentro da ROI quando a fração de "
            "área do bbox contida na ROI atinge este valor.",
            font=("TkDefaultFont", 8),
        )
        self.overlap_help_label.pack(side="left")

        # Help text that changes based on rule
        self.rule_help_label = ttk.Label(
            self.roi_inclusion_frame,
            text="",
            font=("TkDefaultFont", 8),
            wraplength=400,
            justify="left",
        )
        self.rule_help_label.pack(fill="x", pady=(5, 0))

        # Save settings button
        save_settings_frame = ttk.Frame(self.roi_inclusion_frame)
        save_settings_frame.pack(fill="x", pady=(5, 0))
        ttk.Button(
            save_settings_frame,
            text="Aplicar Configurações",
            command=self._on_apply_roi_settings,
        ).pack(side="right")

        # Initialize display based on current rule
        self._on_roi_rule_change()

    def _create_zone_summary_cards_section(self) -> None:
        """Renderiza os cartões com indicadores numéricos da etapa de zonas."""
        if not getattr(self, "zone_controls_frame", None):
            return

        if self.zone_summary_frame and self.zone_summary_frame.winfo_exists():
            try:
                self.zone_summary_frame.destroy()
            except Exception:
                pass

        self.zone_summary_cards = {}
        self.zone_summary_frame = ttk.LabelFrame(
            self.zone_controls_frame,
            text=f"{STATUS_SYMBOLS['summary']} Indicadores de Preparação",
            padding=10,
        )
        self.zone_summary_frame.pack(fill="x", pady=(0, 5))

        cards_container = ttk.Frame(self.zone_summary_frame)
        cards_container.pack(fill="x")

        card_specs = [
            (
                "arena_missing",
                f"{STATUS_SYMBOLS['arena']} Arenas pendentes",
            ),
            (
                "rois_missing",
                f"{STATUS_SYMBOLS['rois']} ROIs pendentes",
            ),
            (
                "ready_for_processing",
                f"{STATUS_SYMBOLS['summary']} Prontos para trajetórias",
            ),
        ]

        for idx, (key, title) in enumerate(card_specs):
            card = ttk.Frame(cards_container, padding=10, relief="ridge", borderwidth=1)
            card.grid(row=0, column=idx, padx=5, pady=5, sticky="nsew")
            cards_container.columnconfigure(idx, weight=1)

            value_var = StringVar(value="0")
            detail_var = StringVar(value="Nenhum vídeo listado")

            ttk.Label(card, text=title, font=("Segoe UI", 9, "bold")).pack(anchor="w")
            ttk.Label(
                card,
                textvariable=value_var,
                font=("Segoe UI", 22, "bold"),
            ).pack(anchor="center", pady=(4, 0))
            ttk.Label(
                card,
                textvariable=detail_var,
                font=("Segoe UI", 8),
                foreground="#555555",
            ).pack(anchor="w", pady=(4, 0))

            self.zone_summary_cards[key] = {
                "value": value_var,
                "detail": detail_var,
            }

        ttk.Label(
            self.zone_summary_frame,
            text=self._get_zone_summary_helper_text(),
            font=("TkDefaultFont", 8),
            foreground="#555555",
            wraplength=520,
            justify="left",
        ).pack(anchor="w", pady=(6, 0))

        self._update_zone_summary_cards()

    def _create_pipeline_processing_tab(self) -> None:
        """Cria a aba dedicada ao pipeline de trajetórias e sumários."""
        if not self.notebook:
            return

        if self.pipeline_tab_frame and self.pipeline_tab_frame.winfo_exists():
            try:
                self.pipeline_tab_frame.destroy()
            except Exception:
                pass

        self.pipeline_tab_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.pipeline_tab_frame, text="Trajetórias e Sumários")

        header = ttk.Label(
            self.pipeline_tab_frame,
            text=(
                "Separe o desenho das zonas do processamento em lote. "
                "Selecione os vídeos com arena válida para gerar "
                "trajetórias completas ou apenas sumários parquet."
            ),
            wraplength=620,
            justify="left",
        )
        header.pack(fill="x", pady=(0, 10))

        listing_frame = ttk.LabelFrame(
            self.pipeline_tab_frame,
            text="Vídeos com arena válida",
            padding=10,
        )
        listing_frame.pack(fill="both", expand=True)

        columns = ("rois", "trajectory", "summary", "status")
        tree_container = ttk.Frame(listing_frame)
        tree_container.pack(fill="both", expand=True)

        self.pipeline_video_tree = ttk.Treeview(
            tree_container,
            columns=columns,
            show="tree headings",
            height=12,
            selectmode="extended",
        )
        self.pipeline_video_tree.heading("#0", text="Estrutura do Projeto")
        self.pipeline_video_tree.heading("rois", text="📍 ROIs")
        self.pipeline_video_tree.heading("trajectory", text="📈 Trajetória")
        self.pipeline_video_tree.heading("summary", text="Σ Sumário")
        self.pipeline_video_tree.heading("status", text="Status")

        self.pipeline_video_tree.column("#0", width=320, stretch=True)
        self.pipeline_video_tree.column("rois", width=100, anchor="center")
        self.pipeline_video_tree.column("trajectory", width=120, anchor="center")
        self.pipeline_video_tree.column("summary", width=130, anchor="center")
        self.pipeline_video_tree.column("status", width=240, anchor="w")

        tree_scroll = ttk.Scrollbar(
            tree_container, orient="vertical", command=self.pipeline_video_tree.yview
        )
        self.pipeline_video_tree.configure(yscrollcommand=tree_scroll.set)
        self.pipeline_video_tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

        self.pipeline_legend_label = ttk.Label(
            listing_frame,
            text=self._build_status_icon_legend(include_summary=True),
            font=("TkDefaultFont", 8),
            foreground="#555555",
            justify="left",
            wraplength=520,
        )
        self.pipeline_legend_label.pack(fill="x", anchor="w", pady=(6, 0))

        self.pipeline_video_tree.bind("<<TreeviewSelect>>", self._on_pipeline_selection_changed)

        footer = ttk.Frame(self.pipeline_tab_frame, padding=(0, 10))
        footer.pack(fill="x")

        self.pipeline_selection_label = ttk.Label(
            footer,
            text="Nenhum vídeo elegível listado.",
            justify="left",
        )
        self.pipeline_selection_label.pack(side="left")

        actions_frame = ttk.Frame(footer)
        actions_frame.pack(side="right")

        traj_btn = ttk.Button(
            actions_frame,
            text="▶️ Gerar Trajetórias",
            command=self._trigger_batch_trajectory_processing,
            state="disabled",
        )
        traj_btn.pack(side="left", padx=(0, 6))

        summary_btn = ttk.Button(
            actions_frame,
            text="Σ Exportar Sumários (Parquet)",
            command=self._trigger_parquet_summaries,
            state="disabled",
        )
        summary_btn.pack(side="left")

        self.pipeline_action_buttons = {
            "trajectories": traj_btn,
            "summaries": summary_btn,
        }

        self._refresh_pipeline_video_table()

    def _update_zone_summary_cards(self, all_videos=None) -> None:
        """Atualiza os cartões de resumo com base na lista de vídeos."""
        if not self.zone_summary_cards:
            return

        if all_videos is None:
            controller = getattr(self, "controller", None)
            if controller and controller.project_manager:
                all_videos = controller.project_manager.get_all_videos() or []
            else:
                all_videos = []

        all_videos = list(all_videos or [])
        total_videos = len(all_videos)

        if total_videos == 0:
            for card in self.zone_summary_cards.values():
                card["value"].set("0")
                card["detail"].set("Nenhum vídeo listado")
            log.info(
                "gui.zone_summary.cards_refresh",
                total=0,
                arenas_missing=0,
                rois_missing=0,
                ready_pending=0,
                ready_completed=0,
            )
            return

        arenas_missing = sum(1 for video in all_videos if not video.get("has_arena"))
        rois_missing = sum(1 for video in all_videos if not video.get("has_rois"))

        ready_total = sum(
            1 for video in all_videos if video.get("has_arena") and video.get("has_rois")
        )
        ready_completed = sum(
            1
            for video in all_videos
            if video.get("has_arena") and video.get("has_rois") and video.get("has_trajectory")
        )
        ready_pending = max(ready_total - ready_completed, 0)

        self.zone_summary_cards["arena_missing"]["value"].set(str(arenas_missing))
        self.zone_summary_cards["arena_missing"]["detail"].set(
            f"{total_videos - arenas_missing} com arena salva"
        )

        self.zone_summary_cards["rois_missing"]["value"].set(str(rois_missing))
        self.zone_summary_cards["rois_missing"]["detail"].set(
            f"{total_videos - rois_missing} com ROIs salvas"
        )

        self.zone_summary_cards["ready_for_processing"]["value"].set(str(ready_pending))
        self.zone_summary_cards["ready_for_processing"]["detail"].set(
            f"{ready_completed} já com trajetórias"
            if ready_total
            else "Sem arenas/ROIs disponíveis"
        )

        log.info(
            "gui.zone_summary.cards_refresh",
            total=total_videos,
            arenas_missing=arenas_missing,
            rois_missing=rois_missing,
            ready_pending=ready_pending,
            ready_completed=ready_completed,
        )

    def _refresh_pipeline_video_table(self, all_videos=None) -> None:
        if not self.pipeline_video_tree or not self.pipeline_tab_frame:
            return

        controller = getattr(self, "controller", None)
        pm = getattr(controller, "project_manager", None)

        if all_videos is None and pm is not None:
            all_videos = pm.get_all_videos() or []

        for item in self.pipeline_video_tree.get_children():
            self.pipeline_video_tree.delete(item)

        prepared_videos: list[dict] = []
        self.pipeline_video_vars = {}
        summary_total = 0

        for video in all_videos or []:
            path = video.get("path")
            if not path or not video.get("has_arena"):
                continue

            summary_exists = self._pipeline_summary_exists(video)

            prepared = dict(video)
            prepared["path"] = path
            prepared["metadata"] = video.get("metadata") or {}
            prepared["has_arena"] = bool(video.get("has_arena"))
            prepared["has_rois"] = bool(video.get("has_rois"))
            prepared["has_trajectory"] = bool(video.get("has_trajectory"))
            prepared["has_complete_data"] = bool(video.get("has_complete_data")) or (
                prepared["has_arena"] and prepared["has_rois"] and prepared["has_trajectory"]
            )
            prepared["has_summary"] = bool(summary_exists)
            prepared["filename"] = os.path.basename(path)

            prepared_videos.append(prepared)

            self.pipeline_video_vars[path] = {
                "info": video,
                "summary": summary_exists,
            }
            if summary_exists:
                summary_total += 1

        hierarchy = self._build_video_hierarchy_data(prepared_videos, "")

        def _count(entries: list[dict], key: str) -> int:
            return sum(1 for entry in entries if entry.get(key))

        def _summary_count(entries: list[dict]) -> int:
            return sum(
                1 for entry in entries if entry.get("has_summary") or entry.get("has_complete_data")
            )

        for group_id, group_data in sorted(
            hierarchy.items(), key=lambda item: str(item[1]["display"]).lower()
        ):
            days_dict = group_data.get("days") or {}
            group_entries = [entry for videos in days_dict.values() for entry in videos or []]
            if not group_entries:
                continue

            total_group = len(group_entries)
            group_node = self.pipeline_video_tree.insert(
                "",
                "end",
                text=f"🏷️ {group_data['display']}",
                values=(
                    self._format_status_ratio(
                        "rois", _count(group_entries, "has_rois"), total_group
                    ),
                    self._format_status_ratio(
                        "trajectory",
                        _count(group_entries, "has_trajectory"),
                        total_group,
                    ),
                    self._format_status_ratio(
                        "summary", _summary_count(group_entries), total_group
                    ),
                    f"{total_group} vídeos",
                ),
                open=True,
            )

            for day_id, entries in sorted(
                days_dict.items(), key=lambda item: self._video_sort_key(item[0])
            ):
                entries = entries or []
                if not entries:
                    continue

                total_day = len(entries)
                sample_metadata = entries[0].get("metadata") if entries else None
                day_title = self._build_day_title(day_id, sample_metadata)
                day_node = self.pipeline_video_tree.insert(
                    group_node,
                    "end",
                    text=f"📅 {day_title}",
                    values=(
                        self._format_status_ratio("rois", _count(entries, "has_rois"), total_day),
                        self._format_status_ratio(
                            "trajectory", _count(entries, "has_trajectory"), total_day
                        ),
                        self._format_status_ratio("summary", _summary_count(entries), total_day),
                        f"{total_day} vídeos",
                    ),
                    open=False,
                )

                for entry in sorted(
                    entries,
                    key=lambda item: self._video_sort_key(item.get("subject")),
                ):
                    path = entry.get("path")
                    if not path:
                        continue

                    rois_label = "✓" if entry.get("has_rois") else "✗"
                    traj_label = "✓" if entry.get("has_trajectory") else "✗"
                    summary_label = "✓" if entry.get("has_summary") else "✗"

                    status_key = str(entry.get("status") or "pending").strip().lower()
                    status_display = self._format_status_label(status_key)

                    subject_label = self._format_subject_label(entry.get("subject"))
                    filename = entry.get("filename")
                    node_text = f"🐟 Sujeito {subject_label}"
                    if filename:
                        node_text = f"{node_text} ({filename})"

                    self.pipeline_video_tree.insert(
                        day_node,
                        "end",
                        iid=path,
                        text=node_text,
                        values=(rois_label, traj_label, summary_label, status_display),
                        tags=(path,),
                    )

        log.info(
            "gui.pipeline_table.refreshed",
            eligible=len(prepared_videos),
            with_rois=sum(1 for entry in prepared_videos if entry.get("has_rois")),
            with_trajectory=sum(1 for entry in prepared_videos if entry.get("has_trajectory")),
            with_summary=summary_total,
        )

        listed = len(self.pipeline_video_vars)
        if listed == 0:
            selection_text = "Nenhum vídeo elegível listado."
        else:
            selection_text = f"{listed} vídeo(s) elegível(is). Selecione itens para ações."

        if self.pipeline_selection_label:
            self.pipeline_selection_label.config(text=selection_text)

        self._update_pipeline_buttons_state()

    def _pipeline_summary_exists(self, video_info: dict) -> bool:
        controller = getattr(self, "controller", None)
        pm = getattr(controller, "project_manager", None)
        path = video_info.get("path")
        if not pm or not path:
            return False

        experiment_id = Path(path).stem
        entry = pm.find_video_entry(path=path)
        metadata_hint = dict(entry.get("metadata") or {}) if entry else {}
        results_path = pm.resolve_results_directory(
            experiment_id,
            video_path=path,
            metadata=metadata_hint,
        )
        summary_path = Path(results_path) / f"{experiment_id}_summary.parquet"
        return summary_path.exists()

    def _get_selected_pipeline_video_paths(self) -> list[str]:
        if not self.pipeline_video_tree:
            return []
        selected = self.pipeline_video_tree.selection()
        return [item for item in selected if item in self.pipeline_video_vars]

    def _on_pipeline_selection_changed(self, event=None) -> None:
        del event
        selections = self._get_selected_pipeline_video_paths()
        listed = len(self.pipeline_video_vars)

        if self.pipeline_selection_label:
            if not selections:
                if listed == 0:
                    text = "Nenhum vídeo elegível listado."
                else:
                    text = f"{listed} vídeo(s) elegível(is). Selecione itens para ações."
            else:
                text = f"{listed} vídeo(s) elegível(is) • {len(selections)} selecionado(s)."
            self.pipeline_selection_label.config(text=text)

        self._update_pipeline_buttons_state(selections)

    def _update_pipeline_buttons_state(self, selections=None) -> None:
        if not self.pipeline_action_buttons:
            return
        if selections is None:
            selections = self._get_selected_pipeline_video_paths()

        has_selection = bool(selections)
        for button in self.pipeline_action_buttons.values():
            button.config(state="normal" if has_selection else "disabled")

        if has_selection:
            all_have_trajectory = all(
                bool(self.pipeline_video_vars.get(path, {}).get("info", {}).get("has_trajectory"))
                for path in selections
            )
            self.pipeline_action_buttons["summaries"].config(
                state="normal" if all_have_trajectory else "disabled"
            )

    def _trigger_batch_trajectory_processing(self) -> None:
        selections = self._get_selected_pipeline_video_paths()
        if not selections:
            if not self.pipeline_video_vars:
                self.show_info(
                    "Processamento",
                    "Nenhum vídeo elegível foi encontrado com arena válida.",
                )
                return
            selections = list(self.pipeline_video_vars.keys())

        self.publish_event(Events.PROJECT_PROCESS_VIDEOS, {"video_paths": selections})
        self._request_overview_refresh()

    def _trigger_parquet_summaries(self) -> None:
        selections = self._get_selected_pipeline_video_paths()
        if not selections:
            self.show_info(
                "Sumários",
                "Selecione ao menos um vídeo com trajetória para exportar o sumário.",
            )
            return

        self.publish_event(Events.PROJECT_GENERATE_SUMMARIES, {"video_paths": selections})
        self._refresh_pipeline_video_table()

    def _refresh_zone_indicators(self, videos=None) -> None:
        controller = getattr(self, "controller", None)
        pm = getattr(controller, "project_manager", None)
        if videos is None:
            videos = pm.get_all_videos() if pm else []
        self._update_zone_summary_cards(videos)
        self._refresh_pipeline_video_table(videos)

    def _create_analysis_tab(self):
        """Creates the dedicated tab for video playback and progress stats."""
        if not self.notebook:
            return

        if self.analysis_tab_frame and self.analysis_tab_frame.winfo_exists():
            self.analysis_tab_frame.destroy()

        self.analysis_tab_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.analysis_tab_frame, text="Análise de Vídeo")

        # Status text (packed first - at the top)
        self.analysis_status_var.set("Nenhuma análise em andamento.")
        self.analysis_status_label = ttk.Label(
            self.analysis_tab_frame,
            textvariable=self.analysis_status_var,
            padding=(0, 6),
        )
        self.analysis_status_label.pack(fill="x")

        self.analysis_task_var.set(self._default_analysis_task_text())
        self._set_analysis_metadata_defaults()

        info_frame = ttk.Frame(self.analysis_tab_frame, padding=(0, 2))
        info_frame.pack(fill="x")
        info_frame.columnconfigure(0, weight=1, uniform="analysis_info")
        info_frame.columnconfigure(1, weight=1, uniform="analysis_info")
        info_frame.columnconfigure(2, weight=1, uniform="analysis_info")
        info_frame.columnconfigure(3, weight=1, uniform="analysis_info")

        self.analysis_task_label = ttk.Label(
            info_frame,
            textvariable=self.analysis_task_var,
            padding=(0, 2),
        )
        self.analysis_task_label.grid(
            row=0,
            column=0,
            columnspan=4,
            sticky="w",
            pady=(0, 2),
        )

        self.analysis_group_label = ttk.Label(
            info_frame,
            textvariable=self.analysis_group_var,
        )
        self.analysis_group_label.grid(row=1, column=0, sticky="w", padx=(0, 12))

        self.analysis_day_label = ttk.Label(
            info_frame,
            textvariable=self.analysis_day_var,
        )
        self.analysis_day_label.grid(row=1, column=1, sticky="w", padx=(0, 12))

        self.analysis_subject_label = ttk.Label(
            info_frame,
            textvariable=self.analysis_subject_var,
        )
        self.analysis_subject_label.grid(row=1, column=2, sticky="w", padx=(0, 12))

        self.analysis_profile_label = ttk.Label(
            info_frame,
            textvariable=self.analysis_profile_var,
        )
        self.analysis_profile_label.grid(row=1, column=3, sticky="w")

        self.tracking_mode_label = ttk.Label(
            info_frame,
            textvariable=self.tracking_mode_var,
        )
        self.tracking_mode_label.grid(
            row=2,
            column=0,
            columnspan=4,
            sticky="w",
            pady=(2, 2),
        )

        controls_frame = ttk.Frame(self.analysis_tab_frame, padding=(0, 4))
        controls_frame.pack(fill="x", pady=(4, 0))

        ttk.Label(controls_frame, text="Track ID ativo:").grid(row=0, column=0, sticky="w")

        self.track_selector_widget = ttk.Combobox(
            controls_frame,
            textvariable=self.track_selector_var,
            state="readonly",
            values=list(self._available_track_options),
            width=14,
        )
        self.track_selector_widget.grid(row=0, column=1, padx=(6, 12), sticky="w")
        self.track_selector_widget.bind("<<ComboboxSelected>>", self._on_track_selection_changed)

        ttk.Label(
            controls_frame,
            textvariable=self.social_summary_var,
            wraplength=360,
            justify="left",
        ).grid(row=0, column=2, sticky="w")
        controls_frame.columnconfigure(2, weight=1)

        # Progress components (packed BEFORE video to stay visible above it)
        self.progress_frame = ttk.Frame(self.analysis_tab_frame, padding=(0, 6))
        self.progress_frame.columnconfigure(0, weight=1)
        self.progress_frame.columnconfigure(1, weight=0)

        self.progress_bar = ttk.Progressbar(
            self.progress_frame,
            orient="horizontal",
            mode="determinate",
        )
        self.progress_bar.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 3),
        )

        stats_container = ttk.Frame(self.progress_frame)
        stats_container.grid(row=1, column=0, sticky="ew")
        stats_container.columnconfigure((0, 1, 2), weight=1, uniform="analysis_stats")

        self.progress_labels = {}
        stats_items = [
            ("total", "Total de Frames:"),
            ("processed", "Processados:"),
            ("detected", "Frames Detectados:"),
            ("percent", "Concluído:"),
            ("elapsed", "Tempo Decorrido:"),
            ("eta", "Tempo Estimado:"),
        ]

        for idx, (key, label_text) in enumerate(stats_items):
            row = idx // 3
            col = idx % 3
            cell = ttk.Frame(stats_container, padding=(0, 2))
            pad_x = (0, 12) if col < 2 else (0, 0)
            cell.grid(row=row, column=col, padx=pad_x, sticky="w")
            ttk.Label(cell, text=label_text).pack(anchor="w")
            var = StringVar(value="-")
            ttk.Label(cell, textvariable=var, font=("Arial", 9, "bold")).pack(anchor="w")
            self.progress_labels[key] = var

        self.cancel_proc_btn = ttk.Button(
            self.progress_frame,
            text="Cancelar Análise",
            command=lambda: self.publish_event(Events.VIDEO_CANCEL_ANALYSIS, {}),
            state="disabled",
        )
        self.cancel_proc_btn.grid(row=1, column=1, sticky="ne", padx=(12, 0))

        # Hide progress frame until analysis starts
        self.progress_frame.pack_forget()

        # Video display area (packed LAST so it fills remaining space)
        self.video_container = ttk.Frame(self.analysis_tab_frame)
        self.video_container.pack(expand=True, fill="both")

        self.analysis_video_label = Label(self.video_container, bg="black")
        self.analysis_video_label.pack(expand=True, fill="both")
        # Maintain backward compatibility with code using video_label
        self.video_label = self.analysis_video_label

    def _create_scrollable_controls_frame(self, parent):
        """Create a scrollable frame for the zone controls."""
        # Create a canvas and scrollbar for scrolling
        self.controls_canvas = Canvas(parent, highlightthickness=0)
        self.controls_scrollbar = ttk.Scrollbar(
            parent, orient="vertical", command=self.controls_canvas.yview
        )

        # Create the main scrollable frame inside the canvas
        self.zone_controls_frame = ttk.Frame(self.controls_canvas)

        # Create a frame for the fixed button at the bottom
        self.fixed_button_frame = ttk.Frame(parent)

        # Configure canvas scrolling
        self.controls_canvas.configure(yscrollcommand=self.controls_scrollbar.set)

        # Pack the scrollbar and canvas
        self.controls_scrollbar.pack(side="right", fill="y")
        self.fixed_button_frame.pack(side="bottom", fill="x", padx=5, pady=5)
        self.controls_canvas.pack(side="left", fill="both", expand=True)

        # Create window in canvas for the scrollable frame
        self.controls_canvas_window = self.controls_canvas.create_window(
            0, 0, anchor="nw", window=self.zone_controls_frame
        )

        # Bind events for proper scrolling behavior
        self.zone_controls_frame.bind("<Configure>", self._on_frame_configure)
        self.controls_canvas.bind("<Configure>", self._on_canvas_configure_scroll)
        self._bind_mousewheel()

    def _on_frame_configure(self, event=None):
        """Update scroll region when frame size changes."""
        self.controls_canvas.configure(scrollregion=self.controls_canvas.bbox("all"))

    def _on_canvas_configure_scroll(self, event=None):
        """Update frame width when canvas size changes."""
        canvas_width = event.width if event else self.controls_canvas.winfo_width()
        self.controls_canvas.itemconfig(self.controls_canvas_window, width=canvas_width)

    def _bind_mousewheel(self):
        """Bind mouse wheel scrolling to the canvas."""

        def _on_mousewheel(event):
            self.controls_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        self.controls_canvas.bind("<MouseWheel>", _on_mousewheel)
        # For Linux
        self.controls_canvas.bind(
            "<Button-4>", lambda e: self.controls_canvas.yview_scroll(-1, "units")
        )
        self.controls_canvas.bind(
            "<Button-5>", lambda e: self.controls_canvas.yview_scroll(1, "units")
        )

    def _recenter_canvas_image(self, canvas_width, canvas_height):
        """Recenter the canvas background image."""
        if not hasattr(self, "_canvas_bg_position"):
            return

        # Remove the old image
        self.roi_canvas.delete("background_image")

        # Center the image in the new canvas size
        center_x = canvas_width // 2
        center_y = canvas_height // 2

        # Update stored position
        self._canvas_bg_position = (center_x, center_y, "center")

        # Create the centered image
        self.roi_canvas.create_image(
            center_x,
            center_y,
            anchor="center",
            image=self._canvas_bg_image,
            tags="background_image",
        )

    def _on_roi_rule_change(self, event=None):
        """Handle ROI inclusion rule change and update UI accordingly."""
        rule = self.roi_inclusion_rule_var.get()

        # Hide all parameter frames first
        self.radius_frame.pack_forget()
        self.overlap_frame.pack_forget()

        # Show appropriate parameters and help text based on rule
        if rule == "centroid_in":
            help_text = (
                "Considera dentro quando o centróide do animal está dentro do "
                "polígono da ROI. Simples e rápido; pode perder entradas parciais "
                "(ex.: cabeça entra primeiro)."
            )

        elif rule == "centroid_in_on_buffered_roi":
            self.radius_frame.pack(fill="x", pady=2)
            help_text = (
                "Igual ao centróide, porém com ROI dilatada por r para capturar "
                "entradas parciais (ex.: cabeça). r em cm se houver calibração; "
                "senão em px."
            )

        elif rule == "bbox_intersects":
            self.overlap_frame.pack(fill="x", pady=2)
            self.overlap_help_label.config(
                text="A detecção é considerada dentro da ROI quando a fração de "
                "área do bbox contida na ROI atinge este valor."
            )
            help_text = (
                "Considera dentro quando o retângulo do animal (bbox) sobrepõe a "
                "ROI ao menos pela fração definida. Captura entradas parciais; "
                "pode superestimar em bordas."
            )

        elif rule == "seg_overlap":
            self.overlap_frame.pack(fill="x", pady=2)
            self.overlap_help_label.config(
                text="Requer dados de máscara. Se não houver, selecione outra regra."
            )
            help_text = (
                "Considera dentro com base na sobreposição da máscara do animal com "
                "a ROI. Requer segmentação; mais preciso e mais custoso."
            )

        else:
            help_text = ""

        self.rule_help_label.config(text=help_text)

    def _on_apply_roi_settings(self):
        """Apply ROI inclusion rule settings to the global settings."""
        from zebtrack import settings

        try:
            # Validate and convert parameters
            buffer_radius = float(self.roi_buffer_radius_var.get())
            overlap_ratio = float(self.roi_overlap_ratio_var.get())

            # Validate ranges
            if buffer_radius < 0:
                raise ValueError("Raio de buffer deve ser >= 0")
            if not (0 <= overlap_ratio <= 1):
                raise ValueError("Fração de sobreposição deve estar entre 0 e 1")

            # Update settings if available
            if settings:
                settings.roi_inclusion_rule = self.roi_inclusion_rule_var.get()
                settings.roi_buffer_radius_value = buffer_radius
                settings.roi_min_bbox_overlap_ratio = overlap_ratio

                # Save to project if available
                if self.controller.project_manager.project_path:
                    self.controller.project_manager._save_settings_snapshot()

                self.show_info(
                    "Sucesso",
                    f"Configurações de ROI aplicadas:\n"
                    f"Regra: {settings.roi_inclusion_rule}\n"
                    f"Raio buffer: {settings.roi_buffer_radius_value}\n"
                    f"Sobreposição mínima: {settings.roi_min_bbox_overlap_ratio}",
                )
            else:
                self.show_warning(
                    "Aviso", "Settings não disponível. Configurações não foram salvas."
                )

        except ValueError as e:
            self.show_error("Erro de Validação", str(e))
        except Exception as e:
            self.show_error("Erro", f"Erro ao aplicar configurações: {e!s}")

    def setup_interactive_polygon(self, polygon: np.ndarray):
        """Draws a suggested polygon that the user can interactively edit."""
        # Garante que há frame no canvas antes de desenhar
        if self._canvas_bg_image is None:
            if not self.load_video_frame_to_canvas():
                self.show_error(
                    "Erro",
                    "Não foi possível carregar um frame para mostrar o polígono detectado.",
                )
                return

        self._clear_interactive_polygon()  # Clear any previous one
        self.edited_polygon_points = [list(p) for p in polygon]

        self._draw_interactive_polygon()

        # Show the save/discard buttons
        if self.interactive_buttons_frame:
            self.interactive_buttons_frame.pack(
                fill="x", padx=5, pady=5, before=self.roi_inclusion_frame
            )

        self.set_status("Ajuste o polígono arrastando os vértices. Salve ou descarte.")

    def _draw_interactive_polygon(self):
        """Helper to (re)draw the polygon and its handles based on current points."""
        # Clear previous drawings
        self.roi_canvas.delete("interactive_polygon", "handle", "edit_clamp_indicator")

        # Convert video coordinates to canvas coordinates for display
        canvas_points = []
        for point in self.edited_polygon_points:
            canvas_point = self._video_to_canvas(point[0], point[1])
            canvas_points.append([canvas_point[0], canvas_point[1]])

        # Draw the polygon itself using canvas coordinates
        flat_points = [coord for point in canvas_points for coord in point]
        self.interactive_polygon_item = self.roi_canvas.create_polygon(
            flat_points,
            fill="",
            outline="yellow",
            width=2,
            tags="interactive_polygon",
        )

        # Draw the handles using canvas coordinates
        self.polygon_handles = []
        for i, canvas_point in enumerate(canvas_points):
            x, y = canvas_point[0], canvas_point[1]

            # Check if this vertex is on the arena boundary (for visual feedback)
            is_on_boundary = False
            if (
                isinstance(self.current_editing_zone, tuple)
                and self.current_editing_zone[0] == "roi"
            ):
                zone_data = self.controller.project_manager.get_zone_data()
                main_arena_poly = zone_data.polygon if zone_data else None
                if main_arena_poly:
                    canvas_arena_poly = []
                    for point in main_arena_poly:
                        canvas_pt = self._video_to_canvas(point[0], point[1])
                        canvas_arena_poly.append([canvas_pt[0], canvas_pt[1]])

                    arena_array = np.array(canvas_arena_poly, dtype=np.float32)
                    result = cv2.pointPolygonTest(arena_array, (x, y), True)

                    # Consider point on boundary if very close to edge (distance ~0)
                    is_on_boundary = abs(result) < 1.0

            # Choose handle color based on whether it's clamped to boundary
            handle_fill = "orange" if is_on_boundary else "darkgoldenrod"
            handle_outline = "red" if is_on_boundary else "yellow"

            handle = self.roi_canvas.create_rectangle(
                x - 4,
                y - 4,
                x + 4,
                y + 4,
                fill=handle_fill,
                outline=handle_outline,
                tags=("handle", f"handle-{i}"),
            )
            self.polygon_handles.append(handle)

            # Draw an additional indicator circle for clamped vertices
            if is_on_boundary:
                self.roi_canvas.create_oval(
                    x - 8,
                    y - 8,
                    x + 8,
                    y + 8,
                    outline="orange",
                    width=2,
                    tags="edit_clamp_indicator",
                )

            # Bind events to each handle
            self.roi_canvas.tag_bind(
                handle, "<ButtonPress-1>", lambda e, i=i: self._on_handle_press(e, i)
            )
            self.roi_canvas.tag_bind(handle, "<B1-Motion>", self._on_handle_drag)
            self.roi_canvas.tag_bind(handle, "<ButtonRelease-1>", self._on_handle_release)

    def _on_handle_press(self, event, handle_index):
        """Records which handle is being dragged and initial offset."""
        self._dragged_handle_index = handle_index

        # Store the initial mouse position and handle position
        self._drag_start_mouse = (float(event.x), float(event.y))

        # Get current handle position in video coordinates
        video_point = self.edited_polygon_points[handle_index]
        # Convert to canvas coordinates
        canvas_point = self._video_to_canvas(video_point[0], video_point[1])
        self._drag_start_handle = canvas_point

        # Calculate offset between mouse and handle center
        self._drag_offset = (canvas_point[0] - event.x, canvas_point[1] - event.y)

        # Bind motion and release to the entire canvas so events continue even
        # when mouse leaves the handle
        self.roi_canvas.bind("<B1-Motion>", self._on_handle_drag_global)
        self.roi_canvas.bind("<ButtonRelease-1>", self._on_handle_release_global)

    def _on_handle_drag(self, event):
        """Updates the polygon point and redraws as the handle is dragged."""
        if self._dragged_handle_index is None:
            return

        # Apply the drag offset to get the actual handle position
        canvas_x = float(event.x) + self._drag_offset[0]
        canvas_y = float(event.y) + self._drag_offset[1]

        # Apply snapping to nearby vertices or edges
        snapped_point = self._apply_snapping(canvas_x, canvas_y, exclude_current_polygon=True)
        if snapped_point:
            canvas_x, canvas_y = snapped_point

        # If editing an ROI, clamp the point within the main arena
        if isinstance(self.current_editing_zone, tuple) and self.current_editing_zone[0] == "roi":
            main_arena_poly = self.controller.project_manager.get_zone_data().polygon
            if main_arena_poly:
                # Convert main arena polygon from video coords to canvas coords
                canvas_arena_poly = []
                for point in main_arena_poly:
                    canvas_pt = self._video_to_canvas(point[0], point[1])
                    canvas_arena_poly.append([canvas_pt[0], canvas_pt[1]])

                arena_array = np.array(canvas_arena_poly, dtype=np.float32)

                # Test if point is inside arena
                result = cv2.pointPolygonTest(arena_array, (canvas_x, canvas_y), True)

                # If outside arena (result < 0), clamp to nearest arena boundary
                if result < 0:
                    # Find the closest point on the arena boundary
                    min_dist = float("inf")
                    closest_point = (canvas_x, canvas_y)

                    # Check distance to each edge of the arena
                    for i in range(len(canvas_arena_poly)):
                        p1 = canvas_arena_poly[i]
                        p2 = canvas_arena_poly[(i + 1) % len(canvas_arena_poly)]

                        edge_snap = self._point_to_segment_distance(
                            canvas_x, canvas_y, p1[0], p1[1], p2[0], p2[1]
                        )

                        if edge_snap and edge_snap["distance"] < min_dist:
                            min_dist = edge_snap["distance"]
                            closest_point = (edge_snap["x"], edge_snap["y"])

                    # Update to clamped position
                    canvas_x, canvas_y = closest_point

        # Convert canvas coordinates to video coordinates before storing
        video_point = self._canvas_to_video(canvas_x, canvas_y)
        self.edited_polygon_points[self._dragged_handle_index] = [
            video_point[0],
            video_point[1],
        ]

        # Redraw the entire interactive polygon and its handles
        self._draw_interactive_polygon()

    def _on_handle_drag_global(self, event):
        """Global drag handler for canvas-wide dragging."""
        self._on_handle_drag(event)

    def _on_handle_release(self, event):
        """Finalizes the drag operation (called from tag binding)."""
        self._handle_release_common()

    def _on_handle_release_global(self, event):
        """Global release handler (called from canvas binding)."""
        # Unbind global handlers
        self.roi_canvas.unbind("<B1-Motion>")
        self.roi_canvas.unbind("<ButtonRelease-1>")
        self._handle_release_common()

    def _handle_release_common(self):
        """Common release logic."""
        self._dragged_handle_index = None
        self._drag_offset = (0, 0)

    def _on_save_arena(self):
        """Saves the edited polygon and makes it static."""
        if self.current_editing_zone == "arena":
            # Save main arena
            self.publish_event(
                Events.ZONE_SAVE_MANUAL_ARENA,
                {"polygon_points": self.edited_polygon_points},
            )
            status_message = "Arena principal salva com sucesso."
            self.set_status(status_message)
            # Enable ROI button after main arena is saved
            self._enable_roi_button_if_arena_exists()
            self._request_overview_refresh(reason=status_message, append_summary=True)
        elif isinstance(self.current_editing_zone, tuple) and self.current_editing_zone[0] == "roi":
            # Save ROI
            _, roi_index, roi_name = self.current_editing_zone
            zone_data = self.controller.project_manager.get_zone_data()

            # Update the ROI polygon
            zone_data.roi_polygons[roi_index] = self.edited_polygon_points

            # Save to project using new zone persistence helper
            self.controller.project_manager.save_zone_data(zone_data)

            status_message = f"ROI '{roi_name}' salva com sucesso."
            self.set_status(status_message)
            self._request_overview_refresh(reason=status_message, append_summary=True)
        else:
            # Fallback - assume arena (legacy behavior)
            self.controller.save_manual_arena(self.edited_polygon_points)
            status_message = "Zona salva com sucesso."
            self.set_status(status_message)
            # Enable ROI button after main arena is saved
            self._enable_roi_button_if_arena_exists()
            self._request_overview_refresh(reason=status_message, append_summary=True)

        # Clear interactive elements and redraw zones
        self._clear_interactive_polygon()
        self.redraw_zones_from_project_data()
        self.update_zone_listbox()
        self._refresh_zone_indicators()

    def _on_discard_arena(self):
        """Discards the interactive polygon."""
        self._clear_interactive_polygon()
        if self.current_editing_zone == "arena":
            self.set_status("Edição da arena descartada.")
        elif isinstance(self.current_editing_zone, tuple) and self.current_editing_zone[0] == "roi":
            _, _, roi_name = self.current_editing_zone
            self.set_status(f"Edição da ROI '{roi_name}' descartada.")
        else:
            self.set_status("Edição descartada.")

        # Redraw zones to restore original state
        self.redraw_zones_from_project_data()

    def _clear_interactive_polygon(self):
        """Clears all interactive elements from the canvas and hides buttons."""
        self.roi_canvas.delete("interactive_polygon", "handle", "suggested_polygon")
        try:
            if self.interactive_buttons_frame and self.interactive_buttons_frame.winfo_exists():
                self.interactive_buttons_frame.pack_forget()
        except Exception:
            # This can fail if the root window is already being destroyed.
            # It's safe to ignore in that case.
            pass

        self.interactive_polygon_item = None
        self.polygon_handles = []
        self.edited_polygon_points = []
        self._dragged_handle_index = None
        self._drag_offset = (0, 0)
        self.current_editing_zone = None

    def display_roi_video_frame(self, video_path):
        """
        Loads the first frame of a video, displays it on the canvas,
        and adjusts the window size.
        """
        try:
            if not video_path or not os.path.exists(video_path):
                log.error(
                    "gui.display_roi_frame.invalid_path",
                    path=video_path,
                )
                self.controller.project_manager.set_active_zone_video(None)
                self.show_error(
                    "Erro",
                    "O vídeo selecionado não foi encontrado ou está inacessível.",
                )
                return

            self.controller.project_manager.set_active_zone_video(video_path)
            self._refresh_roi_templates()

            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                self.show_error("Erro", "Não foi possível abrir o vídeo.")
                return
            ret, frame = cap.read()
            cap.release()
            if not ret:
                self.show_error("Erro", "Não foi possível ler um frame do vídeo.")
                return

            # Logic to display on the canvas
            h, w, _ = frame.shape
            # Adjust the main window to a proportional size
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            win_w = min(int(screen_w * 0.8), w + 400)  # Account for controls space
            win_h = min(int(screen_h * 0.8), h + 150)  # Account for window decorations
            set_geometry_if_not_maximized(self.root, f"{win_w}x{win_h}")
            self.root.update_idletasks()

            # Convert the frame for display
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self._original_image = Image.fromarray(frame_rgb)
            # Also store as _raw_bg_image as mentioned in requirements
            self._raw_bg_image = self._original_image

            # Wait for the canvas to be properly sized after geometry update
            self.root.after(10, lambda: self._draw_bg_image_to_canvas())

        except Exception as e:
            self.show_error("Erro ao Exibir Frame", str(e))

    def _display_image_on_canvas(self):
        """Display the original image on the canvas with proper scaling."""
        if not hasattr(self, "_original_image") or not self._original_image:
            return

        # Get actual canvas dimensions after layout
        canvas_width = self.roi_canvas.winfo_width()
        canvas_height = self.roi_canvas.winfo_height()

        if canvas_width <= 1 or canvas_height <= 1:
            # Canvas not ready yet, try again
            self.root.after(10, self._display_image_on_canvas)
            return

        # Calculate scaling to fit image while maintaining aspect ratio
        img_w, img_h = self._original_image.size
        scale = min(canvas_width / img_w, canvas_height / img_h, 1.0)
        new_width = int(img_w * scale)
        new_height = int(img_h * scale)

        # Scale the image
        image = self._original_image.resize((new_width, new_height), Image.LANCZOS)

        # Clear canvas and display centered image
        self.roi_canvas.delete("all")
        self._canvas_bg_image = ImageTk.PhotoImage(image)

        # Center the image within the canvas
        center_x = canvas_width // 2
        center_y = canvas_height // 2

        # Store positioning for later restoration in redraw_zones_from_project_data
        self._canvas_bg_position = (center_x, center_y, "center")

        self.roi_canvas.create_image(
            center_x,
            center_y,
            anchor="center",
            image=self._canvas_bg_image,
            tags="background_image",
        )

    def _draw_bg_image_to_canvas(self):
        """Draws the background image to canvas with proper scaling and centering."""
        if not hasattr(self, "_raw_bg_image") or not self._raw_bg_image:
            if hasattr(self, "_original_image") and self._original_image:
                self._raw_bg_image = self._original_image
            else:
                return

        # Get actual canvas dimensions after layout
        canvas_width = self.roi_canvas.winfo_width()
        canvas_height = self.roi_canvas.winfo_height()

        if canvas_width <= 1 or canvas_height <= 1:
            # Canvas not ready yet, try again
            self.root.after(10, self._draw_bg_image_to_canvas)
            return

        # Calculate scaling to fit image while maintaining aspect ratio
        img_w, img_h = self._raw_bg_image.size
        scale = min(canvas_width / img_w, canvas_height / img_h, 1.0)
        new_width = int(img_w * scale)
        new_height = int(img_h * scale)

        # Store scaling information for coordinate conversion
        self._bg_scale = scale
        self._bg_img_size = (img_w, img_h)  # Original image size

        # Calculate offset (top-left position of scaled image in canvas)
        center_x = canvas_width // 2
        center_y = canvas_height // 2
        offset_x = center_x - new_width // 2
        offset_y = center_y - new_height // 2
        self._bg_offset = (offset_x, offset_y)

        # Scale the image
        image = self._raw_bg_image.resize((new_width, new_height), Image.LANCZOS)

        # Clear canvas and display centered image
        self.roi_canvas.delete("all")
        self._canvas_bg_image = ImageTk.PhotoImage(image)

        # Store positioning for later restoration in redraw_zones_from_project_data
        self._canvas_bg_position = (center_x, center_y, "center")

        self.roi_canvas.create_image(
            center_x,
            center_y,
            anchor="center",
            image=self._canvas_bg_image,
            tags="background_image",
        )

    def _canvas_to_video(self, canvas_x, canvas_y):
        """Convert canvas coordinates to video frame coordinates."""
        if not hasattr(self, "_bg_scale") or not hasattr(self, "_bg_offset"):
            # Fallback: return canvas coordinates if scaling info not available
            return (float(canvas_x), float(canvas_y))

        scale = self._bg_scale
        offset_x, offset_y = self._bg_offset

        # Convert canvas coordinates to video coordinates
        video_x = (canvas_x - offset_x) / scale
        video_y = (canvas_y - offset_y) / scale

        return (float(video_x), float(video_y))

    def _video_to_canvas(self, video_x, video_y):
        """Convert video frame coordinates to canvas coordinates."""
        if not hasattr(self, "_bg_scale") or not hasattr(self, "_bg_offset"):
            # Fallback: return video coordinates if scaling info not available
            return (float(video_x), float(video_y))

        scale = self._bg_scale
        offset_x, offset_y = self._bg_offset

        # Convert video coordinates to canvas coordinates
        canvas_x = video_x * scale + offset_x
        canvas_y = video_y * scale + offset_y

        return (float(canvas_x), float(canvas_y))

    def load_video_frame_to_canvas(self, video_path: str | None = None, frame_number: int = 0):
        """Carrega um frame do vídeo no canvas"""
        if video_path is None:
            # Tenta usar o vídeo pendente ou do projeto
            if hasattr(self, "pending_single_video_path") and self.pending_single_video_path:
                video_path = self.pending_single_video_path
            elif self.controller.project_manager.project_path:
                videos = self.controller.project_manager.get_all_videos()
                if videos:
                    video_path = videos[0].get("path")

        if not video_path or not os.path.exists(video_path):
            log.error("gui.load_frame.no_video")
            self.controller.project_manager.set_active_zone_video(None)
            return False

        try:
            self.controller.project_manager.set_active_zone_video(video_path)

            cap = cv2.VideoCapture(video_path)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ret, frame = cap.read()
            cap.release()

            if not ret:
                return False

            # Convert frame and store original
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self._original_image = Image.fromarray(frame_rgb)
            # Also store as _raw_bg_image as mentioned in requirements
            self._raw_bg_image = self._original_image

            # Display the image using proper canvas scaling
            self._draw_bg_image_to_canvas()

            log.info("gui.canvas.frame_loaded", video=video_path)
            return True

        except Exception as e:
            log.error("gui.load_frame.error", error=str(e))
            return False

    @staticmethod
    def _video_sort_key(value):
        try:
            return (0, int(value))
        except (TypeError, ValueError):
            value_str = str(value) if value is not None else ""
            return (1, value_str.lower())

    @staticmethod
    def _format_subject_label(value):
        if value is None:
            return "??"
        if isinstance(value, int):
            return f"{value:02d}"
        if isinstance(value, float) and value.is_integer():
            return f"{int(value):02d}"
        value_str = str(value).strip()
        if not value_str:
            return "??"
        if value_str.isdigit():
            try:
                return f"{int(value_str):02d}"
            except ValueError:
                return value_str
        return value_str

    @staticmethod
    def _format_day_display(value):
        if value in (None, ""):
            return ""
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            try:
                return f"{int(value):02d}"
            except (TypeError, ValueError):
                return str(value)
        value_str = str(value).strip()
        if not value_str:
            return ""
        lower_value = value_str.lower()
        if lower_value == "sem dia":
            return "Sem Dia"
        match = re.search(r"(\d+)", value_str)
        if match:
            try:
                return f"{int(match.group(1)):02d}"
            except ValueError:
                return value_str
        return value_str

    def _build_day_title(self, day_value, metadata: dict | None = None) -> str:
        metadata = metadata or {}
        candidate = metadata.get("day_label") or ""
        if not candidate and metadata.get("day") is not None:
            candidate = self._format_day_display(metadata.get("day"))
        if not candidate:
            candidate = self._format_day_display(day_value)
        if not candidate:
            base_value = day_value if day_value not in (None, "") else None
            candidate = str(base_value) if base_value is not None else "Sem Dia"
        candidate_str = str(candidate).strip()
        if not candidate_str:
            candidate_str = "Sem Dia"
        if candidate_str.lower() == "sem dia":
            return "Sem Dia"
        return f"Dia {candidate_str}"

    def _build_video_hierarchy_data(
        self,
        all_videos: list[dict],
        search_text: str,
    ) -> dict[str, dict]:
        hierarchy: dict[str, dict] = {}

        normalized = search_text.strip().lower()

        for video in all_videos:
            metadata = video.get("metadata") or {}
            group_id = metadata.get("group") or "Sem Grupo"
            group_display = metadata.get("group_display_name") or group_id
            day_id = metadata.get("day") or "Sem Dia"
            day_display = metadata.get("day_label") or self._format_day_display(day_id)
            subject_id = metadata.get("subject")
            filename = os.path.basename(video.get("path", ""))
            status_label = video.get("status", "")

            searchable_values = (
                str(group_id),
                str(group_display),
                str(day_id),
                str(day_display),
                str(subject_id) if subject_id is not None else "",
                filename,
                status_label,
            )

            if normalized and not any(
                normalized in str(value).lower() for value in searchable_values
            ):
                continue

            group_data = hierarchy.setdefault(
                group_id,
                {"display": group_display, "days": {}},
            )
            days_dict = group_data["days"]

            has_arena = bool(video.get("has_arena"))
            has_rois = bool(video.get("has_rois"))
            has_trajectory = bool(video.get("has_trajectory"))
            has_complete = bool(video.get("has_complete_data")) or (
                has_arena and has_rois and has_trajectory
            )
            has_summary = bool(video.get("has_summary")) or bool(video.get("has_summary_parquet"))

            video_entry = {
                "path": video.get("path"),
                "metadata": metadata,
                "day_label": day_display,
                "has_arena": has_arena,
                "has_rois": has_rois,
                "has_trajectory": has_trajectory,
                "has_complete_data": has_complete,
                "has_summary": has_summary,
                "filename": filename,
                "status": status_label,
                "subject": subject_id,
            }

            days_dict.setdefault(day_id, []).append(video_entry)

        return hierarchy

    def _build_video_hierarchy_snapshot(self) -> list[dict]:
        controller = getattr(self, "controller", None)
        if not controller or not controller.project_manager:
            return []

        pm = controller.project_manager
        all_videos = pm.get_all_videos() or []
        hierarchy = self._build_video_hierarchy_data(all_videos, "")

        snapshot: list[dict] = []
        for group_id, group_data in sorted(
            hierarchy.items(), key=lambda item: str(item[1]["display"]).lower()
        ):
            group_entry = {
                "label": f"🏷️ {group_data['display']} ({group_id})",
                "status_label": "",
                "filename_display": "",
                "children": [],
            }
            for day_id, videos in sorted(
                group_data["days"].items(),
                key=lambda item: self._video_sort_key(item[0]),
            ):
                sample_metadata = videos[0].get("metadata") if videos else None
                day_title = self._build_day_title(day_id, sample_metadata)
                day_entry = {
                    "label": f"📅 {day_title}",
                    "status_label": "",
                    "children": [],
                }
                for video_entry in sorted(
                    videos,
                    key=lambda entry: self._video_sort_key(entry.get("subject")),
                ):
                    subject_label = self._format_subject_label(video_entry.get("subject"))
                    has_arena = video_entry.get("has_arena", False)
                    has_rois = video_entry.get("has_rois", False)
                    has_traj = video_entry.get("has_trajectory", False)
                    status_tokens = " ".join(
                        [
                            self._format_status_token(has_arena, "arena"),
                            self._format_status_token(has_rois, "rois"),
                            self._format_status_token(has_traj, "trajectory"),
                        ]
                    )
                    day_entry["children"].append(
                        {
                            "path": video_entry.get("path"),
                            "label": f"🐟 Sujeito {subject_label}",
                            "filename": video_entry.get("filename", ""),
                            "status_label": status_tokens,
                        }
                    )
                group_entry["children"].append(day_entry)
            snapshot.append(group_entry)

        return snapshot

    @staticmethod
    def _format_status_token(has_parquet: bool, symbol_key: str) -> str:
        symbol = STATUS_SYMBOLS[symbol_key]
        return f"{symbol} ✓" if has_parquet else f"{symbol} ✗"

    def _populate_video_selector_tree(self, filter_text: str | None = None):
        """Popula a árvore hierárquica do seletor de vídeos."""

        if not self.video_selector_tree:
            return

        # Determine filter text priority: argument > entry value > stored filter
        if filter_text is None:
            if self.video_search_var is not None:
                filter_text = self.video_search_var.get()
            elif self._video_selector_filter:
                filter_text = self._video_selector_filter
            else:
                filter_text = ""

        search_text = (filter_text or "").strip().lower()
        self._video_selector_filter = search_text

        for item in self.video_selector_tree.get_children():
            self.video_selector_tree.delete(item)

        # Configure readiness color tags
        self.video_selector_tree.tag_configure(
            "ready_full", background="#d4edda", foreground="#1e4620"
        )
        self.video_selector_tree.tag_configure(
            "ready_partial", background="#fff3cd", foreground="#5c470b"
        )
        self.video_selector_tree.tag_configure(
            "ready_missing", background="#f8d7da", foreground="#842029"
        )
        self.video_selector_tree.tag_configure("ready_optional", foreground="#5f4b00")

        controller = getattr(self, "controller", None)
        if not controller or not controller.project_manager:
            self._update_zone_summary_cards([])
            return

        pm = controller.project_manager
        if not pm.project_path:
            self._update_zone_summary_cards([])
            return

        all_videos = pm.get_all_videos()
        self._update_zone_summary_cards(all_videos)

        if not all_videos:
            return

        hierarchy = self._build_video_hierarchy_data(all_videos, search_text)
        readiness_tags = self._pending_readiness_snapshot or {}

        displayed_videos = 0

        def format_status(has_parquet: bool, symbol_key: str) -> str:
            symbol = STATUS_SYMBOLS[symbol_key]
            return f"{symbol} ✓" if has_parquet else f"{symbol} ✗"

        for group_id, group_data in sorted(
            hierarchy.items(), key=lambda item: str(item[1]["display"]).lower()
        ):
            days_dict = group_data["days"]
            total_group_videos = sum(len(videos) for videos in days_dict.values())
            if total_group_videos == 0:
                continue

            group_node = self.video_selector_tree.insert(
                "",
                "end",
                text=f"🏷️ {group_data['display']} ({group_id})",
                values=("", f"{total_group_videos} vídeos"),
                open=True,
            )

            for day_id, videos in sorted(
                days_dict.items(), key=lambda item: self._video_sort_key(item[0])
            ):
                if not videos:
                    continue

                sample_metadata = videos[0].get("metadata") if videos else None
                day_title = self._build_day_title(day_id, sample_metadata)
                day_node = self.video_selector_tree.insert(
                    group_node,
                    "end",
                    text=f"📅 {day_title}",
                    values=("", f"{len(videos)} vídeos"),
                    open=False,
                )

                for video_entry in sorted(
                    videos,
                    key=lambda entry: self._video_sort_key(entry.get("subject")),
                ):
                    video_path = video_entry.get("path") or ""
                    if not video_path:
                        continue

                    subject_label = self._format_subject_label(video_entry.get("subject"))

                    status_tokens = " ".join(
                        (
                            format_status(video_entry["has_arena"], "arena"),
                            format_status(video_entry["has_rois"], "rois"),
                            format_status(video_entry["has_trajectory"], "trajectory"),
                        )
                    )

                    extra_tags = readiness_tags.get(video_path, ())
                    if extra_tags:
                        tag_tuple = (video_path, *extra_tags)
                    else:
                        tag_tuple = (video_path,)

                    self.video_selector_tree.insert(
                        day_node,
                        "end",
                        text=f"🐟 Sujeito {subject_label}",
                        values=(status_tokens, video_entry["filename"]),
                        tags=tag_tuple,
                    )
                    displayed_videos += 1

        log.info(
            "gui.video_selector.populated",
            filter=self._video_selector_filter,
            groups=len(hierarchy),
            total_videos=len(all_videos),
            displayed=displayed_videos,
        )

        self._request_overview_refresh()

    def _refresh_video_selector_tree(self) -> None:
        """Repopula a árvore mantendo seleção e filtros atuais sempre que possível."""

        if not self.video_selector_tree:
            return

        selected_tag = None
        selection = self.video_selector_tree.selection()
        if selection:
            try:
                tags = self.video_selector_tree.item(selection[0], "tags")
                if tags:
                    selected_tag = tags[0]
            except Exception:
                selected_tag = None

        current_filter = getattr(self, "_video_selector_filter", "")
        self._populate_video_selector_tree(current_filter)

        if selected_tag:
            self._reselect_video_tree_item(selected_tag)

    def _reselect_video_tree_item(self, target_tag: str) -> None:
        if not target_tag or not self.video_selector_tree:
            return

        def _walk(node: str) -> bool:
            for child in self.video_selector_tree.get_children(node):
                tags = self.video_selector_tree.item(child, "tags")
                if tags and tags[0] == target_tag:
                    # Ensure branch is visible before selecting
                    parent = self.video_selector_tree.parent(child)
                    while parent:
                        self.video_selector_tree.item(parent, open=True)
                        parent = self.video_selector_tree.parent(parent)

                    self.video_selector_tree.selection_set(child)
                    self.video_selector_tree.see(child)
                    return True

                if _walk(child):
                    return True
            return False

        _walk("")

    def _filter_video_tree(self):
        """Filtra a árvore com base no texto de busca."""
        if self.video_search_var is None:
            return
        self._populate_video_selector_tree(self.video_search_var.get())

    def apply_pending_readiness_snapshot(
        self,
        *,
        ready_with_trajectory: list[dict],
        ready_with_zones: list[dict],
        arena_only: list[dict],
        without_arena: list[dict],
    ) -> None:
        mapping: dict[str, tuple[str, ...]] = {}

        def _assign(entries: list[dict], *tags: str) -> None:
            for info in entries or []:
                path = info.get("path")
                if path:
                    mapping[path] = tuple(tags)

        _assign(ready_with_trajectory, "ready_full")
        _assign(ready_with_zones, "ready_partial")
        _assign(arena_only, "ready_partial", "ready_optional")
        _assign(without_arena, "ready_missing")

        self._pending_readiness_snapshot = mapping

        if self.video_selector_tree:
            self._populate_video_selector_tree(self._video_selector_filter)

    def _load_selected_video_frame(self, event=None):
        """Carrega o frame do vídeo selecionado no canvas principal."""

        if not self.video_selector_tree:
            return

        selection = self.video_selector_tree.selection()
        if not selection:
            self.show_warning(
                "Nenhum Vídeo Selecionado",
                "Por favor, selecione um vídeo da lista para carregar.",
            )
            return

        item_id = selection[0]
        tags = self.video_selector_tree.item(item_id, "tags")

        if not tags or not tags[0]:
            self.show_info(
                "Selecione um Vídeo",
                ("Por favor, escolha um item com ícone de peixe (🐟) para carregar o frame."),
            )
            return

        video_path = tags[0]
        success = self.load_video_frame_to_canvas(video_path, frame_number=0)

        if success:
            self._maybe_offer_zone_reuse(video_path)
            self.redraw_zones_from_project_data()
            filename = os.path.basename(video_path)
            self.set_status(f"✓ Frame carregado: {filename}")
            log.info("gui.video_selector.frame_loaded", path=video_path)
        else:
            self.show_error(
                "Erro ao Carregar",
                f"Não foi possível carregar o vídeo selecionado.\n{video_path}",
            )

    def _maybe_offer_zone_reuse(self, video_path: str) -> None:
        """Prompt user to reuse the last zones when the current video has none."""

        if not video_path:
            return

        if video_path in self._zone_prompt_history:
            return

        pm = self.controller.project_manager
        if pm.has_zone_data(video_path):
            return

        last_video_with_zones = pm.get_last_zone_video(exclude=video_path)
        if not last_video_with_zones or not pm.has_zone_data(last_video_with_zones):
            return

        self._zone_prompt_history.add(video_path)

        current_name = os.path.basename(video_path)
        last_name = os.path.basename(last_video_with_zones)

        reuse = messagebox.askyesno(
            "Reutilizar zonas existentes?",
            (
                f'O vídeo "{current_name}" não possui arena ou ROIs salvas.\n\n'
                f'Deseja reutilizar as zonas desenhadas para "{last_name}"?\n'
                'Escolha "Sim" para reutilizar ou "Não" para começar do zero.'
            ),
            icon="question",
        )

        if reuse:
            cloned_zone_data = pm.clone_zone_data_from_video(last_video_with_zones)
            pm.save_zone_data(cloned_zone_data, video_path=video_path, persist=False)
            copied_files = pm.copy_zone_parquet_files(
                last_video_with_zones, video_path, persist=False
            )
            pm.save_project()
            self._refresh_zone_indicators()
            self._refresh_video_selector_tree()
            status_message = f'Zonas reutilizadas de "{last_name}" para "{current_name}".'
            self.set_status(status_message)
            self._request_overview_refresh(reason=status_message, append_summary=True)
            if not copied_files:
                self.show_warning(
                    "Arquivos Parquet Indisponíveis",
                    (
                        "As zonas foram copiadas, mas não encontramos os arquivos "
                        "Parquet originais para duplicar. Caso necessário, redesenhe "
                        "as zonas e salve-as manualmente para gerar novos arquivos."
                    ),
                )
        else:
            pm.clear_zone_data_for_video(video_path, persist=False)
            status_message = "Comece a desenhar a arena e as ROIs para este vídeo."
            self.set_status(status_message)
            self._request_overview_refresh(reason=status_message, append_summary=True)
            self._refresh_video_selector_tree()

    def _on_video_tree_double_click(self, event):
        """Callback para duplo clique no seletor de vídeos."""
        del event  # Evento não é utilizado diretamente
        self._load_selected_video_frame()

    def _create_reports_tab(self):
        """Creates the tab for viewing processed data and generating reports."""
        reports_tab_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(reports_tab_frame, text="Relatórios")

        # --- Estrutura Hierárquica do Experimento ---
        list_frame = ttk.LabelFrame(reports_tab_frame, text="Estrutura do Experimento", padding=10)
        list_frame.pack(fill="both", expand=True, pady=5)

        self.reports_tree = ttk.Treeview(
            list_frame,
            columns=("arena", "rois", "trajectory", "summary", "status"),
            show="tree headings",
        )

        # Cabeçalhos
        self.reports_tree.heading("#0", text="Nome")
        self.reports_tree.heading("arena", text="🏛️ Arena")
        self.reports_tree.heading("rois", text="📍 ROIs")
        self.reports_tree.heading("trajectory", text="📈 Trajetória")
        self.reports_tree.heading("summary", text=f"{STATUS_SYMBOLS['summary']} Sumário")
        self.reports_tree.heading("status", text="Status")

        # Larguras e alinhamentos
        self.reports_tree.column("#0", width=300, stretch=True)
        self.reports_tree.column("arena", width=80, anchor="center")
        self.reports_tree.column("rois", width=80, anchor="center")
        self.reports_tree.column("trajectory", width=100, anchor="center")
        self.reports_tree.column("summary", width=90, anchor="center")
        self.reports_tree.column("status", width=120, anchor="center")

        self.reports_tree.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.reports_tree.yview)
        self.reports_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        self.reports_tree.bind("<<TreeviewSelect>>", self._on_report_item_select)
        self.reports_tree.bind("<Double-1>", self._on_report_item_double_click)

        self._report_tree_metadata: dict[str, dict] = {}

        # --- Actions Panel ---
        actions_frame = ttk.LabelFrame(reports_tab_frame, text="Ações", padding=10)
        actions_frame.pack(fill="x", pady=5)

        self.generate_partial_report_btn = ttk.Button(
            actions_frame,
            text="Gerar Relatório para Selecionados",
            command=self._generate_partial_report,
            state="disabled",
        )
        self.generate_partial_report_btn.pack(side="left", padx=10)

        self.generate_unified_report_btn = ttk.Button(
            actions_frame,
            text="Gerar Relatório Unificado (Todos)",
            command=self._generate_unified_report,
        )
        self.generate_unified_report_btn.pack(side="left", padx=10)

    def update_reports_tree(self):
        """Atualiza a árvore de relatórios com estrutura hierárquica."""
        # Clear existing tree
        for item in self.reports_tree.get_children():
            self.reports_tree.delete(item)

        # Reset metadata store
        if not hasattr(self, "_report_tree_metadata"):
            self._report_tree_metadata = {}
        else:
            self._report_tree_metadata.clear()

        controller = getattr(self, "controller", None)
        if not controller or not controller.project_manager:
            log.debug("gui.update_reports.no_controller_or_pm")
            return

        pm = controller.project_manager
        all_videos = pm.get_all_videos()

        log.debug(
            "gui.update_reports.start",
            video_count=len(all_videos) if all_videos else 0,
            has_project_path=bool(pm.project_path),
        )

        if not all_videos:
            log.debug("gui.update_reports.no_videos")
            return

        hierarchy = self._build_report_hierarchy(all_videos, pm)
        self._populate_reports_tree_from_hierarchy(hierarchy, pm)

        log.info(
            "gui.reports_tree.updated",
            groups=len(hierarchy),
            total_videos=len(all_videos),
        )

        # Keep selector synced
        self._populate_video_selector_tree()

    def _sort_key_for_reports(self, value):
        try:
            return (0, int(value))
        except (TypeError, ValueError):
            value_str = str(value) if value is not None else ""
            return (1, value_str.lower())

    def _format_subject_for_reports(self, value):
        if value is None:
            return "??"
        if isinstance(value, int):
            return f"{value:02d}"
        if isinstance(value, float) and value.is_integer():
            return f"{int(value):02d}"
        value_str = str(value).strip()
        if not value_str:
            return "??"
        if value_str.isdigit():
            try:
                return f"{int(value_str):02d}"
            except ValueError:
                return value_str
        return value_str

    def _build_report_hierarchy(self, all_videos: list[dict], pm) -> dict:
        """Build a nested hierarchy of groups -> days -> entries used to populate the tree."""
        hierarchy: dict[str, dict] = {}
        for video in all_videos:
            metadata = video.get("metadata") or {}
            group_id = metadata.get("group") or "Sem Grupo"
            group_display = metadata.get("group_display_name") or group_id
            day_id = metadata.get("day") or "Sem Dia"

            has_arena = bool(video.get("has_arena"))
            has_rois = bool(video.get("has_rois"))
            has_trajectory = bool(video.get("has_trajectory"))
            has_complete = bool(video.get("has_complete_data")) or (
                has_arena and has_rois and has_trajectory
            )

            entry = {
                "path": video.get("path"),
                "has_arena": has_arena,
                "has_rois": has_rois,
                "has_trajectory": has_trajectory,
                "has_complete_data": has_complete,
                "status": video.get("status", "pending"),
                "filename": os.path.basename(video.get("path", "")),
                "subject": metadata.get("subject"),
                "results_dir": video.get("results_dir"),
                "metadata": dict(metadata),
                "parquet_files": dict(video.get("parquet_files") or {}),
            }

            if not entry["results_dir"] and entry["path"]:
                try:
                    computed_results = pm.resolve_results_directory(
                        os.path.splitext(os.path.basename(entry["path"]))[0],
                        video_path=entry["path"],
                        metadata=metadata,
                    )
                    entry["results_dir"] = str(computed_results)
                except Exception:  # pragma: no cover - defensive logging only
                    log.debug(
                        "gui.reports_tree.results_dir_compute_failed",
                        video=entry["path"],
                    )

            group_data = hierarchy.setdefault(group_id, {"display": group_display, "days": {}})
            group_days = group_data["days"]
            group_days.setdefault(day_id, []).append(entry)

        return hierarchy

    def _populate_reports_tree_from_hierarchy(self, hierarchy: dict, pm) -> None:
        """Insert nodes into the reports tree from a precomputed hierarchy."""
        for group_id, group_data in sorted(
            hierarchy.items(), key=lambda item: str(item[1]["display"]).lower()
        ):
            videos_by_day = group_data["days"]
            total_videos = sum(len(items) for items in videos_by_day.values())
            if total_videos == 0:
                continue
            total_arena = sum(
                1 for items in videos_by_day.values() for entry in items if entry["has_arena"]
            )
            total_rois = sum(
                1 for items in videos_by_day.values() for entry in items if entry["has_rois"]
            )
            total_trajectory = sum(
                1 for items in videos_by_day.values() for entry in items if entry["has_trajectory"]
            )
            total_complete = sum(
                1
                for items in videos_by_day.values()
                for entry in items
                if entry["has_complete_data"] or entry.get("has_summary")
            )

            group_node = self.reports_tree.insert(
                "",
                "end",
                text=f"🏷️ {group_data['display']}",
                values=(
                    self._format_status_ratio("arena", total_arena, total_videos),
                    self._format_status_ratio("rois", total_rois, total_videos),
                    self._format_status_ratio("trajectory", total_trajectory, total_videos),
                    self._format_status_ratio("summary", total_complete, total_videos),
                    f"{total_videos} vídeos",
                ),
                open=True,
            )

            self._report_tree_metadata[group_node] = {"type": "group", "identifier": group_id}

            for day_id, entries in sorted(
                videos_by_day.items(), key=lambda item: self._sort_key_for_reports(item[0])
            ):
                if not entries:
                    continue
                day_arena = sum(1 for entry in entries if entry["has_arena"])
                day_rois = sum(1 for entry in entries if entry["has_rois"])
                day_trajectory = sum(1 for entry in entries if entry["has_trajectory"])
                day_complete = sum(
                    1 for entry in entries if entry["has_complete_data"] or entry.get("has_summary")
                )
                sample_metadata = entries[0].get("metadata") if entries else None
                day_title = self._build_day_title(day_id, sample_metadata)

                day_node = self.reports_tree.insert(
                    group_node,
                    "end",
                    text=f"📅 {day_title}",
                    values=(
                        self._format_status_ratio("arena", day_arena, len(entries)),
                        self._format_status_ratio("rois", day_rois, len(entries)),
                        self._format_status_ratio("trajectory", day_trajectory, len(entries)),
                        self._format_status_ratio("summary", day_complete, len(entries)),
                        f"{len(entries)} vídeos",
                    ),
                    open=False,
                )

                self._report_tree_metadata[day_node] = {
                    "type": "day",
                    "identifier": day_id,
                    "group_id": group_id,
                }

                for entry in sorted(
                    entries, key=lambda item: self._sort_key_for_reports(item.get("subject"))
                ):
                    video_path = entry.get("path")
                    if not video_path:
                        continue

                    subject_label = self._format_subject_for_reports(entry.get("subject"))

                    video_node = self.reports_tree.insert(
                        day_node,
                        "end",
                        text=(f"🐟 Sujeito {subject_label}  ({entry['filename']})"),
                        values=(
                            self._format_status_token(entry["has_arena"], "arena"),
                            self._format_status_token(entry["has_rois"], "rois"),
                            self._format_status_token(entry["has_trajectory"], "trajectory"),
                            self._format_status_token(
                                entry.get("has_summary") or entry.get("has_complete_data"),
                                "summary",
                            ),
                            entry["status"],
                        ),
                        tags=("video-node",),
                    )

                    self._report_tree_metadata[video_node] = {
                        "type": "video",
                        "video_path": video_path,
                        "results_dir": entry.get("results_dir") or "",
                        "parquet_files": entry.get("parquet_files") or {},
                        "metadata": entry.get("metadata") or {},
                    }

                    self._append_report_artifacts(video_node, entry)

    def _append_report_artifacts(self, parent_id: str, entry: dict) -> None:
        tree = getattr(self, "reports_tree", None)
        if not tree:
            return

        video_path = entry.get("path")
        if not video_path:
            return

        results_dir = entry.get("results_dir") or ""
        parquet_files = entry.get("parquet_files") or {}
        experiment_id = Path(video_path).stem if video_path else None

        def _resolve_artifact(candidate: str | None, suffix: str) -> str | None:
            if candidate and os.path.exists(candidate):
                return candidate
            if results_dir and experiment_id:
                guess_path = Path(results_dir) / f"{experiment_id}_{suffix}"
                if guess_path.exists():
                    return str(guess_path)
            return None

        docx_path = _resolve_artifact(
            parquet_files.get("report_docx"),
            "report.docx",
        )
        excel_path = _resolve_artifact(
            parquet_files.get("summary_excel"),
            "summary.xlsx",
        )

        artifacts: list[tuple[str, str, str]] = []
        if docx_path:
            artifacts.append(("file", docx_path, "📝 Word: " + Path(docx_path).name))
        if excel_path:
            artifacts.append(("file", excel_path, "📊 Excel: " + Path(excel_path).name))

        if not artifacts:
            return

        for _kind, artifact_path, label in artifacts:
            child_id = tree.insert(
                parent_id,
                "end",
                text=label,
                values=("", "", "", "", "Abrir"),
                tags=("report-file",),
            )
            self._report_tree_metadata[child_id] = {
                "type": "file",
                "path": artifact_path,
                "parent_video": video_path,
            }

        tree.item(parent_id, open=True)

    def _on_report_item_select(self, event=None):
        """Enables or disables the partial report button based on selection."""
        selection = self.reports_tree.selection()
        has_video = False
        metadata_store = getattr(self, "_report_tree_metadata", {})
        for item_id in selection:
            metadata = metadata_store.get(item_id)
            if metadata and metadata.get("type") == "video":
                has_video = True
                break

        if has_video:
            self.generate_partial_report_btn.config(state="normal")
        else:
            self.generate_partial_report_btn.config(state="disabled")

    def _on_report_item_double_click(self, event=None):
        """Open the results folder for the selected video when reports exist."""
        tree = getattr(self, "reports_tree", None)
        if not tree:
            return

        item_id = None
        if event is not None:
            item_id = tree.identify_row(event.y)
        if not item_id:
            selection = tree.selection()
            if selection:
                item_id = selection[0]
        if not item_id:
            return

        metadata_store = getattr(self, "_report_tree_metadata", {})
        metadata = metadata_store.get(item_id)
        if not metadata:
            return

        node_type = metadata.get("type")

        if node_type == "file":
            self._handle_report_file_node(metadata)
            return

        if node_type != "video":
            return

        self._handle_report_video_node(metadata)

    def _handle_report_file_node(self, metadata: dict) -> None:
        artifact_path = metadata.get("path")
        if artifact_path and os.path.exists(artifact_path):
            self._open_path_in_explorer(artifact_path)
        else:
            self.show_warning(
                "Arquivo não encontrado",
                (
                    "O relatório selecionado não foi localizado no disco. Gere "
                    "novamente o relatório para restaurar o arquivo."
                ),
            )

    def _handle_report_video_node(self, metadata: dict) -> None:
        video_path = metadata.get("video_path")
        if not video_path:
            return

        controller = getattr(self, "controller", None)
        pm = getattr(controller, "project_manager", None)
        if not pm:
            return

        entry = pm.find_video_entry(path=video_path)
        results_dir = metadata.get("results_dir") or ""
        metadata_hint: dict = {}
        has_results = False

        if entry:
            metadata_hint = dict(entry.get("metadata") or {})
            if not results_dir:
                results_dir = entry.get("results_dir") or ""
            for key in ("group", "group_display_name", "day", "subject"):
                if entry.get(key) is not None and key not in metadata_hint:
                    metadata_hint[key] = entry[key]
            parquet_files = entry.get("parquet_files") or {}
            for key in ("summary", "summary_excel", "report_docx"):
                candidate_path = parquet_files.get(key)
                if candidate_path and os.path.exists(candidate_path):
                    has_results = True
                    break

        experiment_id = Path(video_path).stem
        if not results_dir:
            results_path = pm.resolve_results_directory(
                experiment_id,
                video_path=video_path,
                metadata=metadata_hint,
            )
            results_dir = str(results_path)

        if not has_results and results_dir:
            summary_candidate = Path(results_dir) / f"{experiment_id}_summary.parquet"
            report_candidate = Path(results_dir) / f"{experiment_id}_report.docx"
            excel_candidate = Path(results_dir) / f"{experiment_id}_summary.xlsx"
            if summary_candidate.exists() or report_candidate.exists() or excel_candidate.exists():
                has_results = True

        if not results_dir or not os.path.isdir(results_dir) or not has_results:
            self.show_warning(
                "Relatórios indisponíveis",
                ("Gere o relatório para este vídeo antes de abrir a pasta de resultados."),
            )
            return

        self._open_path_in_explorer(results_dir)

    def _open_path_in_explorer(self, target_path: str) -> None:
        """Open the given directory in the user's file explorer."""
        try:
            if sys.platform.startswith("win"):
                os.startfile(target_path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", target_path])
            else:
                subprocess.Popen(["xdg-open", target_path])
        except Exception as exc:  # pragma: no cover - GUI feedback
            self.show_error(
                "Erro ao abrir pasta",
                (
                    "Não foi possível abrir o diretório de resultados.\n"
                    f"Caminho: {target_path}\n\nDetalhes: {exc}"
                ),
            )

    def _generate_partial_report(self):
        """
        Gathers selected videos and tells the controller to generate a partial report.
        """
        selected_items = self.reports_tree.selection()
        if not selected_items:
            return

        selected_videos = []
        all_videos = self.controller.project_manager.get_all_videos()
        metadata_store = getattr(self, "_report_tree_metadata", {})

        for item_id in selected_items:
            if not self.reports_tree.exists(item_id):
                continue
            metadata = metadata_store.get(item_id)
            if not metadata or metadata.get("type") != "video":
                continue
            video_path = metadata.get("video_path")
            if not video_path:
                continue
            for video_data in all_videos:
                if video_data["path"] == video_path:
                    selected_videos.append(video_data)
                    break

        if selected_videos:
            self.publish_event(
                Events.REPORT_GENERATE,
                {"videos": selected_videos, "report_type": "partial"},
            )

    def _generate_unified_report(self):
        """Tells the controller to generate a unified report of all project videos."""
        all_videos = self.controller.project_manager.get_all_videos()
        if not all_videos:
            self.show_warning(
                "Sem Dados",
                "Não há vídeos processados neste projeto para gerar um relatório.",
            )
            return
        self.publish_event(Events.REPORT_GENERATE, {"videos": all_videos, "report_type": "unified"})

    def _start_main_arena_drawing(self):
        """Starts drawing the main arena polygon."""
        # Prevent editing during analysis
        if self.analysis_active:
            self.show_warning(
                "Análise em Progresso",
                "Não é possível editar zonas durante a análise de vídeo.",
            )
            return

        self.current_drawing_type = "arena"

        self._start_polygon_drawing()

    def _start_roi_drawing(self):
        """Starts drawing an ROI polygon, checking if an arena exists first."""
        # Prevent editing during analysis
        if self.analysis_active:
            self.show_warning(
                "Análise em Progresso",
                "Não é possível editar zonas durante a análise de vídeo.",
            )
            return

        main_arena = self.controller.project_manager.get_zone_data().polygon
        if not main_arena:
            self.show_error(
                "Erro",
                "Por favor, defina o 'Polígono Principal' primeiro antes de "
                "adicionar Áreas de Interesse.",
            )
            return
        self.current_drawing_type = "roi"
        self._start_polygon_drawing()

    def _start_polygon_drawing(self):
        """Activates polygon drawing mode."""
        # Garante que há frame no canvas
        if self._canvas_bg_image is None:
            self.set_status("Carregando frame para desenho...")
            if not self.load_video_frame_to_canvas():
                self.show_error(
                    "Erro",
                    "Não foi possível carregar um frame. "
                    "Por favor, carregue um vídeo ou use 'Detectar Aquário (Auto)' "
                    "primeiro.",
                )
                return False

        # Preserve drawing type before cleaning
        preserved_drawing_type = self.current_drawing_type
        self._stop_drawing()  # Ensure clean state
        self.current_drawing_type = preserved_drawing_type  # Restore

        self.drawing_mode = "polygon"
        self.current_polygon_points = []
        self._poly_pts_canvas = []  # Canvas coordinates for UI
        self._poly_pts_video = []  # Video coordinates for saving
        self.roi_canvas.config(cursor="crosshair")
        self.roi_canvas.bind("<Button-1>", self._on_canvas_click)
        self.roi_canvas.bind("<Double-Button-1>", self._on_canvas_double_click)
        self.roi_canvas.bind("<Motion>", self._on_canvas_motion)

        # Add a persistent instruction label
        if not self.drawing_instruction_label:
            self.drawing_instruction_label = ttk.Label(
                self.zone_controls_frame,
                text="Clique para adicionar pontos.\nClique duplo para finalizar.",
                justify="center",
                relief="solid",
                padding=5,
            )
            self.drawing_instruction_label.pack(pady=5, before=self.zone_listbox.master)

        self.set_status(
            "Modo de Desenho (Polígono): Clique para adicionar pontos, clique duplo para finalizar."
        )

    def _stop_drawing(self):
        """Deactivates any drawing mode and unbinds all associated events."""
        # Destroy the instruction label if it exists
        if self.drawing_instruction_label:
            self.drawing_instruction_label.destroy()
            self.drawing_instruction_label = None

        self.drawing_mode = None
        self.current_drawing_type = None
        self.roi_canvas.config(cursor="")
        # Unbind all possible drawing events
        self.roi_canvas.unbind("<Button-1>")
        self.roi_canvas.unbind("<Double-Button-1>")
        self.roi_canvas.unbind("<Motion>")
        self.roi_canvas.unbind("<ButtonPress-1>")
        self.roi_canvas.unbind("<B1-Motion>")
        self.roi_canvas.unbind("<ButtonRelease-1>")

        self.roi_canvas.delete("elastic_line")
        self.roi_canvas.delete("drawing_aid")  # Deletes both vertices and fixed lines
        self.roi_canvas.delete("snap_indicator")  # Clear snap indicators

        # Clear coordinate lists
        self.current_polygon_points = []
        self._poly_pts_canvas = []
        self._poly_pts_video = []

        self.set_status("Pronto.")

    def _apply_snapping(self, canvas_x, canvas_y, exclude_current_polygon=False, snap_threshold=10):
        """
        Applies snapping to nearby vertices or edges of existing polygons.

        Args:
            canvas_x (float): X coordinate in canvas space
            canvas_y (float): Y coordinate in canvas space
            exclude_current_polygon (bool): If True, excludes the polygon
                currently being edited.
            snap_threshold (int): Maximum distance in pixels for snapping to occur

        Returns:
            tuple or None: (snapped_x, snapped_y) if snapping occurred, None otherwise
        """
        zone_data = self._get_zone_data_for_active_context()
        all_polygons = []

        # Add main arena polygon if it exists
        if zone_data.polygon:
            # Convert to canvas coordinates
            canvas_polygon = []
            for point in zone_data.polygon:
                canvas_pt = self._video_to_canvas(point[0], point[1])
                canvas_polygon.append(canvas_pt)

            # Only add if not editing this polygon
            if not (exclude_current_polygon and self.current_editing_zone == "arena"):
                all_polygons.append(canvas_polygon)

        # Add all ROI polygons
        for idx, roi_polygon in enumerate(zone_data.roi_polygons):
            canvas_polygon = []
            for point in roi_polygon:
                canvas_pt = self._video_to_canvas(point[0], point[1])
                canvas_polygon.append(canvas_pt)

            # Only add if not editing this specific ROI
            skip_this_roi = (
                exclude_current_polygon
                and isinstance(self.current_editing_zone, tuple)
                and self.current_editing_zone[0] == "roi"
                and self.current_editing_zone[1] == idx
            )
            if not skip_this_roi:
                all_polygons.append(canvas_polygon)

        # Find closest point
        closest_point = None
        min_distance = snap_threshold

        for polygon in all_polygons:
            # Check snapping to vertices
            for vertex in polygon:
                dist = np.sqrt((canvas_x - vertex[0]) ** 2 + (canvas_y - vertex[1]) ** 2)
                if dist < min_distance:
                    min_distance = dist
                    closest_point = vertex

            # Check snapping to edges
            for i in range(len(polygon)):
                p1 = polygon[i]
                p2 = polygon[(i + 1) % len(polygon)]

                # Calculate distance from point to line segment
                edge_snap = self._point_to_segment_distance(
                    canvas_x, canvas_y, p1[0], p1[1], p2[0], p2[1]
                )

                if edge_snap and edge_snap["distance"] < min_distance:
                    min_distance = edge_snap["distance"]
                    closest_point = (edge_snap["x"], edge_snap["y"])

        anchors: list[tuple[float, float]] = [
            tuple(vertex) for polygon in all_polygons for vertex in polygon
        ]
        axis_centers: list[tuple[float, float]] = []

        if zone_data.polygon:
            centroid = polygon_centroid(zone_data.polygon)
            if centroid:
                axis_centers.append(self._video_to_canvas(*centroid))

        for roi_polygon in zone_data.roi_polygons or []:
            centroid = polygon_centroid(roi_polygon)
            if centroid:
                axis_centers.append(self._video_to_canvas(*centroid))

        axis_snap = snap_point_to_axes(
            (canvas_x, canvas_y),
            anchors=anchors,
            centers=axis_centers,
            threshold=float(snap_threshold),
        )

        if axis_snap is not None:
            axis_dist = np.sqrt((canvas_x - axis_snap[0]) ** 2 + (canvas_y - axis_snap[1]) ** 2)
            if axis_dist < min_distance:
                closest_point = axis_snap
                min_distance = axis_dist

        return closest_point

    def _refresh_roi_templates(self, clear_selection: bool = False) -> None:
        """Refresh template list. If clear_selection=True, always reset to blank."""
        pm = getattr(self.controller, "project_manager", None)
        if pm is None:
            return

        try:
            templates = pm.list_roi_templates()
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("gui.roi_templates.refresh_failed", error=str(exc))
            templates = []

        enriched: list[dict[str, Any]] = []
        for template in templates:
            if not isinstance(template, dict):
                continue

            entry = dict(template)
            entry["display_name"] = self._format_roi_template_display(entry)
            entry["identifier"] = self._build_roi_template_identifier(entry)
            enriched.append(entry)

        self._roi_templates_cache = enriched
        names = [entry["display_name"] for entry in enriched]

        if self.roi_template_combobox:
            self.roi_template_combobox.configure(values=names)

        # If clear_selection is requested, always blank the combobox
        if clear_selection:
            self.roi_template_var.set("")
            return

        current_display = self.roi_template_var.get()
        if names and current_display in names:
            return

        # Only auto-select first template if something was already selected
        # (to avoid pre-populating on initial load)
        if current_display and names:
            self.roi_template_var.set(names[0])
        else:
            self.roi_template_var.set("")

    def _on_save_roi_template(self) -> None:
        pm = getattr(self.controller, "project_manager", None)
        if pm is None:
            return

        zone_data = pm.get_zone_data()
        if not zone_data or (not zone_data.polygon and not (zone_data.roi_polygons or [])):
            self.show_warning(
                "Template incompleto",
                "Desenhe a arena ou pelo menos uma ROI antes de salvar um template.",
            )
            return

        allow_project = bool(getattr(pm, "project_path", None))
        selected_template = self._get_selected_roi_template()
        if selected_template:
            initial_name = selected_template.get("name", "")
        else:
            initial_name = self.roi_template_var.get() or ""
        dialog_result = self._show_template_save_dialog(
            has_arena=bool(zone_data.polygon),
            has_rois=bool(zone_data.roi_polygons),
            allow_project=allow_project,
            initial_name=initial_name,
        )

        if not dialog_result:
            return

        try:
            metadata = pm.save_roi_template(
                dialog_result["name"],
                zone_data,
                save_arena=dialog_result["save_arena"],
                save_rois=dialog_result["save_rois"],
                save_location=dialog_result["save_location"],
                custom_path=dialog_result.get("custom_path"),
                persist=dialog_result["save_location"] == "project",
            )
        except ValueError as exc:
            self.show_warning("Template inválido", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            log.error("gui.roi_templates.save_failed", error=str(exc))
            self.show_error("Erro ao salvar", str(exc))
            return

        self._refresh_roi_templates()
        self._select_roi_template(metadata)
        self.show_info(
            "Template salvo",
            (f"Template '{metadata.get('name', dialog_result['name'])}' disponível para uso."),
        )

    def _format_roi_template_display(self, template: dict[str, Any]) -> str:
        base_name = template.get("name", "")
        location = template.get("location", "project")

        content_parts: list[str] = []
        if template.get("includes_arena"):
            content_parts.append("Arena")
        if template.get("includes_rois"):
            content_parts.append("ROIs")

        if not content_parts:
            content_label = "Sem dados"
        elif len(content_parts) == 2:
            content_label = "Arena + ROIs"
        else:
            content_label = content_parts[0]

        location_label: str | None = None
        if location == "global":
            location_label = "Global"
        elif location not in {"project", "global", None}:
            location_label = str(location)

        suffix_parts = [content_label] if content_label else []
        if location_label:
            suffix_parts.append(location_label)

        suffix = f" ({'; '.join(suffix_parts)})" if suffix_parts else ""

        if base_name:
            return f"{base_name}{suffix}"

        return suffix.lstrip() or "Template"

    def _build_roi_template_identifier(self, template: dict[str, Any]) -> str:
        location = template.get("location", "project")
        slug = template.get("slug") or ""
        file_ref = template.get("file") or ""

        if location == "project" and slug:
            return f"{location}:{slug}"

        if file_ref:
            return f"{location}:{file_ref}"

        return f"{location}:{template.get('name', '')}"

    def _get_selected_roi_template(self) -> dict[str, Any] | None:
        if not self._roi_templates_cache:
            return None

        current_display = self.roi_template_var.get()
        for entry in self._roi_templates_cache:
            if entry.get("display_name") == current_display:
                return entry

        return None

    def _get_zone_data_for_active_context(self) -> ZoneData:
        pm = getattr(self.controller, "project_manager", None)
        if pm is None:
            return ZoneData()

        active_video = pm.get_active_zone_video()
        if not active_video:
            pending_video = getattr(self, "pending_single_video_path", None)
            active_video = pending_video

        if active_video:
            try:
                zone_data = pm.get_zone_data(
                    video_path=active_video,
                    fallback_to_global=False,
                )
            except Exception:
                zone_data = ZoneData()

            if zone_data and (zone_data.polygon or zone_data.roi_polygons):
                return zone_data

        return pm.get_zone_data()

    def _select_roi_template(self, metadata: dict[str, Any]) -> None:
        identifier = self._build_roi_template_identifier(metadata)
        for entry in self._roi_templates_cache:
            if entry.get("identifier") == identifier:
                self.roi_template_var.set(entry.get("display_name", ""))
                return

        fallback_name = metadata.get("name", "")
        if fallback_name:
            for entry in self._roi_templates_cache:
                if entry.get("name") == fallback_name:
                    self.roi_template_var.set(entry.get("display_name", ""))
                    return

        self.roi_template_var.set("")

    def _show_template_save_dialog(
        self,
        *,
        has_arena: bool,
        has_rois: bool,
        allow_project: bool,
        initial_name: str,
    ) -> dict[str, Any] | None:
        dialog = SaveROITemplateDialog(
            self.root,
            default_name=initial_name,
            has_arena=has_arena,
            has_rois=has_rois,
            allow_project=allow_project,
        )

        if not dialog.result:
            return None

        return dialog.result

    def _on_import_roi_template(self) -> None:
        """Import a template file into the library (does not apply it)."""
        pm = getattr(self.controller, "project_manager", None)
        if pm is None:
            return

        file_path = filedialog.askopenfilename(
            title="Importar Template de ROI para Biblioteca",
            filetypes=[("Templates de ROI", "*.json"), ("Todos os arquivos", "*.*")],
        )
        if not file_path:
            return

        try:
            metadata = pm.import_roi_template(file_path)
        except Exception as exc:  # pragma: no cover - defensive
            log.error("gui.roi_templates.import_failed", error=str(exc), file=file_path)
            self.show_error("Erro ao importar", str(exc))
            return

        self._refresh_roi_templates()
        self._select_roi_template(metadata)
        template_name = metadata.get("name", Path(file_path).stem)
        message = (
            f"Template '{template_name}' adicionado à biblioteca.\n\n"
            "Use o botão 'Aplicar' para usar este template."
        )
        self.show_info("Template importado", message)

    def _on_import_and_apply_roi_template(self) -> None:
        """Import a template file and immediately apply it to current video."""
        pm = getattr(self.controller, "project_manager", None)
        if pm is None:
            return

        file_path = filedialog.askopenfilename(
            title="Importar e Aplicar Template de ROI",
            filetypes=[("Templates de ROI", "*.json"), ("Todos os arquivos", "*.*")],
        )
        if not file_path:
            return

        # Get active video context
        active_video = pm.get_active_zone_video()
        if not active_video:
            pending_video = getattr(self, "pending_single_video_path", None)
            if pending_video:
                try:
                    pm.set_active_zone_video(pending_video)
                except Exception as exc:  # pragma: no cover - defensive
                    log.warning(
                        "gui.roi_templates.activate_pending_failed",
                        error=str(exc),
                        video=pending_video,
                    )
                active_video = pm.get_active_zone_video() or pending_video

        if not active_video:
            self.show_warning(
                "Vídeo não selecionado",
                "Selecione um vídeo antes de aplicar o template.",
            )
            return

        try:
            # Load template directly from file
            import json

            with open(file_path, encoding="utf-8") as f:
                template_data = json.load(f)

            # Convert to ZoneData
            from zebtrack.core.detector import ZoneData

            template_zone = ZoneData(
                polygon=template_data.get("polygon"),
                roi_polygons=template_data.get("roi_polygons", []),
                roi_names=template_data.get("roi_names", []),
                roi_colors=template_data.get("roi_colors", []),
            )

            # Save to project
            pm.save_zone_data(
                template_zone,
                video_path=active_video,
                persist=bool(pm.project_path),
            )

            if active_video:
                pm.set_active_zone_video(active_video)

            self.controller.setup_detector_zones()

            log.info(
                "gui.roi_templates.imported_and_applied",
                video=active_video,
                file=file_path,
                polygon_points=len(template_zone.polygon or []),
                roi_count=len(template_zone.roi_polygons or []),
            )

        except Exception as exc:  # pragma: no cover - defensive
            log.error(
                "gui.roi_templates.import_and_apply_failed",
                error=str(exc),
                file=file_path,
            )
            self.show_error("Erro ao importar e aplicar", str(exc))
            return

        # Refresh UI
        self.redraw_zones_from_project_data()
        self.update_zone_listbox()
        self._refresh_zone_indicators()
        self._enable_roi_button_if_arena_exists()

        # Optionally import to library as well
        try:
            metadata = pm.import_roi_template(file_path)
            self._refresh_roi_templates()
            self._select_roi_template(metadata)
        except Exception:  # pragma: no cover - if import fails, we still applied
            pass

        template_name = Path(file_path).stem
        self.show_info(
            "Template aplicado",
            f"As zonas foram atualizadas com o template '{template_name}'.",
        )

    def _on_apply_roi_template(self) -> None:
        pm = getattr(self.controller, "project_manager", None)
        if pm is None:
            return

        selected_template = self._get_selected_roi_template()
        if not selected_template:
            self.show_warning(
                "Nenhum template selecionado",
                "Escolha um template para aplicar nas áreas de interesse.",
            )
            return

        active_video = pm.get_active_zone_video()
        if not active_video:
            pending_video = getattr(self, "pending_single_video_path", None)
            if pending_video:
                try:
                    pm.set_active_zone_video(pending_video)
                except Exception as exc:  # pragma: no cover - defensive
                    log.warning(
                        "gui.roi_templates.activate_pending_failed",
                        error=str(exc),
                        video=pending_video,
                    )
                active_video = pm.get_active_zone_video() or pending_video

        if not active_video:
            self.show_warning(
                "Vídeo não selecionado",
                "Selecione um vídeo na lista antes de aplicar o template.",
            )
            return

        template_name = (
            selected_template.get("name") or selected_template.get("display_name") or "Template"
        )
        template_location = selected_template.get("location")
        template_file = selected_template.get("file")

        try:
            template_zone = pm.load_roi_template(
                selected_template.get("name", ""),
                location=template_location,
                file_path=template_file,
            )
            pm.save_zone_data(
                template_zone,
                video_path=active_video,
                persist=bool(pm.project_path),
            )

            if active_video:
                pm.set_active_zone_video(active_video)

            self.controller.setup_detector_zones()
            log.info(
                "gui.roi_templates.zone_applied",
                video=active_video,
                polygon_points=len(template_zone.polygon or []),
                roi_count=len(template_zone.roi_polygons or []),
            )
        except FileNotFoundError as exc:
            log.error(
                "gui.roi_templates.file_missing",
                template=template_name,
                error=str(exc),
            )
            self.show_error(
                "Arquivo não encontrado",
                (
                    "O arquivo associado ao template não foi encontrado. "
                    "Remova ou importe novamente o template."
                ),
            )
            self._refresh_roi_templates()
            return
        except Exception as exc:  # pragma: no cover - defensive
            log.error(
                "gui.roi_templates.apply_failed",
                error=str(exc),
                template=template_name,
            )
            self.show_error("Erro ao aplicar template", str(exc))
            return

        self.redraw_zones_from_project_data()
        self.update_zone_listbox()
        self._refresh_zone_indicators()
        self._enable_roi_button_if_arena_exists()
        applied_zone = self._get_zone_data_for_active_context()
        log.info(
            "gui.roi_templates.post_refresh_state",
            polygon_points=len(applied_zone.polygon or []),
            roi_count=len(applied_zone.roi_polygons or []),
        )
        self.show_info(
            "Template aplicado",
            f"As zonas foram atualizadas com o template '{template_name}'.",
        )
        self.set_status(f"Template '{template_name}' aplicado ao vídeo em edição.")

    def _point_to_segment_distance(self, px, py, x1, y1, x2, y2):
        """
        Calculates the shortest distance from point (px, py) to line segment
        (x1,y1)-(x2,y2).

        Returns:
            dict or None: {'distance': float, 'x': float, 'y': float} with the
                         closest point on segment, or None if projection falls
                         outside segment
        """
        # Vector from p1 to p2
        dx = x2 - x1
        dy = y2 - y1

        if dx == 0 and dy == 0:
            # Degenerate segment (single point)
            dist = np.sqrt((px - x1) ** 2 + (py - y1) ** 2)
            return {"distance": dist, "x": x1, "y": y1}

        # Parameter t for projection of point onto line
        t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)

        # Clamp t to [0, 1] to stay on segment
        t = max(0, min(1, t))

        # Closest point on segment
        closest_x = x1 + t * dx
        closest_y = y1 + t * dy

        # Distance to closest point
        dist = np.sqrt((px - closest_x) ** 2 + (py - closest_y) ** 2)

        return {"distance": dist, "x": closest_x, "y": closest_y}

    def _on_canvas_click(self, event):
        """Handles single clicks on the canvas during polygon drawing."""
        if self.drawing_mode != "polygon":
            return

        # Get canvas coordinates directly from event
        canvas_x = float(event.x)
        canvas_y = float(event.y)

        # Apply snapping to nearby vertices or edges
        snapped_point = self._apply_snapping(canvas_x, canvas_y)
        if snapped_point:
            canvas_x, canvas_y = snapped_point

        # If drawing an ROI, check if the point is inside the main arena
        # Skip validation if point was snapped (will be adjusted when saving)
        if self.current_drawing_type == "roi" and not snapped_point:
            main_arena_poly = self.controller.project_manager.get_zone_data().polygon
            if main_arena_poly:
                # Convert main arena polygon from video coords to canvas coords
                canvas_arena_poly = []
                for point in main_arena_poly:
                    canvas_pt = self._video_to_canvas(point[0], point[1])
                    canvas_arena_poly.append([canvas_pt[0], canvas_pt[1]])

                # Test canvas coordinates against canvas polygon. Allow points on
                # the boundary (result >= 0) to support snapping to edges
                result = cv2.pointPolygonTest(
                    np.array(canvas_arena_poly, dtype=np.float32),
                    (canvas_x, canvas_y),
                    False,
                )
                if result < -0.5:  # Small tolerance for floating point errors
                    self.show_warning(
                        "Ponto Inválido",
                        "As Áreas de Interesse devem ser desenhadas dentro do Polígono Principal.",
                    )
                    return

        self.current_polygon_points.append((canvas_x, canvas_y))

        # Store both canvas and video coordinates
        canvas_point = (canvas_x, canvas_y)
        video_point = self._canvas_to_video(canvas_x, canvas_y)
        self._poly_pts_canvas.append(canvas_point)
        self._poly_pts_video.append(video_point)

        # Draw a small circle to mark the vertex
        self.roi_canvas.create_oval(
            canvas_x - 2,
            canvas_y - 2,
            canvas_x + 2,
            canvas_y + 2,
            fill="red",
            outline="red",
            tags=("temp_vertex", "drawing_aid"),
        )
        # Draw the fixed line segment if it's not the first point
        if len(self.current_polygon_points) > 1:
            p1 = self.current_polygon_points[-2]
            p2 = self.current_polygon_points[-1]
            self.roi_canvas.create_line(
                p1[0], p1[1], p2[0], p2[1], fill="cyan", width=2, tags="drawing_aid"
            )

    def _on_canvas_motion(self, event):
        """Handles mouse movement for drawing elastic lines."""
        if self.drawing_mode != "polygon":
            return

        self.roi_canvas.delete("elastic_line")
        self.roi_canvas.delete("snap_indicator")  # Clear previous snap indicator

        # Check for snapping
        canvas_x = float(event.x)
        canvas_y = float(event.y)
        snapped_point = self._apply_snapping(canvas_x, canvas_y)

        # Use snapped point if available, otherwise use cursor position
        display_x = snapped_point[0] if snapped_point else canvas_x
        display_y = snapped_point[1] if snapped_point else canvas_y

        # When drawing ROI, clamp the display indicator within the arena
        if self.current_drawing_type == "roi":
            main_arena_poly = self.controller.project_manager.get_zone_data().polygon
            if main_arena_poly:
                # Convert arena to canvas coordinates
                canvas_arena_poly = []
                for point in main_arena_poly:
                    canvas_pt = self._video_to_canvas(point[0], point[1])
                    canvas_arena_poly.append([canvas_pt[0], canvas_pt[1]])

                arena_array = np.array(canvas_arena_poly, dtype=np.float32)

                # Test if display point is inside arena
                result = cv2.pointPolygonTest(arena_array, (display_x, display_y), True)

                # If outside arena (result < 0), clamp to nearest arena boundary
                if result < 0:
                    # Find the closest point on the arena boundary
                    min_dist = float("inf")
                    closest_point = (display_x, display_y)

                    # Check distance to each edge of the arena
                    for i in range(len(canvas_arena_poly)):
                        p1 = canvas_arena_poly[i]
                        p2 = canvas_arena_poly[(i + 1) % len(canvas_arena_poly)]

                        edge_snap = self._point_to_segment_distance(
                            display_x, display_y, p1[0], p1[1], p2[0], p2[1]
                        )

                        if edge_snap and edge_snap["distance"] < min_dist:
                            min_dist = edge_snap["distance"]
                            closest_point = (edge_snap["x"], edge_snap["y"])

                    # Update display position to clamped point
                    display_x, display_y = closest_point

        # Draw snap indicator if snapping is active or if we're drawing ROI
        # (to show the clamped position within arena)
        should_show_indicator = snapped_point is not None or (
            self.current_drawing_type == "roi"
            and self.controller.project_manager.get_zone_data().polygon
        )

        if should_show_indicator:
            # Draw a small circle to indicate snap point
            self.roi_canvas.create_oval(
                display_x - 5,
                display_y - 5,
                display_x + 5,
                display_y + 5,
                outline="cyan",
                width=2,
                tags="snap_indicator",
            )

        # If no points yet, only show snap indicator
        if not self.current_polygon_points:
            return

        last_point = self.current_polygon_points[-1]
        first_point = self.current_polygon_points[0]

        # Line from last vertex to cursor (or snap point)
        self.roi_canvas.create_line(
            last_point[0],
            last_point[1],
            display_x,
            display_y,
            fill="yellow",
            dash=(4, 4),
            tags="elastic_line",
        )
        # Line from cursor (or snap point) to first vertex (if more than one
        # point exists)
        if len(self.current_polygon_points) > 1:
            self.roi_canvas.create_line(
                display_x,
                display_y,
                first_point[0],
                first_point[1],
                fill="yellow",
                dash=(4, 4),
                tags="elastic_line",
            )

    def _on_canvas_double_click(self, event):
        """Finaliza o desenho do polígono e o envia para o controlador."""
        # Fix: Auto-detect drawing type if not set (for single video workflow)
        if self.current_drawing_type is None and self.drawing_mode == "polygon":
            # If no main arena exists, assume we're drawing it
            zone_data = self.controller.project_manager.get_zone_data()
            if not zone_data.polygon:
                self.current_drawing_type = "arena"
            else:
                self.current_drawing_type = "roi"

        if self.drawing_mode != "polygon" or len(self.current_polygon_points) < 3:
            if self.current_polygon_points:
                self.show_warning(
                    "Polígono Incompleto",
                    "Um polígono precisa de pelo menos 3 pontos. Você tem "
                    f"{len(self.current_polygon_points)} pontos.",
                )
            self._stop_drawing()
            return

        try:
            # Limpa elementos temporários de desenho ANTES de salvar
            self.roi_canvas.delete("elastic_line")
            self.roi_canvas.delete("drawing_aid")

            if self.current_drawing_type == "arena":
                # Salva o polígono no projeto
                success = self.controller.set_main_arena_polygon(
                    self._poly_pts_video  # Use video coordinates instead
                )

                if success:
                    # Agora redesenha tudo do zero com os dados salvos
                    # Não chame _stop_drawing() ainda, pois ele limpa o canvas
                    self.drawing_mode = None
                    self.current_drawing_type = None
                    self.roi_canvas.config(cursor="")

                    # Unbind eventos
                    self.roi_canvas.unbind("<Button-1>")
                    self.roi_canvas.unbind("<Double-Button-1>")
                    self.roi_canvas.unbind("<Motion>")

                    # Limpa label de instrução
                    if self.drawing_instruction_label:
                        self.drawing_instruction_label.destroy()
                        self.drawing_instruction_label = None

                    # Força redesenho com dados salvos
                    self.redraw_zones_from_project_data()
                    self.update_zone_listbox()

                    status_message = "✓ Arena principal definida com sucesso!"
                    self.set_status(status_message)
                    self.show_info(
                        "Sucesso",
                        f"Arena principal criada com {len(self.current_polygon_points)} pontos.",
                    )
                    self._request_overview_refresh(reason=status_message, append_summary=True)
                else:
                    self.set_status("❌ Erro ao salvar arena principal.")
                    self.show_error("Erro", "Não foi possível salvar a arena principal.")
                    self._stop_drawing()

            elif self.current_drawing_type == "roi":
                roi_name = self.ask_string(
                    "Nome da ROI", "Digite um nome para esta nova Área de Interesse:"
                )
                if not roi_name:
                    self._stop_drawing()  # This now handles all cleanup
                    return

                # Selecionar cor da área
                color_dialog = ColorSelectionDialog(self.root)
                if not color_dialog.result:
                    self._stop_drawing()  # This now handles all cleanup
                    return

                selected_color = color_dialog.result
                roi_color = selected_color["rgb"]
                color_name = selected_color["name"]

                self.set_status(f"Salvando área de interesse '{roi_name}' ({color_name})...")
                success = self.controller.add_roi_polygon(
                    self._poly_pts_video,
                    roi_name,
                    roi_color,  # Use video coordinates
                )

                if success:
                    # Limpa o estado de desenho manualmente para ROI também
                    self.drawing_mode = None
                    self.current_drawing_type = None
                    self.roi_canvas.config(cursor="")

                    # Unbind eventos
                    self.roi_canvas.unbind("<Button-1>")
                    self.roi_canvas.unbind("<Double-Button-1>")
                    self.roi_canvas.unbind("<Motion>")

                    # Limpa label de instrução
                    if self.drawing_instruction_label:
                        self.drawing_instruction_label.destroy()
                        self.drawing_instruction_label = None

                    # Força redesenho com dados salvos
                    self.redraw_zones_from_project_data()
                    self.update_zone_listbox()

                    status_message = (
                        f"✓ Área de Interesse '{roi_name}' ({color_name}) adicionada com sucesso!"
                    )
                    self.set_status(status_message)
                    self.show_info(
                        "Sucesso",
                        f"Área de interesse '{roi_name}' ({color_name}) criada com "
                        f"{len(self.current_polygon_points)} pontos.",
                    )
                    self._request_overview_refresh(reason=status_message, append_summary=True)
                else:
                    self.set_status(f"❌ Erro ao salvar área de interesse '{roi_name}'.")
                    self.show_error(
                        "Erro",
                        f"Não foi possível salvar a área de interesse '{roi_name}'.",
                    )
                    self._stop_drawing()

        except Exception as e:
            self.set_status("❌ Erro durante salvamento.")
            self.show_error("Erro", str(e))
            self._stop_drawing()

        finally:
            # Limpa pontos temporários
            self.current_polygon_points = []

    def update_zone_listbox(self, zone_data: ZoneData | None = None):
        """Atualiza lista com indicadores visuais de cor."""
        # Guard against missing zone_listbox
        if not hasattr(self, "zone_listbox") or self.zone_listbox is None:
            return

        # Limpa lista
        for item in self.zone_listbox.get_children():
            self.zone_listbox.delete(item)

        if zone_data is None:
            zone_data = self._get_zone_data_for_active_context()

        # Arena principal com emoji e cor
        if zone_data.polygon:
            self.zone_listbox.insert(
                "",
                "end",
                values=("🏠 Arena Principal", "Polígono", "Ciano"),
                tags=("arena",),
            )
            # Configura cor do texto para arena
            self.zone_listbox.tag_configure("arena", foreground="darkcyan")

        # Enable/disable ROI button based on arena existence
        self._enable_roi_button_if_arena_exists(zone_data)

        # Mapear cores BGR (formato OpenCV) para nomes e hex
        color_map = {
            (0, 255, 0): ("Verde", "#00AA00"),
            (255, 0, 0): ("Azul", "#0000AA"),  # BGR: (255, 0, 0) = Blue
            (0, 0, 255): ("Vermelho", "#AA0000"),  # BGR: (0, 0, 255) = Red
            (0, 255, 255): ("Amarelo", "#AAAA00"),  # BGR: (0, 255, 255) = Yellow
            (255, 0, 255): ("Magenta", "#AA00AA"),  # BGR: (255, 0, 255) = Magenta
            (255, 255, 0): ("Ciano", "#00AAAA"),  # BGR: (255, 255, 0) = Cyan
        }

        # ROIs com emojis, cores e tags
        for i, name in enumerate(zone_data.roi_names):
            # Obter cor da ROI se disponível
            color_name = "Verde"
            color_hex = "#00AA00"

            if i < len(zone_data.roi_colors):
                roi_color = tuple(zone_data.roi_colors[i])
                color_info = color_map.get(roi_color, ("Verde", "#00AA00"))
                color_name = color_info[0]
                color_hex = color_info[1]

            # Insere ROI com emoji
            self.zone_listbox.insert(
                "",
                "end",
                values=(f"📍 {name}", "Área de Interesse", color_name),
                tags=(f"roi_{i}",),
            )

            # Configura cor do texto para ROI
            try:
                self.zone_listbox.tag_configure(f"roi_{i}", foreground=color_hex)
            except Exception:
                pass  # Fallback silencioso se a cor não for suportada

    def _enable_roi_button_if_arena_exists(self, zone_data: ZoneData | None = None):
        """Habilita o botão de desenhar ROI se a arena principal existir."""
        if not hasattr(self, "draw_roi_button") or self.draw_roi_button is None:
            return

        if zone_data is None:
            zone_data = self._get_zone_data_for_active_context()

        if zone_data.polygon:
            self.draw_roi_button.config(state="normal")
        else:
            self.draw_roi_button.config(state="disabled")

    def redraw_zones_from_project_data(self, zone_data: ZoneData | None = None):
        """Redesenha zonas preservando o background."""
        log.info("gui.redraw_zones.start")

        # Apaga apenas elementos de zona, preserva background
        for tag in [
            "main_polygon",
            "roi_polygon",
            "roi_label",
            "roi_label_bg",
            "elastic_line",
            "drawing_aid",
            "temp_vertex",
        ]:
            self.roi_canvas.delete(tag)

        # Background já deve estar presente, se não, tenta restaurar
        if self._canvas_bg_image:
            # Verifica se a imagem ainda está no canvas
            bg_items = self.roi_canvas.find_withtag("background_image")
            if not bg_items:
                # Use stored positioning if available, otherwise default to center
                if hasattr(self, "_canvas_bg_position"):
                    x, y, anchor = self._canvas_bg_position
                else:
                    # Fallback to center of current canvas
                    canvas_width = self.roi_canvas.winfo_width() or 800
                    canvas_height = self.roi_canvas.winfo_height() or 600
                    x, y, anchor = canvas_width // 2, canvas_height // 2, "center"

                self.roi_canvas.create_image(
                    x,
                    y,
                    anchor=anchor,
                    image=self._canvas_bg_image,
                    tags="background_image",
                )
                self.roi_canvas.tag_lower("background_image")  # Envia para trás
                log.info("gui.redraw_zones.background_restored")
        else:
            log.warning("gui.redraw_zones.no_background_image")
            # Tenta carregar um frame se não há imagem de fundo
            self.load_video_frame_to_canvas()

        if zone_data is None:
            zone_data = self._get_zone_data_for_active_context()
        log.info(
            "gui.redraw_zones.zone_data_loaded",
            has_main_polygon=bool(zone_data.polygon),
            roi_count=len(zone_data.roi_polygons),
        )

        # Desenha polígono principal
        if zone_data.polygon and len(zone_data.polygon) >= 3:
            try:
                # Convert video coordinates to canvas coordinates
                canvas_polygon = []
                for point in zone_data.polygon:
                    canvas_point = self._video_to_canvas(point[0], point[1])
                    canvas_polygon.extend([canvas_point[0], canvas_point[1]])

                self.roi_canvas.create_polygon(
                    canvas_polygon,
                    fill="",
                    outline="cyan",
                    width=2,
                    tags="main_polygon",
                )
                log.info("gui.main_polygon.drawn", points=len(zone_data.polygon))
            except Exception as e:
                log.error("gui.main_polygon.draw_error", error=str(e))

        # Desenha ROI polygons com melhorias visuais
        for i, polygon in enumerate(zone_data.roi_polygons):
            if len(polygon) < 3:
                continue

            # Cor da ROI (armazenada em BGR para OpenCV)
            color_bgr = zone_data.roi_colors[i] if i < len(zone_data.roi_colors) else (0, 255, 0)
            # Convert BGR to RGB for Tkinter hex color
            color_hex = f"#{color_bgr[2]:02x}{color_bgr[1]:02x}{color_bgr[0]:02x}"

            # Nome da ROI
            name = zone_data.roi_names[i] if i < len(zone_data.roi_names) else f"ROI_{i + 1}"

            # Desenha polígono com tags específicas
            try:
                # Convert video coordinates to canvas coordinates
                canvas_polygon = []
                for point in polygon:
                    canvas_point = self._video_to_canvas(point[0], point[1])
                    canvas_polygon.extend([canvas_point[0], canvas_point[1]])

                # Cria o polígono
                self.roi_canvas.create_polygon(
                    canvas_polygon,
                    fill="",  # Sem preenchimento para manter transparência
                    outline=color_hex,
                    width=2,
                    tags=("roi_polygon", f"roi_{i}"),
                )

                # Adiciona label com o nome no centro do polígono
                import numpy as np

                # Calculate center using canvas coordinates
                poly_array = np.array(
                    [
                        (canvas_polygon[i], canvas_polygon[i + 1])
                        for i in range(0, len(canvas_polygon), 2)
                    ]
                )
                center_x = int(poly_array[:, 0].mean())
                center_y = int(poly_array[:, 1].mean())

                # Cria fundo semi-transparente para melhor legibilidade
                self.roi_canvas.create_oval(
                    center_x - 25,
                    center_y - 10,
                    center_x + 25,
                    center_y + 10,
                    fill="white",
                    outline=color_hex,
                    width=1,
                    tags=("roi_label_bg", f"roi_label_bg_{i}"),
                )

                # Cria o texto do nome
                self.roi_canvas.create_text(
                    center_x,
                    center_y,
                    text=name,
                    fill=color_hex,
                    font=("Arial", 9, "bold"),
                    tags=("roi_label", f"roi_label_{i}"),
                )

                log.info("gui.roi_drawn", name=name, color=color_hex, points=len(polygon))

            except Exception as e:
                log.error("gui.roi_draw_error", name=name, error=str(e), index=i)

        # Atualiza listbox
        self.update_zone_listbox(zone_data)

        log.info("gui.redraw_zones.complete")

    def _remove_selected_roi(self):
        """Removes the ROI selected in the listbox."""
        selected_items = self.roi_listbox.selection()
        if not selected_items:
            self.show_warning(
                "Nenhuma Seleção", "Por favor, selecione uma ROI da lista para remover."
            )
            return

        selected_arena_id = self.arena_selector_var.get()
        if not selected_arena_id or selected_arena_id not in self.roi_data:
            return  # Should not happen if an item is selected

        # Find the index and name of the item to remove
        selected_item = selected_items[0]
        item_index = self.roi_listbox.index(selected_item)

        # Remove from data source
        del self.roi_data[selected_arena_id][item_index]

        # Refresh the view
        self._on_arena_select()

    def _run_center_periphery_analysis(self):
        """Runs the center-periphery analysis."""
        current_arena_id = self.arena_selector_var.get()
        if not current_arena_id:
            self.show_error("Erro", "Selecione um aquário ativo e carregue os dados primeiro.")
            return

        dialog = CenterPeripheryDialog(self.root)
        if not dialog.result:
            return

        self.controller.run_center_periphery_analysis(
            arena_id=current_arena_id,
            method=dialog.result["method"],
            value=dialog.result["value"],
        )

    def _create_template_rois(self):
        """Opens a dialog to create ROIs from a template."""
        current_arena_id = self.arena_selector_var.get()
        if not current_arena_id:
            self.show_error("Erro", "Selecione um aquário ativo primeiro.")
            return

        # Get the arena polygon bounds from the controller
        arena_data = self.controller.get_arena_data(current_arena_id)
        if not arena_data or "polygon_px" not in arena_data:
            self.show_error("Erro", "Não foi possível obter os dados do polígono do aquário.")
            return

        import numpy as np

        poly_points = np.array(arena_data["polygon_px"])
        x_min, y_min = poly_points.min(axis=0)
        x_max, y_max = poly_points.max(axis=0)
        width = x_max - x_min
        height = y_max - y_min

        dialog = TemplateDialog(self.root)
        if not dialog.result:
            return

        rois_to_add = []
        template = dialog.result
        if template["type"] == "vertical":
            lane_width = width / template["lanes"]
            for i in range(template["lanes"]):
                x1 = x_min + i * lane_width
                x2 = x1 + lane_width
                coords = [(x1, y_min), (x2, y_min), (x2, y_max), (x1, y_max)]
                rois_to_add.append({"name": f"V_Lane_{i + 1}", "type": "polygon", "coords": coords})
        elif template["type"] == "horizontal":
            lane_height = height / template["lanes"]
            for i in range(template["lanes"]):
                y1 = y_min + i * lane_height
                y2 = y1 + lane_height
                coords = [(x_min, y1), (x_max, y1), (x_max, y2), (x_min, y2)]
                rois_to_add.append({"name": f"H_Lane_{i + 1}", "type": "polygon", "coords": coords})
        elif template["type"] == "grid":
            col_width = width / template["cols"]
            row_height = height / template["rows"]
            for r in range(template["rows"]):
                for c in range(template["cols"]):
                    x1 = x_min + c * col_width
                    y1 = y_min + r * row_height
                    x2 = x1 + col_width
                    y2 = y1 + row_height
                    coords = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
                    rois_to_add.append(
                        {
                            "name": f"Grid_{r + 1}-{c + 1}",
                            "type": "polygon",
                            "coords": coords,
                        }
                    )

        self.roi_data.setdefault(current_arena_id, []).extend(rois_to_add)
        self._on_arena_select()

    def _start_circle_drawing(self):
        """Activates circle drawing mode."""
        self._stop_drawing()  # Ensure clean state
        self.drawing_mode = "circle"
        self.current_circle_center = None
        self.roi_canvas.config(cursor="crosshair")
        self.roi_canvas.bind("<ButtonPress-1>", self._on_canvas_press_circle)
        self.roi_canvas.bind("<B1-Motion>", self._on_canvas_drag_circle)
        self.roi_canvas.bind("<ButtonRelease-1>", self._on_canvas_release_circle)
        self.set_status("Modo de Desenho (Círculo): Clique e arraste para definir o raio.")

    def _on_canvas_press_circle(self, event):
        if self.drawing_mode != "circle":
            return
        self.current_circle_center = (event.x, event.y)

    def _on_canvas_drag_circle(self, event):
        if self.drawing_mode != "circle" or not self.current_circle_center:
            return

        self.roi_canvas.delete("elastic_line")
        cx, cy = self.current_circle_center
        radius = ((event.x - cx) ** 2 + (event.y - cy) ** 2) ** 0.5
        self.roi_canvas.create_oval(
            cx - radius,
            cy - radius,
            cx + radius,
            cy + radius,
            outline="yellow",
            dash=(4, 4),
            tags="elastic_line",
        )

    def _on_canvas_release_circle(self, event):
        if self.drawing_mode != "circle" or not self.current_circle_center:
            return

        cx, cy = self.current_circle_center
        radius = ((event.x - cx) ** 2 + (event.y - cy) ** 2) ** 0.5

        if radius < 2:  # Ignore tiny circles
            self._stop_drawing()
            return

        roi_name = self.ask_string(
            "Nome da ROI",
            "Digite um nome para esta nova Região de Interesse (Círculo):",
        )
        if not roi_name:
            self._stop_drawing()
            return

        current_arena_id = self.arena_selector_var.get()
        if not current_arena_id:
            self.show_error("Erro", "Nenhum aquário ativo selecionado.")
            self._stop_drawing()
            return

        new_roi = {"name": roi_name, "type": "circle", "coords": (cx, cy, radius)}
        self.roi_data.setdefault(current_arena_id, []).append(new_roi)

        self.roi_canvas.create_oval(
            cx - radius,
            cy - radius,
            cx + radius,
            cy + radius,
            outline="blue",
            fill="cyan",
            stipple="gray25",
            width=2,
        )
        self.roi_listbox.insert("", "end", values=(roi_name,))

        self._stop_drawing()

    def _load_project_view(self):
        """
        Transitions from the welcome screen to the main control view and
        initializes the detector with the appropriate plugin.
        """
        # Reset analysis display state from single video workflow
        self.hide_progress_bar()
        self.analysis_status_var.set("Nenhuma análise em andamento.")
        if self.analysis_video_label:
            try:
                self.analysis_video_label.configure(image="")
                self._analysis_overlay_image = None
            except Exception:
                pass

        pm = self.controller.project_manager

        # Load persisted user preferences if present
        if pm.get_project_type() == "pre-recorded":
            if pm.project_data.get("last_processing_interval") is not None:
                try:
                    self.processing_interval_var.set(
                        str(int(pm.project_data["last_processing_interval"]))
                    )
                except (ValueError, TypeError):
                    pass
            if pm.project_data.get("last_show_preview") is not None:
                try:
                    self.show_preview_var.set(
                        bool(pm.project_data["last_show_preview"])  # type: ignore[arg-type]
                    )
                except Exception:
                    pass

            # Restore analysis and display intervals
            if pm.project_data.get("analysis_interval_frames") is not None:
                try:
                    self.analysis_interval_var.set(
                        str(int(pm.project_data["analysis_interval_frames"]))
                    )
                except (ValueError, TypeError):
                    pass
            if pm.project_data.get("display_interval_frames") is not None:
                try:
                    self.display_interval_var.set(
                        str(int(pm.project_data["display_interval_frames"]))
                    )
                except (ValueError, TypeError):
                    pass

        self._create_main_control_frame()

        project_type = pm.get_project_type()
        if project_type == "live":
            # Initial rendering of the progress grid
            self.root.after(100, self._render_progress_grid)

            # Only attempt to connect if a port is configured from the dialog
            if settings.arduino.port:
                if not self.controller.arduino.connect():
                    self.show_warning(
                        "Aviso do Arduino",
                        f"Não foi possível conectar ao Arduino na porta "
                        f"{settings.arduino.port}. Executando em modo offline.",
                    )
            try:
                self.controller.camera = Camera()
                self.controller.active_frame_source = self.controller.camera
                self.controller.detector.update_scaling(
                    self.controller.camera.actual_width,
                    self.controller.camera.actual_height,
                )
            except OSError as e:
                self.show_error("Erro na Câmera", str(e))
                self._create_welcome_frame()
                return
        elif project_type == "pre-recorded":
            self.update_reports_tree()
            self._populate_video_selector_tree()
            ready_message = f"Projeto: {pm.get_project_name()} - Pronto."
            self.set_status(ready_message)
            self._request_overview_refresh(reason=ready_message, append_summary=True)

        if project_type == "live":
            self.controller.capture_thread = threading.Thread(
                target=self._live_frame_capture_loop, name="CaptureThread", daemon=False
            )
            self.controller.processing_thread = threading.Thread(
                target=self._live_processing_loop, name="ProcessingThread", daemon=False
            )
            self.controller.capture_thread.start()
            self.controller.processing_thread.start()

            # Auto-calibration for Live projects when no zones are defined
            self.root.after(1000, self._check_live_project_calibration)

    def _create_progress_grid_tab(self):
        """Creates the tab for viewing the experimental progress grid."""
        self.progress_grid_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.progress_grid_frame, text="Progresso do Experimento")

        # This frame will hold the actual grid of buttons, which is rendered later
        self.grid_container = ttk.Frame(self.progress_grid_frame)
        self.grid_container.pack(expand=True, fill="both")

        # Add a refresh button
        refresh_button = ttk.Button(
            self.progress_grid_frame,
            text="Atualizar Grade",
            command=self._render_progress_grid,
        )
        refresh_button.pack(side="bottom", pady=10)

    def _check_live_project_calibration(self):
        """Checks if Live project needs calibration and prompts user automatically."""
        if self.controller.project_manager.get_project_type() != "live":
            return

        zone_data = self.controller.project_manager.get_zone_data()
        if not zone_data or not zone_data.polygon:
            log.info("ui.live_calibration.auto_prompt")

            response = self.ask_ok_cancel(
                "Calibração Automática",
                "Nenhuma arena principal foi definida para este projeto ao vivo.\n\n"
                "Deseja configurar a calibração automaticamente agora?\n\n"
                "• Será aberta a aba de Configuração de Zonas\n"
                "• Você pode usar 'Detectar Aquário (Auto)' ou desenhar manualmente\n"
                "• A configuração será salva automaticamente",
            )

            if response:
                log.info("ui.live_calibration.auto_accepted")
                # Switch to zone configuration tab
                if hasattr(self, "notebook") and hasattr(self, "zone_tab_frame"):
                    self.notebook.select(self.zone_tab_frame)

                # Show guidance message
                self.show_info(
                    "Configuração de Arena Principal",
                    "Configure a arena principal usando:\n\n"
                    "1. 'Detectar Aquário (Auto)' - Para detecção automática\n"
                    "2. 'Desenhar Polígono Principal' - Para desenho manual\n\n"
                    "A configuração será salva automaticamente.",
                )
            else:
                log.info("ui.live_calibration.auto_declined")

    def _render_progress_grid(self):
        """Clears and redraws the experimental progress grid based on project data."""
        # 1. Clear existing widgets
        for widget in self.grid_container.winfo_children():
            widget.destroy()

        # 2. Get project data from controller/project_manager
        pm = self.controller.project_manager
        if not pm or pm.get_project_type() != "live":
            return

        days = pm.project_data.get("experiment_days", 0)
        groups = pm.project_data.get("groups", [])
        subjects_per_group = pm.project_data.get("subjects_per_group", 0)

        if not all([days, groups, subjects_per_group]):
            ttk.Label(
                self.grid_container,
                text="O design experimental não está totalmente configurado.",
            ).pack()
            return

        completed_sessions = pm.get_completed_sessions()

        # 3. Create headers
        ttk.Label(self.grid_container, text="Dia/Grupo", font=("Helvetica", 10, "bold")).grid(
            row=0, column=0, padx=5, pady=5, sticky="nsew"
        )
        for j, group_name in enumerate(groups):
            ttk.Label(
                self.grid_container,
                text=group_name,
                font=("Helvetica", 10, "bold"),
                anchor="center",
            ).grid(row=0, column=j + 1, padx=5, pady=5, sticky="nsew")

        # 4. Create grid cells
        for i in range(days):
            day = i + 1
            day_title = self._build_day_title(day)
            ttk.Label(
                self.grid_container,
                text=day_title,
                font=("Helvetica", 10, "bold"),
            ).grid(row=i + 1, column=0, padx=5, pady=5, sticky="nsew")

            for j, group_name in enumerate(groups):
                completed_count = sum(
                    1 for (d, g, s) in completed_sessions if d == day and g == group_name
                )

                status_text = f"{completed_count}/{subjects_per_group}"

                if completed_count == 0:
                    color = "#E0E0E0"  # Grey - Pending
                elif completed_count < subjects_per_group:
                    color = "#FFFACD"  # LemonChiffon - In progress
                else:
                    color = "#90EE90"  # LightGreen - Completed

                cell_btn = Button(
                    self.grid_container,
                    text=status_text,
                    background=color,
                    width=15,
                    height=3,
                    command=lambda d=day, g=group_name: self._on_grid_cell_clicked(d, g),
                )
                cell_btn.grid(row=i + 1, column=j + 1, padx=2, pady=2, sticky="nsew")

        for col_index in range(len(groups) + 1):
            self.grid_container.columnconfigure(col_index, weight=1)
        for row_index in range(days + 1):
            self.grid_container.rowconfigure(row_index, weight=1)

    def _on_grid_cell_clicked(self, day, group_name):
        pm = self.controller.project_manager
        subjects_per_group = pm.project_data.get("subjects_per_group", 0)
        completed_sessions = pm.get_completed_sessions()

        completed_subjects = {s for (d, g, s) in completed_sessions if d == day and g == group_name}

        dialog = SubjectSelectionDialog(
            self.root, day, group_name, subjects_per_group, completed_subjects
        )

        if dialog.result:
            subject_id = dialog.result
            self.controller.start_recording(day=day, group=group_name, cobaia=str(subject_id))
            self._render_progress_grid()  # Refresh grid after starting a recording

    def _live_frame_capture_loop(self):
        """
        Loop to capture frames from a LIVE source (camera).
        """
        live_frame_count = 0
        while not self.controller.program_exit_event.is_set():
            if not self.controller.active_frame_source:
                time.sleep(0.1)
                continue

            ret, frame = self.controller.active_frame_source.get_frame()
            if not ret:
                log.error("gui.capture_thread.get_frame_failed")
                time.sleep(0.5)
                continue

            live_frame_count += 1

            if not self.controller.frame_queue.full():
                self.controller.frame_queue.put((live_frame_count, frame.copy()))
            if self.controller.is_capturing_for_video and not self.controller.video_queue.full():
                self.controller.video_queue.put(frame.copy())

            time.sleep(1 / (settings.video_processing.fps * 1.5))

    def _live_processing_loop(self):
        """
        Loop to process frames from a LIVE source.
        """
        while not self.controller.program_exit_event.is_set():
            try:
                frame_number, frame = self.controller.frame_queue.get(timeout=1)
            except queue.Empty:
                continue

            if self.controller.is_processing:
                # Apply perspective warp if calibration data is available
                calib_data = self.controller.project_manager.project_data.get("calibration", {})
                h_matrix = calib_data.get("homography_matrix")
                target_dims = calib_data.get("target_dims_px")

                if h_matrix and target_dims:
                    import numpy as np

                    h_matrix = np.array(h_matrix)
                    frame = cv2.warpPerspective(frame, h_matrix, tuple(target_dims))

                detections, command = self.controller.detector.process_frame(frame, "live")
                if command is not None:
                    self.controller.arduino.send_command(command)
                if self.controller.is_recording and detections:
                    timestamp = time.time() - self.controller.recorder.start_time
                    self.controller.recorder.write_detection_data(
                        timestamp, frame_number, detections
                    )
                self.controller.detector.draw_overlay(frame, detections)

            cv2.imshow("Live View", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                self.controller.on_close()
                break
        cv2.destroyAllWindows()
        log.info("gui.live_processing_loop.finished")

    def _load_new_weight_clicked(self):
        """Handles the 'Load New Weight' button click."""
        filepath = filedialog.askopenfilename(
            title="Selecione um arquivo de peso .pt",
            filetypes=[("Pesos PyTorch", "*.pt")],
        )
        if not filepath:
            return

        # Classify weight type by filename
        filename = os.path.basename(filepath)
        weight_type = self.controller.classify_weight_type(filename)

        # If type cannot be determined, ask user
        if weight_type is None:
            weight_type = self._prompt_for_weight_type()
            if weight_type is None:  # User cancelled
                return

        # Ask user what to do with the new weight
        choice = messagebox.askquestion(
            "Adicionar Peso",
            f"Deseja definir este novo peso {weight_type} como padrão para seu tipo?",
            icon="question",
            type="yesnocancel",
        )

        if choice == "cancel":
            return
        elif choice == "yes":
            # Add as new default for this type
            self.publish_event(
                Events.MODEL_ADD_WEIGHT,
                {"path": filepath, "set_as_default": True, "weight_type": weight_type},
            )
        else:  # 'no'
            # Add as an alternative
            self.publish_event(
                Events.MODEL_ADD_WEIGHT,
                {"path": filepath, "set_as_default": False, "weight_type": weight_type},
            )

    def _prompt_for_weight_type(self):
        """Prompts user to select weight type when it cannot be determined
        from filename."""
        from tkinter import Radiobutton, Toplevel

        dialog = Toplevel(self.root)
        dialog.title("Tipo de Peso")
        dialog.geometry("300x150")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        # Center dialog
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (300 // 2)
        y = (self.root.winfo_screenheight() // 2) - (150 // 2)
        dialog.geometry(f"+{x}+{y}")

        Label(dialog, text="Selecione o tipo de modelo:").pack(pady=10)

        weight_type_var = StringVar(value="seg")

        Radiobutton(
            dialog,
            text="Segmentação (para máscaras e bordas precisas)",
            variable=weight_type_var,
            value="seg",
        ).pack(anchor="w", padx=20)

        Radiobutton(
            dialog,
            text="Detecção (para caixas delimitadoras rápidas)",
            variable=weight_type_var,
            value="det",
        ).pack(anchor="w", padx=20)

        result = [None]  # Use list to allow modification in nested function

        def on_ok():
            result[0] = weight_type_var.get()
            dialog.destroy()

        def on_cancel():
            result[0] = None
            dialog.destroy()

        button_frame = Frame(dialog)
        button_frame.pack(pady=20)

        Button(button_frame, text="OK", command=on_ok).pack(side="left", padx=5)
        Button(button_frame, text="Cancelar", command=on_cancel).pack(side="left", padx=5)

        dialog.wait_window()
        return result[0]

    def _manage_weights_clicked(self):
        """Opens the weight management dialog."""
        ManageWeightsDialog(self.root, self.controller)

    def update_weights_dropdown(self, weights: list[str]):
        """Caches available weights so summaries stay consistent."""
        self._available_weight_names = list(weights or [])
        if (
            self.controller.active_weight_name
            and self.controller.active_weight_name in self._available_weight_names
        ):
            self._update_active_weight_display(self.controller.active_weight_name)
        elif not self._available_weight_names:
            self._update_active_weight_display("")

    def set_active_weight_in_dropdown(self, weight_name: str | None):
        """Updates the active weight summary."""
        self._update_active_weight_display(weight_name or "")

    def update_openvino_checkbox(self, enabled: bool):
        """Synchronizes OpenVINO toggle state with the summary label."""
        self._openvino_enabled = bool(enabled)
        self._refresh_openvino_summary()

    def update_openvino_status_display(self, status: str):
        """Updates the detailed OpenVINO status shown in the UI."""
        self._openvino_status_message = status or ""
        self._refresh_openvino_summary()

    def _refresh_openvino_summary(self):
        state_text = "Ativado" if self._openvino_enabled else "Desativado"
        status_text = self._openvino_status_message.strip()
        if status_text:
            self._openvino_display_var.set(f"OpenVINO: {state_text} — {status_text}")
        else:
            self._openvino_display_var.set(f"OpenVINO: {state_text}")

    def _update_active_weight_display(self, weight_name: str):
        if weight_name:
            self._active_weight_display_var.set(f"Peso ativo: {weight_name}")
        else:
            self._active_weight_display_var.set("Peso ativo: Nenhum peso selecionado.")

    def _create_project_workflow(self):
        """
        Handles the UI part of creating a new project by opening a comprehensive dialog,
        then calls the controller with the collected data.
        """
        # Always use the wizard (v1.6+, wizard is now permanent)
        from zebtrack.ui.wizard import (
            WizardDialog,
            adapt_wizard_data_to_controller_format,
        )

        wizard = WizardDialog(self.root)
        if not wizard.result:
            return  # User cancelled

        # Adapt wizard output to controller format
        try:
            controller_data = adapt_wizard_data_to_controller_format(wizard.result)
        except ValueError as e:
            self.show_error("Erro no Wizard", f"Erro ao processar dados do wizard: {e}")
            return

        # Call controller with adapted data via event
        self.publish_event(Events.PROJECT_CREATE, controller_data)

    def _open_project_workflow(self):
        """Handles the UI part of opening a project, then calls the controller."""
        project_path = self.ask_directory(title="Selecione uma Pasta de Projeto Existente")
        if not project_path:
            return

        self.publish_event(Events.PROJECT_OPEN, {"project_path": project_path})

    def _on_analyze_single_video_clicked(self):
        """Handles the UI part of the single video workflow."""
        dialog = SingleVideoConfigDialog(self.root)
        if not dialog.result:
            return  # User cancelled

        video_path = self.ask_open_filenames(
            "Selecione um Único Arquivo de Vídeo",
            [("Arquivos de vídeo", "*.mp4 *.avi *.mov")],
        )
        if not video_path:
            return

        # Pass both config and video path to the controller via event
        self.publish_event(
            Events.VIDEO_ANALYZE_SINGLE,
            {
                "video_path": video_path[0],
                "config": dialog.result,
            },
        )

    def setup_zone_definition_for_single_video(self, video_path: str, config: dict):
        """Prepares and displays the zone configuration tab for a single video."""
        # Reset analysis UI elements for a clean setup
        self.hide_progress_bar()
        self.analysis_status_var.set("Nenhuma análise em andamento.")
        if self.analysis_video_label:
            try:
                self.analysis_video_label.configure(image="")
                self._analysis_overlay_image = None
            except Exception:
                pass

        self.pending_single_video_path = video_path
        self.pending_single_video_config = config

        # Ensure zone edits persist under the selected video
        self.controller.project_manager.set_active_zone_video(video_path)

        # Open the main project view if it is not already open
        if not self.notebook:
            self._create_main_control_frame()

        self.display_roi_video_frame(video_path)
        self.notebook.select(self.zone_tab_frame)

        # Clear template selection for single video workflow - user should
        # explicitly choose if they want to apply a template
        self._refresh_roi_templates(clear_selection=True)

        # Add a "Start Analysis" button specific to this flow
        if not self.start_single_analysis_btn:
            self.start_single_analysis_btn = ttk.Button(
                self.fixed_button_frame,  # Add to the fixed button frame at bottom
                text="Iniciar Análise de Vídeo Único",
                command=self._on_start_single_video_processing_clicked,
            )
            self.start_single_analysis_btn.pack(side="bottom", fill="x", pady=5)
        self.start_single_analysis_btn.config(state="normal")

        self.show_info(
            "Configuração Necessária",
            "Defina a arena do aquário usando a detecção automática ou o "
            "desenho manual.\n\n"
            "Após definir a arena principal, clique em 'Iniciar Análise de "
            "Vídeo Único'.",
        )

    def _on_auto_detect_clicked(self):
        """Handler for the auto-detect button."""
        # Prevent editing during analysis
        if self.analysis_active:
            self.show_warning(
                "Análise em Progresso",
                "Não é possível detectar zonas durante a análise de vídeo.",
            )
            return

        try:
            stabilization_frames = int(self.stabilization_frames_var.get())
            if stabilization_frames <= 0:
                self.show_warning("Entrada Inválida", "O número de frames deve ser positivo.")
                return
        except (ValueError, TypeError):
            self.show_warning(
                "Entrada Inválida",
                "O número de frames para análise deve ser um número inteiro.",
            )
            return

        # Clear any old interactive polygon before starting a new detection
        self._clear_interactive_polygon()

        if self.pending_single_video_path:
            # Single video flow
            self.controller.run_aquarium_detection(
                video_path=self.pending_single_video_path,
                stabilization_frames=stabilization_frames,
            )
        else:
            # Project flow
            self.controller.run_aquarium_detection(stabilization_frames=stabilization_frames)

    def _on_start_single_video_processing_clicked(self):
        """Handler for the 'Start Analysis' button in the single video flow."""
        # If the user was editing a polygon, prompt for confirmation before saving.
        if self.edited_polygon_points:
            response = messagebox.askyesnocancel(
                "Salvar Polígono?",
                "Você deseja salvar as alterações no polígono antes de iniciar a "
                "análise?\n\n"
                "Sim: Salvar e iniciar análise\n"
                "Não: Descartar alterações e iniciar análise\n"
                "Cancelar: Voltar para edição",
            )
            if response is None:
                # Cancel pressed, abort analysis
                return
            elif response:
                # Yes pressed, save polygon
                self.controller.save_manual_arena(self.edited_polygon_points)
                self._clear_interactive_polygon()
            else:
                # No pressed, discard changes
                self._clear_interactive_polygon()

        # 1. Get the zone data that the user drew
        zone_data = self.controller.project_manager.get_zone_data()
        if not zone_data.polygon:
            self.show_error("Erro", "A área principal do aquário (polígono) não foi definida.")
            return

        # 2. Disable the button
        self.start_single_analysis_btn.config(state="disabled")
        self.controller.start_single_video_processing(
            self.pending_single_video_path,
            self.pending_single_video_config,
            zone_data,
        )
        # Clear the pending state
        self.pending_single_video_path = None
        self.pending_single_video_config = None

    def _on_close(self):
        """Delegates the close action to the controller."""
        self.controller.on_close()

    def _join_threads(self):
        """Delegates thread joining to the controller."""
        self.controller.join_threads()

    def set_status(self, text):
        """Updates the UI status bar."""
        self.status_var.set(text)

    def show_progress_bar(self):
        """Shows the progress bar frame and cancel button."""
        if self.progress_frame and not self.progress_frame.winfo_viewable():
            # Pack progress_frame BEFORE video_container to ensure it stays visible
            if hasattr(self, "video_container") and self.video_container:
                self.progress_frame.pack(before=self.video_container, pady=5, fill="x", padx=10)
            else:
                self.progress_frame.pack(pady=5, fill="x", padx=10)
            self.progress_bar["value"] = 0
        if self.cancel_proc_btn:
            self.cancel_proc_btn.config(state="normal")

    def update_progress(self, value):
        """Updates the progress bar."""
        if self.progress_bar:
            self.progress_bar["value"] = value * 100  # Convert fraction to percentage
            self.update_idletasks()

    def update_idletasks(self):
        """Force the GUI to update, processing pending events."""
        self.root.update_idletasks()

    def update_progress_stats(
        self,
        *,
        total=None,
        processed=None,
        detected=None,
        percent=None,
        elapsed=None,
        eta=None,
    ):
        """Update textual statistics for file processing."""
        if not self.progress_labels:
            return
        if total is not None:
            self.progress_labels["total"].set(str(total))
        if processed is not None:
            self.progress_labels["processed"].set(str(processed))
        if detected is not None:
            self.progress_labels["detected"].set(str(detected))
        if percent is not None:
            self.progress_labels["percent"].set(f"{percent:.1f}%")
        if elapsed is not None:
            self.progress_labels["elapsed"].set(self._format_time(elapsed))
        if eta is not None:
            self.progress_labels["eta"].set(self._format_time(eta) if eta >= 0 else "-")

    def hide_progress_bar(self):
        """Hides the progress bar and cancel button, and resets its value."""
        if self.progress_frame and self.progress_frame.winfo_viewable():
            self.progress_frame.pack_forget()
            self.progress_bar["value"] = 0
        if self.cancel_proc_btn:
            self.cancel_proc_btn.config(state="disabled")

    def _draw_zones_on_frame(self, frame):
        """Desenha a arena e as ROIs salvas no frame de vídeo."""
        zone_data = self.controller.project_manager.get_zone_data()
        if zone_data.polygon:
            pts = np.array(zone_data.polygon, np.int32)
            pts = pts.reshape((-1, 1, 2))
            cv2.polylines(
                frame, [pts], isClosed=True, color=(0, 255, 255), thickness=2
            )  # Yellow for the main arena

        for i, polygon in enumerate(zone_data.roi_polygons):
            color = (
                zone_data.roi_colors[i] if i < len(zone_data.roi_colors) else (0, 255, 0)
            )  # Default to green
            pts = np.array(polygon, np.int32)
            pts = pts.reshape((-1, 1, 2))
            cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=2)
        return frame

    def display_frame(self, frame):
        """Display a video frame inside the GUI, with overlays."""
        # If analysis is active, route to analysis display
        if self.analysis_active:
            self.display_analysis_frame(frame)
            return

        try:
            # Original behavior for non-analysis display
            # Desenha as zonas antes de exibir
            frame_with_zones = self._draw_zones_on_frame(frame.copy())

            # Converte e embute
            frame_rgb = cv2.cvtColor(frame_with_zones, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)
            imgtk = ImageTk.PhotoImage(image=img)
            if self.video_label:
                self.video_label.configure(image=imgtk)
                self.video_label.image = imgtk  # keep reference
        except Exception:
            # Fallback to OpenCV window if Pillow not installed or other error
            try:
                cv2.imshow("Preview", frame)
                cv2.waitKey(1)
            except Exception:
                pass

    def _toggle_canvas_view(self):
        """Toggle between zone drawing view and analysis progress view."""
        if not self.notebook or not self.analysis_tab_frame or not self.zone_tab_frame:
            return

        current_tab = self.notebook.select()
        analysis_tab_id = str(self.analysis_tab_frame)

        if current_tab != analysis_tab_id:
            self._switch_to_analysis_view()
        else:
            self._switch_to_zones_view()

    def _switch_to_analysis_view(self):
        """Switch to analysis progress view."""
        if not self.notebook or not self.analysis_tab_frame:
            return

        self.canvas_view_mode = "analysis"
        self.notebook.select(self.analysis_tab_frame)

        if self.toggle_view_btn:
            self.toggle_view_btn.config(text="Ver Configuração de Zonas")

    def _switch_to_zones_view(self):
        """Switch to zone drawing view."""
        if not self.notebook or not self.zone_tab_frame:
            return

        self.canvas_view_mode = "zones"
        self.notebook.select(self.zone_tab_frame)

        if self.toggle_view_btn:
            self.toggle_view_btn.config(text="Ver Análise em Progresso")

    def start_analysis_view_mode(self):
        """Called when analysis starts - immediately switch to analysis view and
        enable toggle."""
        self.analysis_active = True
        self.analysis_status_var.set("Preparando análise...")
        if self.analysis_task_var is not None:
            self.analysis_task_var.set("Preparando fila de análise...")
        self._set_analysis_metadata_defaults()
        self._reset_analysis_controls()
        self.show_progress_bar()
        if self.toggle_view_btn:
            self.toggle_view_btn.config(state="normal")
        if self.cancel_proc_btn:
            self.cancel_proc_btn.config(state="normal")
        self._switch_to_analysis_view()

    def stop_analysis_view_mode(self):
        """Called when analysis stops - disable toggle and return to zones view."""
        self.analysis_active = False
        if self.toggle_view_btn:
            self.toggle_view_btn.config(state="disabled")
        if self.cancel_proc_btn:
            self.cancel_proc_btn.config(state="disabled")
        self.hide_progress_bar()
        self.analysis_status_var.set("Nenhuma análise em andamento.")
        if self.analysis_task_var is not None:
            self.analysis_task_var.set(self._default_analysis_task_text())
        self._set_analysis_metadata_defaults()
        self._reset_analysis_controls()
        self._switch_to_zones_view()

    def display_analysis_frame(self, frame):
        """Display analysis frame in the overlay instead of separate progress bar."""
        try:
            self._last_analysis_frame = frame.copy()
            self._render_last_analysis_frame()
        except Exception:
            # Fallback to OpenCV window if Pillow not installed or other error
            try:
                cv2.imshow("Preview", frame)
                cv2.waitKey(1)
            except Exception:
                pass

    def update_detection_overlay(
        self,
        detections: list[tuple],
        report: ProcessingReport | None = None,
    ) -> None:
        """Receive the latest detection batch for track selection overlays."""
        if detections is None:
            detections = []

        mode = report.mode if report else self._active_processing_mode
        self._current_detections = list(detections)

        if self.track_selector_widget:
            state = "disabled" if mode is ProcessingMode.SINGLE_SUBJECT else "readonly"
            self.track_selector_widget.configure(state=state)

        if mode is ProcessingMode.SINGLE_SUBJECT:
            self.track_selector_var.set("Todos")
            self._update_track_options(["Todos"])
        else:
            options = self._build_track_options(self._current_detections)
            self._update_track_options(options)

        if self._last_analysis_frame is not None:
            self._render_last_analysis_frame()

    def update_processing_mode(self, report: ProcessingReport | None) -> None:
        """Update the UI to reflect the active tracking pipeline."""

        if report is None:
            return

        previous_mode = self._active_processing_mode
        mode = report.mode
        self._active_processing_mode = mode

        self.tracking_mode_var.set(f"Modo de rastreamento: {mode.display_name}")

        if not self.track_selector_widget:
            return

        state = "disabled" if mode is ProcessingMode.SINGLE_SUBJECT else "readonly"
        self.track_selector_widget.configure(state=state)

        if mode is ProcessingMode.SINGLE_SUBJECT:
            self.track_selector_var.set("Todos")
            self._update_track_options(["Todos"])
        elif previous_mode is ProcessingMode.SINGLE_SUBJECT:
            options = self._build_track_options(self._current_detections)
            self._update_track_options(options)

    def update_analysis_profile(self, profile_name: str) -> None:
        """Update the label describing the active analysis profile."""
        text = (profile_name or "default").strip() or "default"
        self.analysis_profile_var.set(f"Perfil de análise: {text}")
        self._reset_analysis_controls()

    def update_social_summary(
        self,
        *,
        profile: str,
        stats: dict | None,
        tracks: list[str] | None,
    ) -> None:
        """Display aggregated social proximity statistics for the active video."""
        if stats and isinstance(stats, dict):
            percentages = stats.get("social_time_percentage") or {}
            if isinstance(percentages, dict) and percentages:
                formatted = []
                for key, value in sorted(
                    percentages.items(),
                    key=lambda item: str(item[0]),
                ):
                    if isinstance(value, (int, float)):
                        formatted.append(f"ID {key}: {value:.1f}%")
                if formatted:
                    self.social_summary_var.set("Interações sociais: " + ", ".join(formatted))
                else:
                    self.social_summary_var.set(
                        "Interações sociais: nenhum agrupamento registrado."
                    )
            else:
                self.social_summary_var.set("Interações sociais: nenhum agrupamento registrado.")
        else:
            self.social_summary_var.set("Interações sociais: aguardando dados.")

        if tracks and self._active_processing_mode is not ProcessingMode.SINGLE_SUBJECT:
            normalized_tracks = [str(track).strip() for track in tracks if str(track).strip()]
            if normalized_tracks:
                self._update_track_options(["Todos", *normalized_tracks])

    def _reset_analysis_controls(self) -> None:
        """Reset track selector state and cached frames."""
        self._current_detections = []
        self._last_analysis_frame = None
        self._analysis_overlay_image = None
        self.track_selector_var.set("Todos")
        self._update_track_options(["Todos"])
        if self.track_selector_widget:
            state = (
                "disabled"
                if self._active_processing_mode is ProcessingMode.SINGLE_SUBJECT
                else "readonly"
            )
            self.track_selector_widget.configure(state=state)

    def _build_track_options(self, detections: list[tuple]) -> list[str]:
        observed: set[str] = set()
        for det in detections:
            if len(det) < 6:
                continue
            track_id = det[5]
            if track_id is None:
                continue
            text = str(track_id).strip()
            if text:
                observed.add(text)

        ordered = sorted(observed, key=str)
        return ["Todos", *ordered]

    def _update_track_options(self, options: list[str]) -> None:
        cleaned: list[str] = []
        seen: set[str] = set()
        for option in options:
            option_str = str(option).strip() or "Todos"
            if option_str not in seen:
                cleaned.append(option_str)
                seen.add(option_str)

        if not cleaned:
            cleaned = ["Todos"]

        normalized = tuple(cleaned)
        if normalized == self._available_track_options:
            return

        self._available_track_options = normalized
        if self.track_selector_widget:
            self.track_selector_widget.configure(values=list(normalized))

        if self.track_selector_var.get() not in normalized:
            self.track_selector_var.set(normalized[0] if normalized else "Todos")

    def _on_track_selection_changed(self, _event=None) -> None:
        self._render_last_analysis_frame()

    def _render_last_analysis_frame(self) -> None:
        if self._last_analysis_frame is None:
            return
        frame = self._annotate_selected_tracks(self._last_analysis_frame.copy())
        self._show_analysis_frame_image(frame)

    def _annotate_selected_tracks(self, frame):
        selected = self.track_selector_var.get() if hasattr(self, "track_selector_var") else "Todos"
        selected = str(selected).strip()
        if not selected or selected.lower() == "todos":
            return frame

        for det in self._current_detections:
            if len(det) < 6:
                continue
            x1, y1, x2, y2, _, track_id = det
            if track_id is None or str(track_id).strip() != selected:
                continue
            try:
                x1, y1, x2, y2 = map(int, (x1, y1, x2, y2))
            except (TypeError, ValueError):
                continue
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 215, 255), 3)
            cv2.putText(
                frame,
                f"ID {track_id}",
                (x1, max(y1 - 8, 12)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 215, 255),
                2,
            )

        return frame

    def _show_analysis_frame_image(self, frame) -> None:
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)
        label = getattr(self, "analysis_video_label", None)

        available_width = None
        available_height = None

        if label is not None and hasattr(label, "winfo_width"):
            label_width = label.winfo_width()
            label_height = label.winfo_height()

            if isinstance(label_width, (int, float)) and isinstance(label_height, (int, float)):
                available_width = label_width
                available_height = label_height

            if (available_width is None or available_height is None) and hasattr(
                label, "update_idletasks"
            ):
                label.update_idletasks()
                label_width = label.winfo_width()
                label_height = label.winfo_height()
                if isinstance(label_width, (int, float)) and isinstance(label_height, (int, float)):
                    available_width = label_width
                    available_height = label_height

        if (available_width is None or available_height is None) and hasattr(
            self, "video_container"
        ):
            container = self.video_container
            if hasattr(container, "winfo_width"):
                if hasattr(container, "update_idletasks"):
                    container.update_idletasks()
                container_width = container.winfo_width()
                container_height = container.winfo_height()
                if isinstance(container_width, (int, float)) and isinstance(
                    container_height, (int, float)
                ):
                    available_width = available_width or container_width
                    available_height = available_height or container_height

        if (
            isinstance(available_width, (int, float))
            and isinstance(available_height, (int, float))
            and available_width > 1
            and available_height > 1
        ):
            scale = min(available_width / img.width, available_height / img.height, 1.0)
            if scale < 1.0:
                resample_attr = getattr(Image, "Resampling", None)
                if resample_attr is not None:
                    resample = getattr(
                        resample_attr,
                        "LANCZOS",
                        getattr(
                            resample_attr,
                            "BICUBIC",
                            getattr(resample_attr, "BILINEAR", 0),
                        ),
                    )
                else:
                    resample = getattr(
                        Image,
                        "LANCZOS",
                        getattr(Image, "BICUBIC", getattr(Image, "BILINEAR", 0)),
                    )
                new_size = (
                    max(1, int(img.width * scale)),
                    max(1, int(img.height * scale)),
                )
                img = img.resize(new_size, resample=resample)

        imgtk = ImageTk.PhotoImage(image=img)
        self._analysis_overlay_image = imgtk
        if label is not None:
            label.configure(image=imgtk)
            label.image = imgtk

    def update_analysis_progress(self, value, status_text=None):
        """Update progress bar and status in the analysis overlay."""
        if self.progress_bar:
            self.progress_bar["value"] = value * 100
        if status_text:
            self.analysis_status_var.set(status_text)
        self.update_idletasks()

    def update_processing_stats(
        self,
        total_frames=None,
        processed_frames=None,
        detected_frames=None,
        start_time=None,
        current_frame=None,
    ):
        """Update processing statistics in real-time during video analysis."""
        if not self.progress_labels:
            return

        # Update frame counters in all label sets
        labels = self.progress_labels
        if total_frames is not None:
            labels["total"].set(str(total_frames))
        if processed_frames is not None:
            labels["processed"].set(str(processed_frames))
        if detected_frames is not None:
            labels["detected"].set(str(detected_frames))

        # Calculate and update percentage based on actual frame position
        if total_frames:
            frame_for_percent = current_frame if current_frame is not None else processed_frames
            if frame_for_percent is not None:
                percent = (frame_for_percent / total_frames) * 100
                labels["percent"].set(f"{percent:.1f}%")

        # Calculate elapsed time and ETA
        if start_time:
            import time

            elapsed = time.time() - start_time
            labels["elapsed"].set(self._format_time(elapsed))

            frame_for_eta = current_frame if current_frame is not None else processed_frames
            if frame_for_eta and total_frames and frame_for_eta > 0:
                rate = frame_for_eta / elapsed
                remaining_frames = total_frames - frame_for_eta
                if rate > 0:
                    eta = remaining_frames / rate
                    labels["eta"].set(self._format_time(eta))
                else:
                    labels["eta"].set("-")

    def update_analysis_metadata(self, *, metadata: dict | None) -> None:
        """Update the metadata display for the currently processed video."""
        metadata = metadata or {}
        group_display = self._resolve_group_display(metadata)
        day_display = self._resolve_day_display(metadata)
        subject_display = self._resolve_subject_display(metadata)

        self._apply_analysis_metadata_strings(
            group_display,
            day_display,
            subject_display,
        )

    def update_analysis_task_status(
        self,
        *,
        index: int,
        total: int,
        experiment_id: str | None = None,
        step: str | None = None,
    ) -> None:
        """Update the task summary indicating which video is being processed."""
        if not hasattr(self, "analysis_task_var") or self.analysis_task_var is None:
            return

        total_videos = max(int(total) if total is not None else 0, 1)
        current_index = max(int(index) if index is not None else 0, 0) + 1

        parts: list[str] = [f"Vídeo {current_index} de {total_videos}"]

        if experiment_id:
            exp_text = str(experiment_id).strip()
            if exp_text:
                parts.append(f"— {exp_text}")

        if step:
            step_text = str(step).strip()
            if step_text:
                if step_text.lower().startswith("etapa:"):
                    step_text = step_text[6:].strip()
                if step_text:
                    parts.append(f"• {step_text}")

        self.analysis_task_var.set(" ".join(parts))

    @staticmethod
    def _analysis_metadata_defaults() -> tuple[str, str, str]:
        return ("Sem Grupo", "Sem Dia", "Não informado")

    @classmethod
    def _default_analysis_metadata_text(cls) -> str:
        group, day, subject = cls._analysis_metadata_defaults()
        return f"Grupo: {group} | Dia: {day} | Indivíduo: {subject}"

    def _set_analysis_metadata_defaults(self) -> None:
        group, day, subject = self._analysis_metadata_defaults()
        self._apply_analysis_metadata_strings(group, day, subject)

    def _apply_analysis_metadata_strings(
        self,
        group: str,
        day: str,
        subject: str,
    ) -> None:
        combined = f"Grupo: {group} | Dia: {day} | Indivíduo: {subject}"

        if getattr(self, "analysis_metadata_var", None) is not None:
            self.analysis_metadata_var.set(combined)

        if getattr(self, "analysis_group_var", None) is not None:
            self.analysis_group_var.set(f"Grupo: {group}")

        if getattr(self, "analysis_day_var", None) is not None:
            self.analysis_day_var.set(f"Dia: {day}")

        if getattr(self, "analysis_subject_var", None) is not None:
            self.analysis_subject_var.set(f"Indivíduo: {subject}")

    @staticmethod
    def _default_analysis_task_text() -> str:
        return "Nenhuma tarefa em andamento."

    def _resolve_group_display(self, metadata: dict) -> str:
        for key in (
            "group_display_name",
            "group_label",
            "group_name",
            "group_id",
            "group",
        ):
            value = metadata.get(key)
            if value not in (None, "", "None"):
                text = str(value).strip()
                if text:
                    return text
        return "Sem Grupo"

    def _resolve_day_display(self, metadata: dict) -> str:
        for key in ("day_label", "day_display_name"):
            value = metadata.get(key)
            if value not in (None, "", "None"):
                text = str(value).strip()
                if text:
                    return text if text.lower().startswith("dia") else f"Dia {text}"

        for key in ("day", "day_id", "dia"):
            value = metadata.get(key)
            if value not in (None, "", "None"):
                formatted = self._format_day_display(value)
                if formatted.lower() == "sem dia":
                    return "Sem Dia"
                return f"Dia {formatted}"

        return "Sem Dia"

    def _resolve_subject_display(self, metadata: dict) -> str:
        for key in (
            "subject_label",
            "subject_display_name",
            "subject",
            "subject_id",
            "animal",
            "animal_id",
            "individual",
            "individuo",
            "cobaia",
        ):
            value = metadata.get(key)
            if value in (None, "", "None"):
                continue

            if isinstance(value, bool):
                text = str(value).strip()
                if text:
                    return text

            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if float(value).is_integer():
                    return f"{int(value):02d}"
                return str(value)

            text = str(value).strip()
            if not text:
                continue
            if text.isdigit():
                return f"{int(text):02d}"
            return text

        return "Não informado"

    @staticmethod
    def _format_time(seconds: float) -> str:
        if seconds is None or seconds < 0:
            return "-"
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h:d}h {m:02d}m {s:02d}s"
        if m:
            return f"{m:d}m {s:02d}s"
        return f"{s:d}s"

    def show_error(self, title, message):
        """Shows an error message box."""
        messagebox.showerror(title, message)

    def show_warning(self, title, message):
        """Shows a warning message box."""
        messagebox.showwarning(title, message)

    def show_info(self, title, message):
        """Shows an info message box."""
        messagebox.showinfo(title, message)

    def show_pending_videos_dialog(
        self,
        *,
        ready_with_trajectory: list[dict],
        ready_with_zones: list[dict],
        arena_only: list[dict],
        without_arena: list[dict],
    ) -> dict | None:
        """Exibe o diálogo hierárquico de vídeos pendentes."""

        self.apply_pending_readiness_snapshot(
            ready_with_trajectory=ready_with_trajectory,
            ready_with_zones=ready_with_zones,
            arena_only=arena_only,
            without_arena=without_arena,
        )

        dialog = PendingVideosDialog(
            self.root,
            hierarchy_builder=self._build_video_hierarchy_snapshot,
            ready_with_trajectory=ready_with_trajectory,
            ready_with_zones=ready_with_zones,
            arena_only=arena_only,
            without_arena=without_arena,
        )

        return dialog.result

    def ask_ok_cancel(self, title, message):
        """Shows a confirmation dialog."""
        return messagebox.askokcancel(title, message)

    def ask_string(self, title, prompt, initialvalue=None):
        """Shows a dialog for string input."""
        return simpledialog.askstring(title, prompt, initialvalue=initialvalue)

    def ask_directory(self, title):
        """Shows a dialog to select a directory."""
        return filedialog.askdirectory(title=title)

    def ask_open_filenames(self, title, filetypes):
        """Shows a dialog to select one or more files."""
        return filedialog.askopenfilenames(title=title, filetypes=filetypes)

    def _create_roi_context_menu(self):
        """Cria menu de contexto para ROIs"""
        from tkinter import Menu

        self.roi_context_menu = Menu(self.root, tearoff=0)
        self.roi_context_menu.add_command(
            label="🔧 Editar Vértices", command=self._edit_selected_zone_vertices
        )
        self.roi_context_menu.add_separator()
        self.roi_context_menu.add_command(label="✏️ Renomear", command=self._rename_selected_roi)
        self.roi_context_menu.add_command(label="🎨 Mudar Cor", command=self._change_roi_color)
        self.roi_context_menu.add_separator()
        self.roi_context_menu.add_command(
            label="🗑️ Remover", command=self._remove_selected_roi_confirm
        )

    def _on_zone_double_click(self, event):
        """Handle double-click on zone list - opens vertex editing mode."""
        self._edit_selected_zone_vertices()

    def _on_zone_right_click(self, event):
        """Mostra menu de contexto"""
        # Seleciona item sob o cursor
        item = self.zone_listbox.identify_row(event.y)
        if item:
            self.zone_listbox.selection_set(item)

            # Verifica se é ROI (não arena principal)
            values = self.zone_listbox.item(item)["values"]
            if values and "Arena Principal" not in values[0]:
                # ROI - show full menu
                self.roi_context_menu.post(event.x_root, event.y_root)
            elif values and "Arena Principal" in values[0]:
                # Arena Principal - show limited menu (only edit vertices)
                arena_menu = Menu(self.root, tearoff=0)
                arena_menu.add_command(
                    label="🔧 Editar Vértices",
                    command=self._edit_selected_zone_vertices,
                )
                arena_menu.post(event.x_root, event.y_root)

    def _edit_selected_zone_vertices(self):
        """Enables interactive editing of the selected zone's vertices."""
        selected = self.zone_listbox.selection()
        if not selected:
            return

        item = self.zone_listbox.item(selected[0])
        zone_name = item["values"][0]

        # Check if we are already in drawing mode
        if self.drawing_mode is not None:
            self.show_warning(
                "Modo de Desenho Ativo",
                "Finalize o desenho atual antes de editar vértices de outra zona.",
            )
            return

        zone_data = self.controller.project_manager.get_zone_data()

        if "Arena Principal" in zone_name:
            # Edit main arena
            if not zone_data.polygon:
                self.show_warning("Erro", "Arena principal não encontrada.")
                return

            # Convert polygon to the format expected by setup_interactive_polygon
            polygon_points = np.array(zone_data.polygon)
            self.setup_interactive_polygon(polygon_points)
            self.current_editing_zone = "arena"
            self.set_status("Editando vértices da arena principal. Arraste os pontos amarelos.")

        else:
            # Edit ROI
            roi_name = zone_name.replace("📍 ", "")
            try:
                roi_index = zone_data.roi_names.index(roi_name)
                roi_polygon = zone_data.roi_polygons[roi_index]

                # Convert polygon to the format expected by setup_interactive_polygon
                polygon_points = np.array(roi_polygon)
                self.setup_interactive_polygon(polygon_points)
                self.current_editing_zone = ("roi", roi_index, roi_name)
                self.set_status(
                    f"Editando vértices da ROI '{roi_name}'. Arraste os pontos amarelos."
                )

            except (ValueError, IndexError):
                self.show_error("Erro", f"ROI '{roi_name}' não encontrada.")
                return

    def _rename_selected_roi(self):
        """Renomeia ROI selecionada"""
        selected = self.zone_listbox.selection()
        if not selected:
            return

        item = self.zone_listbox.item(selected[0])
        old_name = item["values"][0].replace("📍 ", "")

        new_name = self.ask_string(
            "Renomear ROI", f"Novo nome para '{old_name}':", initialvalue=old_name
        )

        if new_name and new_name != old_name:
            # Atualiza no projeto
            zone_data = self.controller.project_manager.get_zone_data()
            try:
                idx = zone_data.roi_names.index(old_name)
                zone_data.roi_names[idx] = new_name

                # Persist updated ROI name
                self.controller.project_manager.save_zone_data(zone_data)

                # Atualiza visualização
                self.redraw_zones_from_project_data()
                self.show_info("Sucesso", f"ROI renomeada para '{new_name}'")
                status_message = f"ROI renomeada para '{new_name}'."
                self.set_status(status_message)
                self._request_overview_refresh(reason=status_message, append_summary=True)

            except ValueError:
                self.show_error("Erro", "ROI não encontrada")

    def _change_roi_color(self):
        """Muda cor da ROI selecionada"""
        selected = self.zone_listbox.selection()
        if not selected:
            return

        item = self.zone_listbox.item(selected[0])
        old_name = item["values"][0].replace("📍 ", "")

        # Usa o diálogo de cores personalizado
        color_dialog = ColorSelectionDialog(self.root, "Mudar Cor da ROI")
        if not color_dialog.result:
            return

        selected_color = color_dialog.result
        new_color = selected_color["rgb"]
        color_name = selected_color["name"]

        # Atualiza no projeto
        zone_data = self.controller.project_manager.get_zone_data()
        try:
            idx = zone_data.roi_names.index(old_name)
            zone_data.roi_colors[idx] = new_color

            # Persist color change
            self.controller.project_manager.save_zone_data(zone_data)

            # Atualiza visualização
            self.redraw_zones_from_project_data()
            self.show_info("Sucesso", f"Cor da ROI '{old_name}' alterada para {color_name}")
            status_message = f"Cor da ROI '{old_name}' alterada para {color_name}."
            self.set_status(status_message)
            self._request_overview_refresh(reason=status_message, append_summary=True)

        except ValueError:
            self.show_error("Erro", "ROI não encontrada")
        except IndexError:
            self.show_error("Erro", "Dados de cor da ROI não encontrados")

    def _remove_selected_roi_confirm(self):
        """Remove ROI selecionada com confirmação"""
        selected = self.zone_listbox.selection()
        if not selected:
            return

        item = self.zone_listbox.item(selected[0])
        roi_name = item["values"][0].replace("📍 ", "")

        # Confirmação
        from tkinter import messagebox

        confirm = messagebox.askyesno(
            "Confirmar Remoção",
            f"Tem certeza que deseja remover a ROI '{roi_name}'?\n\n"
            "Esta ação não pode ser desfeita.",
            icon="warning",
        )

        if confirm:
            # Remove do projeto
            zone_data = self.controller.project_manager.get_zone_data()
            try:
                idx = zone_data.roi_names.index(roi_name)

                # Remove da lista de nomes
                zone_data.roi_names.pop(idx)

                # Remove da lista de polígonos
                if idx < len(zone_data.roi_polygons):
                    zone_data.roi_polygons.pop(idx)

                # Remove da lista de cores
                if idx < len(zone_data.roi_colors):
                    zone_data.roi_colors.pop(idx)

                # Persist removals
                self.controller.project_manager.save_zone_data(zone_data)

                # Atualiza visualização
                self.redraw_zones_from_project_data()
                self.show_info("Sucesso", f"ROI '{roi_name}' removida com sucesso")
                status_message = f"ROI '{roi_name}' removida com sucesso."
                self.set_status(status_message)
                self._request_overview_refresh(reason=status_message, append_summary=True)

            except ValueError:
                self.show_error("Erro", "ROI não encontrada")

    def ask_save_filename(self, **options):
        """Shows a dialog to select a save file path."""
        return filedialog.asksaveasfilename(**options)

    def update_button_state(self, button_name, state):
        """Updates the state of a button ('normal' or 'disabled')."""
        if button_name == "start_rec" and self.start_rec_btn is not None:
            self.start_rec_btn.config(state=state)
        elif button_name == "stop_rec" and self.stop_rec_btn is not None:
            self.stop_rec_btn.config(state=state)
        elif button_name == "process_video" and self.process_video_btn is not None:
            self.process_video_btn.config(state=state)
        elif button_name == "cancel_processing" and self.cancel_proc_btn is not None:
            self.cancel_proc_btn.config(state=state)

    def ask_recording_details_unified(self):
        """Shows a unified dialog to get day, group, and subject."""
        # Check if it's a live project with the necessary config
        pm = self.controller.project_manager
        if not pm.project_data.get("experiment_days"):
            self.show_error(
                "Error",
                "This project is not configured for live experimental tracking.",
            )
            return None

        dialog = StartRecordingDialog(self.root, pm)
        return dialog.result

    def ask_missing_metadata(self, experiment_id):
        """Shows a dialog to get missing metadata from the user."""
        dialog = MissingMetadataDialog(self.root, experiment_id)
        return dialog.result


class SingleVideoConfigDialog(simpledialog.Dialog):
    """A simplified dialog to get configuration for a single video analysis."""

    def __init__(self, parent):
        self.result = None
        super().__init__(parent, "Configuração de Análise de Vídeo Único")

    def body(self, master):
        # --- Tkinter Variables ---
        self.num_aquariums_var = StringVar(value="1")
        self.animals_per_aquarium_var = StringVar(value="1")
        self.aquarium_width_var = StringVar(value="10.0")
        self.aquarium_height_var = StringVar(value="10.0")

        # Pre-fill with defaults from settings
        self.sharp_turn_var = StringVar(
            value=str(settings.video_processing.sharp_turn_threshold_deg_s)
        )
        self.freeze_thresh_var = StringVar(
            value=str(settings.video_processing.freezing_velocity_threshold)
        )
        self.freeze_dur_var = StringVar(
            value=str(settings.video_processing.freezing_min_duration_s)
        )
        self.smoothing_window_var = StringVar(
            value=str(settings.trajectory_smoothing.window_length)
        )
        self.smoothing_polyorder_var = StringVar(value=str(settings.trajectory_smoothing.polyorder))

        # Frame interval configuration variables
        self.analysis_interval_var = StringVar(value="10")
        self.display_interval_var = StringVar(value="10")

        # Detection method configuration variables
        self.aquarium_method_var = StringVar(value=settings.model_selection.aquarium_method)
        self.animal_method_var = StringVar(value=settings.model_selection.animal_method)
        self.use_openvino_var = BooleanVar(value=True)  # OpenVINO enabled by default

        # --- Layout ---
        main_frame = ttk.Frame(master, padding=10)
        main_frame.pack(expand=True, fill="both")

        # --- Aquarium Dimensions ---
        dim_frame = ttk.LabelFrame(main_frame, text="Calibração", padding=10)
        dim_frame.pack(fill="x", pady=5)
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
        behavior_frame = ttk.LabelFrame(main_frame, text="Parâmetros de Análise", padding=10)
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

        ttk.Label(behavior_frame, text="Janela de Suavização (frames):").grid(
            row=3, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(behavior_frame, textvariable=self.smoothing_window_var, width=10).grid(
            row=3, column=1, sticky="w", padx=5
        )

        ttk.Label(behavior_frame, text="Ordem do Polinômio:").grid(
            row=4, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(behavior_frame, textvariable=self.smoothing_polyorder_var, width=10).grid(
            row=4, column=1, sticky="w", padx=5
        )

        ttk.Label(
            behavior_frame,
            text=(
                "Savitzky-Golay suaviza trajetórias preservando picos. "
                "Use janela ímpar ≥ 3 e ordem < janela para evitar distorções."
            ),
            wraplength=260,
            font=("TkDefaultFont", 8),
            foreground="#444",
        ).grid(row=5, column=0, columnspan=2, sticky="w", padx=5, pady=(4, 0))

        # --- Frame Interval Settings ---
        interval_frame = ttk.LabelFrame(main_frame, text="Intervalos de Processamento", padding=10)
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
        method_frame = ttk.LabelFrame(main_frame, text="Métodos de Detecção", padding=10)
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

    def validate(self):
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
        log.info(
            "single_video_dialog.apply",
            analysis_interval=analysis_interval,
            display_interval=display_interval,
        )
        self.result = {
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


class StartRecordingDialog(simpledialog.Dialog):
    def __init__(self, parent, project_manager):
        self.pm = project_manager
        self.result = None
        super().__init__(parent, "Iniciar Nova Sessão de Gravação")

    def body(self, master):
        # Get data from project manager
        days = self.pm.project_data.get("experiment_days", 1)
        groups = self.pm.project_data.get("groups", [])
        subjects = self.pm.project_data.get("subjects_per_group", 1)
        last_day, last_group = self.pm.get_last_session_details()

        # Create variables
        self.day_var = StringVar()
        self.group_var = StringVar()
        self.subject_var = StringVar()

        # Set initial values for smart state retention
        day_opts = [str(d) for d in range(1, days + 1)]
        if last_day and str(last_day) in day_opts:
            self.day_var.set(str(last_day))
        elif day_opts:
            self.day_var.set(day_opts[0])

        if last_group and last_group in groups:
            self.group_var.set(last_group)
        elif groups:
            self.group_var.set(groups[0])

        # --- Layout ---
        # Day Dropdown
        Label(master, text="Selecione o Dia:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        day_menu = OptionMenu(master, self.day_var, *day_opts)
        day_menu.grid(row=0, column=1, sticky="ew", padx=5)

        # Group Dropdown
        Label(master, text="Selecione o Grupo:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        group_menu = OptionMenu(master, self.group_var, *groups)
        group_menu.grid(row=1, column=1, sticky="ew", padx=5)

        # Subject Dropdown
        Label(master, text="Selecione a Cobaia:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        subject_opts = [str(s) for s in range(1, subjects + 1)]
        subject_menu = OptionMenu(master, self.subject_var, *subject_opts)
        subject_menu.grid(row=2, column=1, sticky="ew", padx=5)
        if subject_opts:
            self.subject_var.set(subject_opts[0])

        return subject_menu  # Initial focus

    def validate(self):
        if not all([self.day_var.get(), self.group_var.get(), self.subject_var.get()]):
            messagebox.showerror("Erro", "Todos os campos são obrigatórios.")
            return False
        return True

    def apply(self):
        self.result = {
            "day": int(self.day_var.get()),
            "group": self.group_var.get(),
            "cobaia": self.subject_var.get(),
        }


class MissingMetadataDialog(simpledialog.Dialog):
    def __init__(self, parent, experiment_id):
        self.experiment_id = experiment_id
        self.result = None
        super().__init__(parent, "Metadados Ausentes")

    def body(self, master):
        Label(master, text="Não foi possível encontrar metadados automaticamente para:").pack(
            pady=5
        )
        Label(master, text=self.experiment_id, font=("Helvetica", 10, "bold")).pack(pady=(0, 10))
        Label(master, text="Por favor, insira os detalhes manualmente:").pack(pady=5)

        self.day_var = StringVar()
        self.group_var = StringVar()
        self.cobaia_var = StringVar()

        form_frame = Frame(master)
        form_frame.pack(padx=10, pady=10)

        Label(form_frame, text="Dia:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        Entry(form_frame, textvariable=self.day_var).grid(row=0, column=1, sticky="ew", padx=5)

        Label(form_frame, text="Grupo:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        Entry(form_frame, textvariable=self.group_var).grid(row=1, column=1, sticky="ew", padx=5)

        Label(form_frame, text="Cobaia (ID):").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        Entry(form_frame, textvariable=self.cobaia_var).grid(row=2, column=1, sticky="ew", padx=5)

        return form_frame

    def validate(self):
        try:
            int(self.day_var.get())
            int(self.cobaia_var.get())
        except ValueError:
            messagebox.showerror(
                "Erro de Validação", "Dia e Cobaia (ID) devem ser números inteiros."
            )
            return 0

        if not self.group_var.get().strip():
            messagebox.showerror("Erro de Validação", "O nome do grupo não pode estar vazio.")
            return 0

        return 1

    def apply(self):
        self.result = {
            "day": int(self.day_var.get()),
            "group": self.group_var.get().strip(),
            "cobaia": int(self.cobaia_var.get()),
        }


class SubjectSelectionDialog(simpledialog.Dialog):
    def __init__(self, parent, day, group_name, subjects_per_group, completed_subjects):
        self.day = day
        self.group_name = group_name
        self.subjects_per_group = subjects_per_group
        self.completed_subjects = completed_subjects
        self.result = None  # This will be the selected subject_id

        day_display = ApplicationGUI._format_day_display(day) or day
        day_title = (
            f"Dia {day_display}" if str(day_display).strip().lower() != "sem dia" else "Sem Dia"
        )

        super().__init__(parent, f"Selecionar Cobaia para o {day_title} - {group_name}")

    def body(self, master):
        master.config(padx=10, pady=10)
        for i in range(self.subjects_per_group):
            subject_id = i + 1
            is_completed = subject_id in self.completed_subjects

            status_text = f"Cobaia {subject_id}: {'Concluído' if is_completed else 'Pendente'}"
            status_color = "darkgreen" if is_completed else "black"

            label = ttk.Label(
                master,
                text=status_text,
                foreground=status_color,
                font=("Helvetica", 10),
            )
            label.pack(anchor="w", pady=3)

            if not is_completed:
                label.config(cursor="hand2")
                label.bind("<Button-1>", lambda e, s=subject_id: self.select_subject(s))
        return None  # No initial focus

    def select_subject(self, subject_id):
        self.result = subject_id
        self.ok()  # Close the dialog

    def buttonbox(self):
        # Override to have only a cancel button, since selection closes the dialog
        box = ttk.Frame(self)
        w = ttk.Button(box, text="Cancelar", width=10, command=self.cancel)
        w.pack(side="left", padx=5, pady=5)
        self.bind("<Escape>", self.cancel)
        box.pack()


class SaveROITemplateDialog(simpledialog.Dialog):
    """Dialog that gathers options for saving ROI/Arena templates."""

    def __init__(
        self,
        parent,
        *,
        default_name: str,
        has_arena: bool,
        has_rois: bool,
        allow_project: bool,
    ) -> None:
        self.result: dict[str, Any] | None = None
        self._has_arena = has_arena
        self._has_rois = has_rois
        self._allow_project = allow_project
        self._default_name = default_name
        super().__init__(parent, "Salvar template de zonas")

    def body(self, master):
        master.columnconfigure(1, weight=1)

        ttk.Label(master, text="Nome do template:").grid(
            row=0, column=0, sticky="w", padx=(5, 5), pady=(5, 2)
        )
        self.name_var = StringVar(value=self._default_name)
        self.name_entry = ttk.Entry(master, textvariable=self.name_var, width=40)
        self.name_entry.grid(row=0, column=1, sticky="ew", padx=(0, 5), pady=(5, 2))

        ttk.Label(master, text="Incluir no template:").grid(
            row=1, column=0, sticky="nw", padx=(5, 5), pady=(8, 2)
        )
        options_frame = ttk.Frame(master)
        options_frame.grid(row=1, column=1, sticky="w", padx=(0, 5), pady=(5, 2))

        self.save_arena_var = BooleanVar(value=self._has_arena)
        arena_check = ttk.Checkbutton(
            options_frame,
            text="Arena principal",
            variable=self.save_arena_var,
        )
        arena_check.grid(row=0, column=0, sticky="w")
        if not self._has_arena:
            self.save_arena_var.set(False)
            arena_check.state(["disabled"])

        self.save_rois_var = BooleanVar(value=self._has_rois)
        rois_check = ttk.Checkbutton(
            options_frame,
            text="Regiões de Interesse (ROIs)",
            variable=self.save_rois_var,
        )
        rois_check.grid(row=1, column=0, sticky="w", pady=(3, 0))
        if not self._has_rois:
            self.save_rois_var.set(False)
            rois_check.state(["disabled"])

        ttk.Label(master, text="Salvar em:").grid(
            row=2, column=0, sticky="nw", padx=(5, 5), pady=(10, 2)
        )
        location_frame = ttk.Frame(master)
        location_frame.grid(row=2, column=1, sticky="w", padx=(0, 5), pady=(5, 2))

        default_location = "project" if self._allow_project else "global"
        self.location_var = StringVar(value=default_location)
        self.location_var.trace_add("write", lambda *_: self._update_custom_state())

        self._project_radio = ttk.Radiobutton(
            location_frame,
            text="Projeto atual",
            value="project",
            variable=self.location_var,
        )
        self._project_radio.grid(row=0, column=0, sticky="w")
        if not self._allow_project:
            self._project_radio.state(["disabled"])

        ttk.Radiobutton(
            location_frame,
            text="Configurações globais",
            value="global",
            variable=self.location_var,
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))

        ttk.Radiobutton(
            location_frame,
            text="Local personalizado",
            value="custom",
            variable=self.location_var,
        ).grid(row=2, column=0, sticky="w", pady=(3, 0))

        custom_frame = ttk.Frame(location_frame)
        custom_frame.grid(row=3, column=0, sticky="we", pady=(6, 0))
        custom_frame.columnconfigure(0, weight=1)

        self.custom_path_var = StringVar(value="")
        self.custom_path_entry = ttk.Entry(
            custom_frame,
            textvariable=self.custom_path_var,
            width=36,
        )
        self.custom_path_entry.grid(row=0, column=0, sticky="ew")

        self.browse_button = ttk.Button(
            custom_frame,
            text="Procurar…",
            command=self._browse_custom_path,
            width=12,
        )
        self.browse_button.grid(row=0, column=1, padx=(6, 0))

        ttk.Label(
            master,
            text=(
                "Templates globais ficam disponíveis para todos os projetos. "
                "Use um local personalizado para compartilhar manualmente."
            ),
            wraplength=360,
            foreground="#4a4a4a",
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=(12, 0))

        self._update_custom_state()
        return self.name_entry

    def validate(self) -> bool:
        name = (self.name_var.get() or "").strip()
        save_arena = bool(self.save_arena_var.get())
        save_rois = bool(self.save_rois_var.get())
        location = self.location_var.get()

        if not name:
            messagebox.showwarning("Nome obrigatório", "Informe o nome do template.")
            return False

        if not save_arena and not save_rois:
            messagebox.showwarning(
                "Seleção incompleta",
                "Escolha ao menos a arena ou as ROIs para salvar no template.",
            )
            return False

        if location == "custom":
            path = (self.custom_path_var.get() or "").strip()
            if not path:
                messagebox.showwarning(
                    "Local não definido",
                    "Selecione o arquivo onde o template será salvo.",
                )
                return False

        return True

    def apply(self) -> None:
        location = self.location_var.get()
        custom_path = (self.custom_path_var.get() or "").strip()
        if location == "custom" and custom_path:
            candidate = Path(custom_path)
            if candidate.suffix.lower() != ".json":
                custom_path = str(candidate.with_suffix(".json"))

        self.result = {
            "name": (self.name_var.get() or "").strip(),
            "save_arena": bool(self.save_arena_var.get()),
            "save_rois": bool(self.save_rois_var.get()),
            "save_location": location,
            "custom_path": custom_path if location == "custom" else None,
        }

    def _update_custom_state(self) -> None:
        is_custom = self.location_var.get() == "custom"
        state = "normal" if is_custom else "disabled"
        self.custom_path_entry.config(state=state)
        self.browse_button.config(state=state)

    def _browse_custom_path(self) -> None:
        initial_slug = self._suggest_filename()
        chosen = filedialog.asksaveasfilename(
            title="Salvar template de zonas",
            defaultextension=".json",
            filetypes=[("Template de zonas", "*.json"), ("Todos os arquivos", "*.*")],
            initialfile=f"{initial_slug}.json" if initial_slug else "",
        )
        if chosen:
            self.custom_path_var.set(chosen)
            self.location_var.set("custom")

    def _suggest_filename(self) -> str:
        candidate = (self.name_var.get() or "").strip()
        if not candidate:
            return "template"
        normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", candidate).strip("-")
        return normalized.lower() or "template"


class TemplateDialog(simpledialog.Dialog):
    """Dialog to create ROI templates."""

    def body(self, master):
        self.template_type = StringVar(value="vertical")
        self.num_lanes = StringVar(value="3")
        self.num_rows = StringVar(value="2")
        self.num_cols = StringVar(value="2")

        ttk.Radiobutton(
            master,
            text="Faixas Verticais",
            variable=self.template_type,
            value="vertical",
        ).pack(anchor="w")
        ttk.Radiobutton(
            master,
            text="Faixas Horizontais",
            variable=self.template_type,
            value="horizontal",
        ).pack(anchor="w")
        ttk.Radiobutton(master, text="Grade", variable=self.template_type, value="grid").pack(
            anchor="w"
        )

        ttk.Label(master, text="Nº de Faixas:").pack(anchor="w", pady=(5, 0))
        ttk.Entry(master, textvariable=self.num_lanes).pack(anchor="w")

        ttk.Label(master, text="Grade (Linhas x Colunas):").pack(anchor="w", pady=(5, 0))
        grid_frame = ttk.Frame(master)
        grid_frame.pack(anchor="w")
        ttk.Entry(grid_frame, textvariable=self.num_rows, width=5).pack(side="left")
        ttk.Label(grid_frame, text="x").pack(side="left")
        ttk.Entry(grid_frame, textvariable=self.num_cols, width=5).pack(side="left")
        return master

    def apply(self):
        try:
            self.result = {
                "type": self.template_type.get(),
                "lanes": int(self.num_lanes.get()),
                "rows": int(self.num_rows.get()),
                "cols": int(self.num_cols.get()),
            }
        except (ValueError, TypeError):
            self.result = None


class CenterPeripheryDialog(simpledialog.Dialog):
    """Dialog for center-periphery analysis settings."""

    def body(self, master):
        self.method = StringVar(value="distance")
        self.value = StringVar(value="5.0")

        ttk.Label(master, text="Método:").pack(anchor="w")
        ttk.Radiobutton(
            master,
            text="Distância da Borda (cm)",
            variable=self.method,
            value="distance",
        ).pack(anchor="w")
        ttk.Radiobutton(
            master,
            text="Razão da Área (0.0-1.0)",
            variable=self.method,
            value="area_ratio",
        ).pack(anchor="w")

        ttk.Label(master, text="Valor:").pack(anchor="w", pady=(5, 0))
        ttk.Entry(master, textvariable=self.value).pack(anchor="w")
        return master

    def apply(self):
        try:
            self.result = {
                "method": self.method.get(),
                "value": float(self.value.get()),
            }
        except (ValueError, TypeError):
            self.result = None


# ==============================================================================
# Backward Compatibility Properties for Component Migration
# ==============================================================================
# These properties allow legacy code to continue working while we gradually
# migrate to the new component-based architecture. They map old attribute names
# to the new component APIs.
# TODO: Remove these after full migration is complete.


def _add_compatibility_properties_to_application_gui():
    """Add backward compatibility properties to ApplicationGUI class."""

    @property
    def roi_canvas(self):
        """
        Backward compatibility property: maps roi_canvas to video_display.canvas.

        This allows existing drawing code to continue working during the gradual
        migration to VideoDisplayWidget. Should be removed after migration is complete.
        """
        if hasattr(self, "video_display") and self.video_display:
            return self.video_display.canvas
        # Fallback to old widget if component not yet created
        if hasattr(self, "_roi_canvas_widget"):
            return self._roi_canvas_widget
        return None

    @property
    def zone_listbox(self):
        """Backward compatibility: map zone_listbox to zone_controls.zone_listbox."""
        if hasattr(self, "zone_controls") and self.zone_controls:
            return self.zone_controls.zone_listbox
        return None

    @property
    def draw_roi_button(self):
        """Backward compatibility: map draw_roi_button to zone_controls.draw_roi_button."""
        if hasattr(self, "zone_controls") and self.zone_controls:
            return self.zone_controls.draw_roi_button
        return None

    @property
    def toggle_view_btn(self):
        """Backward compatibility: map toggle_view_btn to zone_controls.toggle_view_btn."""
        if hasattr(self, "zone_controls") and self.zone_controls:
            return self.zone_controls.toggle_view_btn
        return None

    @property
    def roi_template_combobox(self):
        """
        Backward compatibility: map roi_template_combobox to
        zone_controls.roi_template_combobox.
        """
        if hasattr(self, "zone_controls") and self.zone_controls:
            return self.zone_controls.roi_template_combobox
        return None

    @property
    def video_selector_tree(self):
        """Backward compatibility: map video_selector_tree to zone_controls.video_selector_tree."""
        if hasattr(self, "zone_controls") and self.zone_controls:
            return self.zone_controls.video_selector_tree
        return None

    @property
    def interactive_buttons_frame(self):
        """
        Backward compatibility: map interactive_buttons_frame to
        zone_controls.interactive_buttons_frame.
        """
        if hasattr(self, "zone_controls") and self.zone_controls:
            return self.zone_controls.interactive_buttons_frame
        return None

    # Add properties to ApplicationGUI class
    ApplicationGUI.roi_canvas = roi_canvas
    ApplicationGUI.zone_listbox = zone_listbox
    ApplicationGUI.draw_roi_button = draw_roi_button
    ApplicationGUI.toggle_view_btn = toggle_view_btn
    ApplicationGUI.roi_template_combobox = roi_template_combobox
    ApplicationGUI.video_selector_tree = video_selector_tree
    ApplicationGUI.interactive_buttons_frame = interactive_buttons_frame


# Apply compatibility properties
_add_compatibility_properties_to_application_gui()


class ColorSelectionDialog(simpledialog.Dialog):
    """Diálogo para seleção de cor de áreas de interesse."""

    def __init__(self, parent, title="Selecionar Cor da Área"):
        self.result = None
        super().__init__(parent, title)

    def body(self, master):
        """Cria o corpo do diálogo com opções de cores."""
        self.selected_color = StringVar(value="green")

        # Cores disponíveis: (nome, valor_bgr para OpenCV, cor_hex para visualização)
        self.colors = [
            ("Verde", (0, 255, 0), "#00FF00"),
            ("Azul", (255, 0, 0), "#0000FF"),  # BGR: (255, 0, 0) = Blue
            ("Vermelho", (0, 0, 255), "#FF0000"),  # BGR: (0, 0, 255) = Red
            ("Amarelo", (0, 255, 255), "#FFFF00"),  # BGR: (0, 255, 255) = Yellow
            ("Magenta", (255, 0, 255), "#FF00FF"),  # BGR: (255, 0, 255) = Magenta
            ("Ciano", (255, 255, 0), "#00FFFF"),  # BGR: (255, 255, 0) = Cyan
        ]

        ttk.Label(master, text="Escolha a cor para esta área de interesse:").pack(pady=5)

        # Frame para os botões de cor
        colors_frame = ttk.Frame(master)
        colors_frame.pack(pady=10)

        # Criar botões de cor em duas fileiras
        for i, (name, rgb, hex_color) in enumerate(self.colors):
            row = i // 3
            col = i % 3

            color_frame = ttk.Frame(colors_frame)
            color_frame.grid(row=row, column=col, padx=5, pady=5)

            # Radiobutton para seleção
            ttk.Radiobutton(
                color_frame,
                text=name,
                variable=self.selected_color,
                value=name.lower(),
            ).pack()

            # Quadrado colorido para visualização
            color_canvas = Canvas(color_frame, width=30, height=20, highlightthickness=1)
            color_canvas.pack()
            color_canvas.create_rectangle(0, 0, 30, 20, fill=hex_color, outline="black")

        return master

    def apply(self):
        """Aplica a seleção de cor."""
        selected_name = self.selected_color.get()
        for name, rgb, hex_color in self.colors:
            if name.lower() == selected_name:
                self.result = {"name": name, "rgb": rgb, "hex": hex_color}
                break


if __name__ == "__main__":
    # Using print is fine here as it's for direct execution feedback
    print("Este arquivo deve ser importado, não executado diretamente.")
    print("Execute o script principal da aplicação para iniciar o Zebtrack.")
