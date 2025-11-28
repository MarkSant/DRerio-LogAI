from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from zebtrack.core.application_bootstrapper import BootstrapResult
    from zebtrack.core.dependency_container import MainViewModelDependencies
    from zebtrack.core.detector import Detector

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
    ):
        self.detector_service = dependencies.detector_service
        self.model_service = dependencies.model_service
        self.hardware_coordinator = dependencies.hardware_coordinator
        self.detector_coordinator = bootstrap_result.legacy_coordinators.get("detector_coordinator")
        self.arduino_manager = bootstrap_result.arduino_manager
        self.weight_manager = dependencies.weight_manager
        self.session_coordinator = dependencies.session_coordinator
        self.ui_state_controller = bootstrap_result.ui_state_controller
        self.model_diagnostics_orchestrator = bootstrap_result.model_diagnostics_orchestrator
        self.recording_session_orchestrator = bootstrap_result.recording_session_orchestrator
        self.recording_coordinator = dependencies.recording_coordinator
        self.state_manager = dependencies.state_manager
        self.settings = dependencies.settings_obj

        self.ui_event_bus = event_bus

        self.arduino = None  # Initialized later via setup
        self.camera = None
        self.active_frame_source = None

        # Bootstrapped values
        self.active_weight_name = bootstrap_result.active_weight_name
        self.use_openvino = bootstrap_result.use_openvino

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

    def setup_detector(self, temp_animal_method: str | None = None) -> bool:
        success, _ = self.detector_coordinator.setup_detector(
            animal_method=temp_animal_method,
            use_openvino=self.use_openvino,
            active_weight_name=self.active_weight_name,
        )
        return success

    def update_detector_parameters(self, params: dict, **kwargs) -> bool:
        if self.detector_coordinator:
            return self.detector_coordinator.update_detector_parameters(params, **kwargs)
        return False

    def get_current_detector_parameters(self) -> dict:
        if self.detector_coordinator:
            return self.detector_coordinator.get_detector_parameters()
        return {}

    def restore_detector_defaults(self, scope: str = "global") -> bool:
        if not self.detector_coordinator:
            return False

        if scope == "global":
            factory_defaults = self.detector_coordinator.get_factory_detector_parameters()
            return self.detector_coordinator.update_detector_parameters(
                params=factory_defaults, scope="global", reset_overrides=True
            )
        elif scope == "project":
            return self.detector_coordinator.update_detector_parameters(
                params={}, scope="project", reset_overrides=True
            )
        return False

    # --- Arduino ---

    def setup_arduino(self) -> bool:
        success = self.hardware_coordinator.setup_arduino()
        self.arduino = self.hardware_coordinator.arduino
        self.arduino_manager = self.hardware_coordinator.arduino_manager
        return success

    def log_arduino_event(self, message: str):
        self.hardware_coordinator.log_arduino_event(message)

    def on_arduino_status_change(self, connected: bool, port: str | None):
        self.hardware_coordinator.on_arduino_status_change(connected, port)

    def on_arduino_command_sent(self, command: int, success: bool, source: str):
        self.hardware_coordinator.on_arduino_command_sent(command, success, source)

    def _get_arduino_manager(self):
        # Lazy init if needed, though passed in bootstrap
        return self.arduino_manager

    def _shutdown_arduino_manager(self):
        if self.arduino_manager:
            try:
                self.arduino_manager.shutdown()
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
            weight_name=self.active_weight_name, use_openvino=self.use_openvino
        )

    def get_openvino_cache_status(self, weight_name: str | None = None) -> dict:
        if not weight_name:
            weight_name = self.active_weight_name
        if self.model_service:
            return self.model_service.check_openvino_conversion_status(weight_name)
        return {"status": "unknown"}

    def set_active_weight(self, name: str | None, dialog=None):
        return self.ui_state_controller.set_active_weight(name, dialog)

    def set_openvino_usage(self, use_openvino: bool, dialog=None):
        return self.ui_state_controller.set_openvino_usage(use_openvino, dialog)

    def update_openvino_status(self, dialog=None):
        return self.ui_state_controller.update_openvino_status(dialog)

    def load_new_weight(self, **kwargs):
        self.ui_state_controller.load_new_weight(**kwargs)

    def add_new_weight(self, path: str, set_as_default: bool, weight_type: str | None = None):
        self.ui_state_controller.add_new_weight(path, set_as_default, weight_type)

    def delete_weight(self, name: str):
        self.ui_state_controller.delete_weight(name)

    def manage_weights(self):
        self.ui_state_controller.manage_weights()

    def run_model_diagnostic(self, config: dict):
        if self.model_diagnostics_orchestrator:
            self.model_diagnostics_orchestrator.run_model_diagnostic(config)

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

    def start_live_camera_analysis(self, camera_index: int | None = None):
        return self.session_coordinator.start_live_camera_analysis(camera_index)

    def start_live_project_session(self):
        return self.session_coordinator.start_live_project_session()

    def start_recording(self, **kwargs):
        if self.recording_session_orchestrator:
            self.recording_session_orchestrator.start_recording(**kwargs)

    def stop_recording(self):
        if self.recording_session_orchestrator:
            self.recording_session_orchestrator.stop_recording()

    def toggle_recording(self):
        if self.recording_service and self.recording_service.is_recording:
            self.stop_recording()
        else:
            self.start_recording()

    @property
    def recording_service(self):
        if self._recording_service:
            return self._recording_service
        return getattr(self.session_coordinator, "recording_service", None)

    @recording_service.setter
    def recording_service(self, value):
        self._recording_service = value
        if self.recording_coordinator:
            self.recording_coordinator.recording_service = value
