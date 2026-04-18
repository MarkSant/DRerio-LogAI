from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

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

    def manage_weights(self):
        self.ui_state_controller.manage_weights()

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

    def handle_open_manage_weights(self, root):
        from zebtrack.ui.dialogs.manage_weights_dialog import ManageWeightsDialog

        ManageWeightsDialog(root, self.ui_state_controller)

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
