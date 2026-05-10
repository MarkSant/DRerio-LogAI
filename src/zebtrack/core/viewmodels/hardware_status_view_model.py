from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import structlog

if TYPE_CHECKING:
    from zebtrack.core.application_bootstrapper import BootstrapResult
    from zebtrack.core.dependency_container import MainViewModelDependencies
    from zebtrack.core.detection import Detector

log = structlog.get_logger()


class HardwareStatusViewModel:
    """
    ViewModel responsible for Hardware (Arduino/Camera) and Model (OpenVINO/Weights) status.
    """

    def __init__(
        self,
        dependencies: MainViewModelDependencies,
        bootstrap_result: BootstrapResult,
        event_bus: Any,
    ) -> None:
        self.detector_service = dependencies.detector_service
        self.model_service = dependencies.model_service
        # Phase 4.9: HardwareCoordinator decomposed
        self.detector_setup_coordinator = dependencies.detector_setup_coordinator
        self.model_diagnostics_coordinator = dependencies.model_diagnostics_coordinator
        self.arduino_manager = bootstrap_result.hardware.arduino_manager
        self.weight_manager = dependencies.weight_manager
        # Phase 4.7: Replaced single session_coordinator with 3 focused coordinators
        self.recording_session_coordinator = dependencies.recording_session_coordinator
        self.live_camera_session_coordinator = dependencies.live_camera_session_coordinator
        self.live_calibration_coordinator = dependencies.live_calibration_coordinator
        self.ui_state_controller = bootstrap_result.ui_state_controller
        # Phase 3C/D: model_diagnostics_orchestrator and recording_session_orchestrator removed
        # Phase 4.7: Removed recording_coordinator (dead legacy code)
        self.state_manager = dependencies.state_manager
        self.settings = dependencies.settings_obj

        self.ui_event_bus = event_bus

        self.arduino = None  # Initialized later via setup
        self.camera = None
        self.active_frame_source = None

        # Bootstrapped values
        self.active_weight_name = bootstrap_result.hardware.active_weight_name
        self.use_openvino = bootstrap_result.hardware.use_openvino

        self._recording_service = None

    @property
    def detector(self) -> Detector | None:
        return self.detector_service.detector

    @detector.setter
    def detector(self, value: Detector | None) -> None:
        self.detector_service.detector = value

    @property
    def detector_initialized(self) -> bool:
        return self.state_manager.get_detector_state().detector_initialized

    def setup_detector(
        self,
        temp_animal_method: str | None = None,
        perspective: str | None = None,
    ) -> bool:
        if not self.detector_setup_coordinator:
            return False

        success, _ = self.detector_setup_coordinator.setup_detector(
            animal_method=temp_animal_method,
            use_openvino=self.use_openvino,
            active_weight_name=self.active_weight_name,
            perspective=perspective,
        )
        return success

    def update_detector_parameters(self, params: dict, **kwargs) -> bool:
        if self.detector_setup_coordinator:
            return self.detector_setup_coordinator.update_detector_parameters(params, **kwargs)
        return False

    def get_current_detector_parameters(self) -> dict:
        if self.detector_setup_coordinator:
            return self.detector_setup_coordinator.get_detector_parameters()
        return {}

    def restore_detector_defaults(self, scope: str = "global") -> bool:
        if not self.detector_setup_coordinator:
            return False

        if scope == "global":
            factory_defaults = self.detector_setup_coordinator.get_factory_detector_parameters()
            return self.detector_setup_coordinator.update_detector_parameters(
                params=factory_defaults, scope="global", reset_overrides=True
            )
        elif scope == "project":
            return self.detector_setup_coordinator.update_detector_parameters(
                params={}, scope="project", reset_overrides=True
            )
        return False

        # --- Arduino ---

    def setup_arduino(self) -> bool:
        # Note: Arduino setup is now handled differently in HardwareCoordinator
        # These methods are deprecated
        log.warning(
            "hardware_status_view_model.arduino_deprecated",
            message="Direct Arduino access via HardwareCoordinator is deprecated.",
        )
        return False

    def log_arduino_event(self, message: str) -> None:
        # Deprecated - logging moved to SessionCoordinator
        pass

    def on_arduino_status_change(self, connected: bool, port: str | None) -> None:
        # Deprecated - status handling moved to SessionCoordinator
        pass

    def on_arduino_command_sent(self, command: int, success: bool, source: str) -> None:
        # Deprecated - command handling moved to SessionCoordinator
        pass

    def _get_arduino_manager(self):
        # Lazy init if needed, though passed in bootstrap
        return self.arduino_manager

    def _shutdown_arduino_manager(self) -> None:
        try:
            if self.arduino_manager:
                self.arduino_manager.shutdown()
        # except Exception justified: serial hardware shutdown — cleanup must not propagate
        except Exception as e:
            log.warning("controller.arduino.shutdown_failed", error=str(e))
        self.arduino_manager = None
        self.arduino = None

    # --- Model / Weights ---

    def get_all_weight_names(self) -> list[str]:
        if self.model_service:
            return self.model_service.get_all_weight_names()
        return []

    def get_weight_details(self, weight_name: str) -> dict[str, Any] | None:
        """Return metadata for a registered weight, if available."""
        if self.model_service:
            return self.model_service.get_weight_details(weight_name)
        return None

    def get_weight_names_for_slot(self, method: str, target: str) -> list[str]:
        """Return candidate weights for a specific (method, target) slot.

        Exact `(method, target)` matches are preferred. If none exist, fall back
        to any weight of the requested method so the UI never becomes empty when
        a weight still needs reclassification.
        """
        exact_matches: list[str] = []
        fallback_matches: list[str] = []
        for weight_name in self.get_all_weight_names():
            details = self.get_weight_details(weight_name) or {}
            if details.get("type") != method:
                continue
            fallback_matches.append(weight_name)
            if details.get("target") == target:
                exact_matches.append(weight_name)
        return exact_matches or fallback_matches

    # Slot summary used by the main-window status panel and the project tab.
    # Returns one entry per (method, target) slot. ``scope="project"`` filters
    # to the two slots actually consumed by runtime processing of the open
    # project, picked from ``settings.model_selection.{aquarium,animal}_method``.
    _SLOT_LABELS: ClassVar[dict[tuple[str, str], tuple[str, str, str]]] = {
        ("det", "aquarium"): ("🐠 Aquário (det)", "det", "aquarium"),
        ("seg", "aquarium"): ("🐠 Aquário (seg)", "seg", "aquarium"),
        ("det", "zebrafish"): ("🐟 Animal (det)", "det", "zebrafish"),
        ("seg", "zebrafish"): ("🐟 Animal (seg)", "seg", "zebrafish"),
    }

    def get_default_weights_summary(
        self, *, scope: str = "global"
    ) -> list[tuple[str, str, str, str | None]]:
        """Return the (method, target) default-slot summary.

        Each entry is ``(label, method, target, weight_name_or_None)``.

        - ``scope="global"`` lists all 4 slots.
        - ``scope="project"`` returns only the 2 slots that runtime detection
          will actually consult, derived from
          ``settings.model_selection.aquarium_method`` and ``animal_method``.
          Falls back to the full 4-slot view when settings are unavailable.
        """
        wm = self.weight_manager
        all_slots = list(self._SLOT_LABELS.values())

        if scope == "project":
            try:
                model_sel = self.settings.model_selection
                aquarium_method = getattr(model_sel, "aquarium_method", None)
                animal_method = getattr(model_sel, "animal_method", None)
            # except Exception justified: settings may be a mock during tests.
            except Exception:
                aquarium_method = None
                animal_method = None
            if aquarium_method and animal_method:
                all_slots = [
                    self._SLOT_LABELS[(aquarium_method, "aquarium")],
                    self._SLOT_LABELS[(animal_method, "zebrafish")],
                ]

        result: list[tuple[str, str, str, str | None]] = []
        for label, method, target in all_slots:
            name: str | None = None
            if wm is not None:
                got, _ = wm.get_default_weight_for(method, target)
                name = got
            result.append((label, method, target, name))
        return result

    def get_openvino_status(self) -> str:
        return self.model_service.get_openvino_status(
            weight_name=self.active_weight_name or "", use_openvino=self.use_openvino
        )

    def get_openvino_cache_status(self, weight_name: str | None = None) -> dict:
        if not weight_name:
            weight_name = self.active_weight_name
        if self.model_service:
            return self.model_service.check_openvino_conversion_status(weight_name or "")
        return {"status": "unknown"}

    def set_active_weight(self, name: str | None, dialog=None):
        return self.ui_state_controller.set_active_weight(name, dialog)

    def set_openvino_usage(self, use_openvino: bool, dialog=None, device: str | None = None):
        return self.ui_state_controller.set_openvino_usage(use_openvino, dialog, device=device)

    def update_openvino_status(self, dialog=None):
        return self.ui_state_controller.update_openvino_status(dialog)

    def load_new_weight(self, **kwargs):
        self.ui_state_controller.load_new_weight(**kwargs)

    def add_new_weight(
        self, path: Path | str, set_as_default: bool, weight_type: str | None = None
    ):
        self.ui_state_controller.add_new_weight(path, set_as_default, weight_type)

    def delete_weight(self, name: str):
        self.ui_state_controller.delete_weight(name)

    def run_model_diagnostic(self, config: dict):
        # Phase 4.9: Redirect to ModelDiagnosticsCoordinator
        if self.model_diagnostics_coordinator:
            # Inject active weight name into config so coordinator doesn't depend on
            # WeightManager state
            config["active_weight_name"] = self.active_weight_name
            self.model_diagnostics_coordinator.run_model_diagnostic(config)

    def handle_request_weight_file(self):
        from tkinter import filedialog

        file_path = filedialog.askopenfilename(
            title="Carregar Novo Peso", filetypes=[("Modelos YOLO/OpenVINO", "*.pt *.onnx *.xml")]
        )
        if file_path:
            self.ui_state_controller.load_new_weight(filepath=file_path)

    # --- Model Default Slots & Maintenance (4-target architecture) ---

    def set_default_weight_for(self, name: str, *, method: str, target: str) -> bool:
        """Mark ``name`` as default for the (method, target) slot."""
        if not self.weight_manager:
            return False
        return self.weight_manager.set_default_weight_for(name, method=method, target=target)

    def reclassify_weight_target(self, name: str, target: str) -> bool:
        """Update only the ``target`` field of an existing weight."""
        if not self.weight_manager:
            return False
        return self.weight_manager.set_weight_target(name, target)

    def clear_openvino_cache(self, name: str | None = None) -> dict[str, list[str]]:
        """Wipe OpenVINO cache for ``name`` (or all weights when ``None``).

        Returns the underlying ``WeightManager.clear_openvino_cache`` report
        ``{"cleared": [...], "locked": [...], "orphans_locked": [...]}``
        so the UI can warn about locked files (typically caused by the
        running detector still holding the .xml/.bin open).
        """
        if not self.weight_manager:
            return {"cleared": [], "locked": [], "orphans_locked": []}
        report = self.weight_manager.clear_openvino_cache(name)
        log.info(
            "hardware_vm.openvino_cache.cleared",
            name=name,
            cleared=len(report["cleared"]),
            locked=len(report["locked"]),
            orphans_locked=len(report["orphans_locked"]),
        )
        return report

    def rescan_weights_folder(self) -> int:
        """Re-run discovery against the configured weights folder."""
        if not self.weight_manager:
            return 0
        added = self.weight_manager.rescan_source_folder()
        log.info("hardware_vm.weights.rescan", added=added)
        return added

    def reset_weights_registry(self) -> int:
        """Wipe ``weights_config.json`` and rebuild it from defaults."""
        if not self.weight_manager:
            return 0
        count = self.weight_manager.reset_registry()
        log.info("hardware_vm.weights.registry_reset", count=count)
        return count

    def validate_weight_files(self) -> dict[str, bool]:
        """Return ``{name: exists}`` for every registered weight."""
        if not self.weight_manager:
            return {}
        return self.weight_manager.validate_weight_files()

    def force_benchmark(self) -> dict[str, Any] | None:
        """Re-run the hardware benchmark from scratch (force_rerun=True).

        Runs synchronously on the calling thread — callers that invoke this
        from the UI should schedule it on a worker thread and re-route the
        result back via ``root.after(0, ...)``. Returns the benchmark result
        as a dict for easy display, or ``None`` on failure.
        """
        try:
            from zebtrack.utils.hardware_benchmark import get_or_run_benchmark

            result = get_or_run_benchmark(force_rerun=True, quick_mode=True)
        # except Exception justified: hardware probing — failures must not crash UI.
        except Exception as e:
            log.error("hardware_vm.benchmark.force_failed", error=str(e))
            return None

        rec = result.recommendation
        return {
            "backend": rec.backend if rec else None,
            "device_live": rec.device_live if rec else None,
            "device_batch": rec.device_batch if rec else None,
            "fps_live": getattr(rec, "estimated_fps_live", 0.0) if rec else 0.0,
            "precision": rec.openvino_precision if rec else None,
        }

    def convert_weight_to_openvino(self, name: str) -> str | None:
        """Trigger OpenVINO export for ``name`` synchronously.

        Returns the absolute path to the converted model directory, or
        ``None`` on failure. Callers from the UI must schedule this on a
        worker thread to avoid blocking Tk.
        """
        if not self.weight_manager:
            return None
        try:
            return self.weight_manager.convert_to_openvino(name)
        # except Exception justified: PyTorch/OpenVINO export — surface error gracefully.
        except Exception as e:
            log.error("hardware_vm.openvino.convert_failed", name=name, error=str(e))
            return None

    # --- Recording / Live Session ---

    def start_live_camera_analysis(self, camera_index: int | None = None) -> Any:
        if self.live_camera_session_coordinator:
            return self.live_camera_session_coordinator.start_live_camera_analysis(camera_index)
        return None

    def start_live_project_session(
        self,
        day: int,
        group: str,
        subject: str,
        duration_s: float | None = None,
    ) -> Any:
        if self.live_camera_session_coordinator:
            return self.live_camera_session_coordinator.start_live_project_session(
                day=day, group=group, subject=subject, duration_s=duration_s
            )
        return None

    def start_live_session(self, **kwargs: Any) -> None:
        """Start a live session (delegates to LiveCameraSessionCoordinator)."""
        if self.live_camera_session_coordinator:
            self.live_camera_session_coordinator.start_live_session(**kwargs)

    def start_recording(self, **kwargs: Any) -> None:
        # Phase 4.7: Delegates to RecordingSessionCoordinator
        if self.recording_session_coordinator:
            self.recording_session_coordinator.start_recording(**kwargs)

    def stop_recording(self) -> None:
        # Phase 4.7: Delegates to RecordingSessionCoordinator
        if self.recording_session_coordinator:
            self.recording_session_coordinator.stop_recording()

    def toggle_recording(self) -> None:
        if self.recording_service and self.recording_service.is_recording:
            self.stop_recording()
        else:
            self.start_recording()

    @property
    def recording_service(self) -> Any | None:
        # Return Any | None because types might be circular or loaded dynamically
        if self._recording_service:
            return self._recording_service
        # Phase 4.7: Get from recording_session_coordinator
        return getattr(self.recording_session_coordinator, "recording_service", None)

    @recording_service.setter
    def recording_service(self, value: Any | None) -> None:
        self._recording_service = value
        # Phase 4.7: Removed forwarding to dead recording_coordinator
