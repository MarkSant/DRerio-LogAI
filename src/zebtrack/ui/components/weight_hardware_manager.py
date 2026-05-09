"""Weight/hardware manager — manages model weights and hardware display state.

Extracted from ApplicationGUI (Phase 4.4) to isolate weight selection,
OpenVINO toggle, and GPU hardware display logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import structlog

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

    def handle_request_weight_type(self, filepath: Path | str) -> None:
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

    def handle_request_weight_action(self, filepath: Path | str, weight_type: str) -> None:
        """Handle request for action on new weight."""
        from tkinter import messagebox

        type_label = "Segmentação" if weight_type == "seg" else "Detecção"

        response = messagebox.askyesnocancel(
            "Novo Peso Encontrado",
            f"O arquivo '{Path(filepath).name}' foi identificado como modelo de {type_label}.\n\n"
            f"Deseja defini-lo como o novo padrão para {type_label}?\n"
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
        """Cache available weights and refresh the slot-summary display."""
        self.gui._available_weight_names = list(weights or [])
        self.refresh_weights_summary()

    def set_active_weight_in_dropdown(self, weight_name: str | None) -> None:
        """Refresh slot summary; the diagnostic-weight combobox lives elsewhere now."""
        # ``weight_name`` is now solely the diagnostic-test weight in the
        # Calibration dialog; the welcome / project status panel reflects the
        # 4 (or 2) default slots, not a single ``active_weight``.
        del weight_name
        self.refresh_weights_summary()

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
        device_text = self._get_openvino_device_label()

        summary = f"OpenVINO: {state_text}"
        if device_text:
            summary = f"{summary} ({device_text})"

        if status_text:
            self._openvino_display_var.set(f"{summary} — {status_text}")
        else:
            self._openvino_display_var.set(summary)

    def _get_openvino_device_label(self) -> str:
        """Return human-readable OpenVINO device target from active settings.

        This may run before ``MainViewModel`` is fully resolved (e.g. when
        ``ApplicationBootstrapper`` updates the OpenVINO status during DI
        warm-up). The controller can therefore be a ``LazyRef`` whose
        ``__getattr__`` raises ``RuntimeError`` for unresolved access —
        which ``getattr`` with a default does NOT catch. We swallow that
        case explicitly and return an empty label.
        """
        controller = getattr(self.gui, "controller", None)
        if not controller:
            return ""

        # Bail out when a LazyRef is still pending (avoids RuntimeError on access).
        is_resolved = getattr(controller, "is_resolved", None)
        if callable(is_resolved) and not is_resolved():
            return ""

        try:
            settings_obj = getattr(controller, "settings", None) or getattr(
                controller, "settings_obj", None
            )
        except RuntimeError:
            # Defensive: covers any LazyRef without is_resolved() introspection.
            return ""

        if settings_obj and hasattr(settings_obj, "openvino"):
            raw_device = getattr(settings_obj.openvino, "device", "")
            if isinstance(raw_device, str) and raw_device.strip():
                return f"dispositivo: {raw_device.strip().upper()}"

        return ""

    # ------------------------------------------------------------------
    # Active weight summary (4-slot or 2-slot multi-line label)
    # ------------------------------------------------------------------

    def refresh_weights_summary(self, *, scope: str | None = None) -> None:
        """Re-render the multi-line weights summary in the status panel.

        ``scope`` selects which slots to render:

        - ``"global"`` shows all 4 ``(method × target)`` defaults.
        - ``"project"`` shows only the 2 slots actually consumed by the open
          project (filtered by ``settings.model_selection.{aquarium,animal}_method``).
        - ``None`` (default) auto-picks: ``"project"`` when a project is open,
          otherwise ``"global"``.

        Safe to call before the ``controller`` LazyRef is resolved — silently
        defers the render and re-tries via ``root.after(0, ...)`` so the
        welcome panel paints once the wiring is complete.
        """
        controller = getattr(self.gui, "controller", None)
        if controller is None:
            return

        # Handle LazyRef proxy gracefully: ``is_resolved`` is a bool property,
        # not a callable. Any direct attribute access would raise RuntimeError
        # while the underlying MainViewModel is still being constructed.
        if getattr(controller, "is_resolved", True) is False:
            self._defer_summary_refresh(scope)
            return

        try:
            hardware_vm = getattr(controller, "hardware_vm", None)
        except RuntimeError:
            # Defensive: LazyRef variant without ``is_resolved`` introspection.
            self._defer_summary_refresh(scope)
            return

        if hardware_vm is None or not hasattr(hardware_vm, "get_default_weights_summary"):
            return

        if scope is None:
            scope = "project" if self._project_is_open() else "global"

        try:
            summary = hardware_vm.get_default_weights_summary(scope=scope)
        # except Exception justified: status panel must never crash on bad data.
        except Exception as exc:
            log.warning("weight_hardware_manager.summary.failed", error=str(exc))
            self._active_display_var.set("Modelo: erro ao consultar pesos")
            return

        header = "Modelo (em uso neste projeto):" if scope == "project" else "Modelo (defaults):"
        if not summary:
            self._active_display_var.set(f"{header}\n  Nenhum peso configurado.")
            return

        lines = [header]
        for label, _method, _target, name in summary:
            display_name = name if name else "—"
            lines.append(f"  {label}: {display_name}")
        self._active_display_var.set("\n".join(lines))

    def _defer_summary_refresh(self, scope: str | None) -> None:
        """Schedule a retry once the Tk event loop processes pending DI work."""
        root = getattr(self.gui, "root", None)
        if root is None or not hasattr(root, "after"):
            return
        try:
            root.after(50, lambda: self.refresh_weights_summary(scope=scope))
        # except Exception justified: deferred refresh is best-effort.
        except Exception as exc:
            log.debug("weight_hardware_manager.defer.failed", error=str(exc))

    def _project_is_open(self) -> bool:
        controller = getattr(self.gui, "controller", None)
        if controller is None:
            return False
        if getattr(controller, "is_resolved", True) is False:
            return False
        try:
            project_manager = getattr(controller, "project_manager", None)
            if project_manager is None:
                return False
            project_data = getattr(project_manager, "project_data", None) or {}
            return bool(project_data.get("project_name"))
        # except Exception justified: probe must not raise during UI refresh.
        except Exception:
            return False

    # ------------------------------------------------------------------
    # GPU / Hardware display
    # ------------------------------------------------------------------

    def update_gpu_hardware_display(self, hardware_summary: dict) -> None:
        """Update the GPU hardware information shown in the UI."""
        gpu_name = "CPU apenas"
        recommended_backend = hardware_summary.get("recommended_backend", "pytorch")
        npu_suffix = ""

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

        # Check for NPU availability
        if hardware_summary.get("has_npu", False):
            npu_suffix = " + NPU"

        # Format display string
        backend_display = "PyTorch" if recommended_backend == "pytorch" else "OpenVINO"
        if "CPU" in gpu_name and not npu_suffix:
            display_text = f"Hardware: {gpu_name}"
        else:
            display_text = f"Hardware: {gpu_name}{npu_suffix} (recomendado: {backend_display})"

        self._gpu_display_var.set(display_text)
