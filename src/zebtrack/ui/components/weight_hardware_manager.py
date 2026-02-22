"""Weight/hardware manager — manages model weights and hardware display state.

Extracted from ApplicationGUI (Phase 4.4) to isolate weight selection,
OpenVINO toggle, and GPU hardware display logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from zebtrack.ui.event_bus_v2 import UIEvents

if TYPE_CHECKING:
    from tkinter import StringVar

    from zebtrack.ui.gui import ApplicationGUI

log = structlog.get_logger()


class WeightHardwareManager:
    """Manages model weight state, OpenVINO status, and GPU hardware display.

    All widget state is stored on the parent ``ApplicationGUI`` instance via
    the ``gui`` back-reference; this class only contains the update logic.
    """

    def __init__(self, gui: ApplicationGUI) -> None:
        self.gui = gui

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def _active_display_var(self) -> StringVar:
        return self.gui._active_weight_display_var

    @property
    def _openvino_display_var(self) -> StringVar:
        return self.gui._openvino_display_var

    @property
    def _gpu_display_var(self) -> StringVar:
        return self.gui._gpu_hardware_display_var

    # ------------------------------------------------------------------
    # Weight type / action dialogs
    # ------------------------------------------------------------------

    def handle_request_weight_type(self, filepath: str) -> None:
        """Handle request to identify weight type."""
        from tkinter import simpledialog

        weight_type = simpledialog.askstring(
            "Tipo do Modelo",
            "O tipo do modelo não pôde ser determinado automaticamente.\n"
            "Digite 'seg' para Segmentação ou 'det' para Detecção:",
            parent=self.gui.root,
        )

        if weight_type:
            # Normalize input
            weight_type = weight_type.lower().strip()
            if weight_type in ["seg", "segmentation", "segmentação"]:
                weight_type = "seg"
            elif weight_type in ["det", "detection", "detecção"]:
                weight_type = "det"

            # Resume workflow
            self.gui.controller.hardware_vm.load_new_weight(
                filepath=filepath, weight_type=weight_type
            )

    def handle_request_weight_action(self, filepath: str, weight_type: str) -> None:
        """Handle request for action on new weight."""
        from tkinter import messagebox

        type_label = "Segmentação" if weight_type == "seg" else "Detecção"

        response = messagebox.askyesnocancel(
            "Novo Peso Encontrado",
            f"O arquivo '{Path(filepath).name}' foi identificado como modelo de {type_label}.\n\n"
            "Deseja defini-lo como o novo padrão para {type_label}?\n"
            "Sim: Define como padrão\n"
            "Não: Apenas adiciona à lista\n"
            "Cancelar: Aborta a operação",
            parent=self.gui.root,
        )

        choice = None
        if response is True:
            choice = "yes"
        elif response is False:
            choice = "no"
        else:
            choice = "cancel"

        if choice != "cancel":
            self.gui.controller.hardware_vm.load_new_weight(
                filepath=filepath, weight_type=weight_type, choice=choice
            )

    # ------------------------------------------------------------------
    # Weight dropdown
    # ------------------------------------------------------------------

    def update_weights_dropdown(self, weights: list[str]) -> None:
        """Cache available weights so summaries stay consistent."""
        self.gui._available_weight_names = list(weights or [])
        if (
            self.gui.controller.hardware_vm.active_weight_name
            and self.gui.controller.hardware_vm.active_weight_name
            in self.gui._available_weight_names
        ):
            self._update_active_weight_display(self.gui.controller.hardware_vm.active_weight_name)
        elif not self.gui._available_weight_names:
            self._update_active_weight_display("")

    def set_active_weight_in_dropdown(self, weight_name: str | None) -> None:
        """Update the active weight summary."""
        self._update_active_weight_display(weight_name or "")

    # ------------------------------------------------------------------
    # OpenVINO state
    # ------------------------------------------------------------------

    def update_openvino_checkbox(self, enabled: bool) -> None:
        """Synchronize OpenVINO toggle state with the summary label."""
        self.gui._openvino_enabled = bool(enabled)
        self._refresh_openvino_summary()

    def update_openvino_status_display(self, status: str) -> None:
        """Update the detailed OpenVINO status shown in the UI."""
        self.gui._openvino_status_message = status or ""
        self._refresh_openvino_summary()

    def _refresh_openvino_summary(self) -> None:
        state_text = "Ativado" if self.gui._openvino_enabled else "Desativado"
        status_text = self.gui._openvino_status_message.strip()
        if status_text:
            self._openvino_display_var.set(f"OpenVINO: {state_text} — {status_text}")
        else:
            self._openvino_display_var.set(f"OpenVINO: {state_text}")

    # ------------------------------------------------------------------
    # Active weight display
    # ------------------------------------------------------------------

    def _update_active_weight_display(self, weight_name: str) -> None:
        if weight_name:
            self._active_display_var.set(f"Peso ativo: {weight_name}")
        else:
            self._active_display_var.set("Peso ativo: Nenhum peso selecionado.")

    # ------------------------------------------------------------------
    # GPU / Hardware display
    # ------------------------------------------------------------------

    def update_gpu_hardware_display(self, hardware_summary: dict) -> None:
        """Update the GPU hardware information shown in the UI."""
        gpu_name = "CPU apenas"
        recommended_backend = hardware_summary.get("recommended_backend", "pytorch")

        # Try to get NVIDIA GPU name first
        if hardware_summary.get("cuda_available", False):
            try:
                import torch

                if torch.cuda.is_available():
                    gpu_name = torch.cuda.get_device_name(0)
            except (ImportError, RuntimeError):
                gpu_name = "NVIDIA GPU"
        # Then check for Intel/OpenVINO GPU
        elif hardware_summary.get("has_intel_gpu", False):
            openvino_devices = hardware_summary.get("openvino_devices", [])
            gpu_devices = [d for d in openvino_devices if "GPU" in d]
            if gpu_devices:
                gpu_name = "Intel GPU"

        # Format display string
        backend_display = "PyTorch" if recommended_backend == "pytorch" else "OpenVINO"
        if "CPU" in gpu_name:
            display_text = f"Hardware: {gpu_name}"
        else:
            display_text = f"Hardware: {gpu_name} (recomendado: {backend_display})"

        self._gpu_display_var.set(display_text)

    # ------------------------------------------------------------------
    # Manage weights event
    # ------------------------------------------------------------------

    def manage_weights_clicked(self) -> None:
        """Open the weight management dialog."""
        self.gui.event_dispatcher.publish_event(UIEvents.MODEL_MANAGE_WEIGHTS)
