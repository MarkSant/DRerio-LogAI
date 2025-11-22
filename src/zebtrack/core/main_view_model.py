"""Main application view model orchestrating the ZebTrack-AI application.

Coordinates all core services, manages application state, handles user interactions,
and orchestrates video processing workflows with dependency injection.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

# Legacy imports kept for type hinting in signatures
from zebtrack.core.application_bootstrapper import BootstrapResult
from zebtrack.core.dependency_container import MainViewModelDependencies
from zebtrack.core.detector import Detector
from zebtrack.core.processing_mode import ProcessingMode
from zebtrack.core.recording_service import RecordingService
from zebtrack.core.state_manager import StateCategory
from zebtrack.io.arduino_manager import ArduinoManager
from zebtrack.ui.events import Events

if TYPE_CHECKING:
    pass

log = structlog.get_logger()


class MainViewModel:
    """
    Main View Model for ZebTrack-AI application.

    Refactored to follow Single Responsibility Principle by delegating initialization
    to ApplicationBootstrapper.

    This class focuses on:
    - UI-facing state management (via StateManager)
    - Command handling via event bus
    - Orchestrating services (ProjectService, AnalysisService)
    - Hardware setup (detector, Arduino)
    - Recording control
    """

    def __init__(
        self,
        dependencies: MainViewModelDependencies,
        bootstrap_result: BootstrapResult,
    ):
        """Initialize MainViewModel with pre-bootstrapped components.

        Args:
            dependencies: Injected dependencies container
            bootstrap_result: Result of ApplicationBootstrapper initialization
        """
        # 1. Extract core dependencies
        self._extract_dependencies(dependencies)

        # 2. Assign bootstrap result components
        self._assign_bootstrap_result(bootstrap_result)

        # 3. Subscribe to state changes
        self._subscribe_to_state()

        # 4. Setup event handlers mapping
        self._EVENT_METHOD_MAPPING = {
            Events.RECORDING_START: ("start_recording", [], "no_params"),
            Events.RECORDING_STOP: ("stop_recording", [], "no_params"),
            Events.RECORDING_TOGGLE: ("toggle_recording", [], "no_params"),
            Events.PROJECT_CREATE: ("create_project_workflow", ["wizard_data"], "kwargs_all"),
            Events.PROJECT_OPEN: ("open_project_workflow", ["project_path"], "positional"),
            Events.PROJECT_CLOSE: ("close_project", [], "no_params"),
            Events.PROJECT_PROCESS_VIDEOS: ("start_project_processing_workflow", [], "no_params"),
            Events.PROJECT_ADD_VIDEOS: ("add_videos_to_project", [], "no_params"),
        }

        log.info("main_view_model.initialized", source="init")

    def _extract_dependencies(self, dependencies: MainViewModelDependencies):
        """Extract and assign injected dependencies."""
        self.root = dependencies.root
        self.settings = dependencies.settings_obj
        self._test_sync_event = dependencies.test_sync_event

        self.state_manager = dependencies.state_manager
        self.project_manager = dependencies.project_manager
        self.weight_manager = dependencies.weight_manager
        self.model_service = dependencies.model_service
        self.detector_service = dependencies.detector_service
        self.video_processing_service = dependencies.video_processing_service
        self.project_workflow_service = dependencies.project_workflow_service
        self.ui_coordinator = dependencies.ui_coordinator

        # Super coordinators
        self.project_lifecycle_coordinator = dependencies.project_lifecycle_coordinator
        self.hardware_coordinator = dependencies.hardware_coordinator
        self.processing_coordinator = dependencies.processing_coordinator
        self.session_coordinator = dependencies.session_coordinator

        # Legacy dependencies
        self.recording_coordinator = dependencies.recording_coordinator
        self._live_camera_service_param = dependencies.live_camera_service

        if self._test_sync_event is not None:
            self.state_manager.subscribe_all(self._on_state_change_for_test)

    def _assign_bootstrap_result(self, result: BootstrapResult):
        """Assign components created by ApplicationBootstrapper."""
        # Services
        self.project_service = result.project_service
        self.analysis_service = result.analysis_service
        self.video_classification_service = result.video_classification_service
        self.video_selection_service = result.video_selection_service
        self.video_validation_service = result.video_validation_service
        self.batch_configuration_service = result.batch_configuration_service
        self.thread_coordinator = result.thread_coordinator
        self.dialog_coordinator = result.dialog_coordinator
        self.event_dispatcher = result.event_dispatcher

        # Hardware & Runtime
        self.active_weight_name = result.active_weight_name
        self.use_openvino = result.use_openvino
        self._hardware_summary = result.hardware_summary
        self._recommended_backend = result.recommended_backend
        self.recorder = result.recorder
        self.arduino_manager = result.arduino_manager

        # Queues & Events
        self.frame_queue = result.frame_queue
        self.video_queue = result.video_queue
        self.program_exit_event = result.program_exit_event
        self.cancel_event = result.cancel_event

        # Legacy Orchestrators
        self.video_processing_orchestrator = result.video_processing_orchestrator
        self.analysis_orchestrator = result.analysis_orchestrator
        self.recording_session_orchestrator = result.recording_session_orchestrator
        self.project_orchestrator = result.project_orchestrator
        self.ui_state_controller = result.ui_state_controller
        self.model_diagnostics_orchestrator = result.model_diagnostics_orchestrator
        self.zone_arena_orchestrator = result.zone_arena_orchestrator
        self.processing_config_orchestrator = result.processing_config_orchestrator
        self.calibration_orchestrator = result.calibration_orchestrator

        # Legacy Coordinators
        self.detector_coordinator = result.legacy_coordinators.get("detector_coordinator")
        self.video_orchestrator = result.legacy_coordinators.get("video_orchestrator")
        self.analysis_coordinator = result.legacy_coordinators.get("analysis_coordinator")
        self.project_coordinator = result.legacy_coordinators.get("project_coordinator")
        self.recording_coordinator = result.legacy_coordinators.get("recording_coordinator")
        self.live_camera_coordinator = result.legacy_coordinators.get("live_camera_coordinator")

        # Registry & Adapter
        self.orchestrators = result.orchestrators
        self.project_workflow_adapter = result.project_workflow_adapter

        # Runtime flags
        self._active_processing_mode = ProcessingMode.MULTI_TRACK
        self.processing_thread = None
        self.pending_single_video_analysis = None
        self.processing_worker = None
        self._cancel_feedback_displayed = False
        self.is_capturing_for_video = False
        self.active_frame_source = None
        self.arduino = None # Will be set when manager is initialized
        self.report_results_paths = {}
        self.timed_recording_job = None
        self._pending_external_trigger = None

        # Event bus flag
        self.ui_event_bus = self.event_dispatcher.event_bus
        self._use_event_bus = bool(self.ui_event_bus)

        # Set legacy services if needed (for properties)
        self._recording_service = None

        # NOTE: self.view is NOT assigned here anymore.
        # MainViewModel is decoupled from the concrete View instance.
        # Any remaining self.view usages must be refactored.
        # Only VideoProcessingOrchestrator holds a reference to view (via proxy).

    def _subscribe_to_state(self):
        """Subscribe to state manager updates."""
        self.state_manager.subscribe(StateCategory.PROJECT, self._on_project_state_changed)
        self.state_manager.subscribe(StateCategory.DETECTOR, self._on_detector_state_changed)
        self.state_manager.subscribe(StateCategory.PROCESSING, self._on_processing_state_changed)

    # =========================================================================
    # Phase 3: Delegation Methods (TEMPORARY - for backward compatibility)
    # =========================================================================

    def set_active_weight(self, name: str | None, dialog=None):
        return self.ui_state_controller.set_active_weight(name, dialog)

    def set_openvino_usage(self, use_openvino: bool, dialog=None):
        return self.ui_state_controller.set_openvino_usage(use_openvino, dialog)

    def update_openvino_status(self, dialog=None):
        return self.ui_state_controller.update_openvino_status(dialog)

    def close_project(self):
        return self.project_lifecycle_coordinator.close_project()

    def _setup_zones_from_project(self):
        return self.project_orchestrator._setup_zones_from_project()

    def open_project_workflow(self, project_path):
        return self.project_orchestrator.open_project_workflow(project_path)

    # =========================================================================
    # Application Lifecycle
    # =========================================================================

    def run(self):
        """Start the Tkinter main event loop."""
        self.root.mainloop()

    def bind_events(self):
        """Binds all UI events."""
        if self._use_event_bus:
            self._register_event_handlers()
            self.video_processing_orchestrator.register_event_handlers()

    # ==================== Properties ====================

    @property
    def recording_service(self) -> RecordingService | None:
        if self._recording_service:
            return self._recording_service
        return getattr(self.session_coordinator, "recording_service", None)

    @recording_service.setter
    def recording_service(self, value: RecordingService | None) -> None:
        self._recording_service = value
        if self.recording_coordinator:
            self.recording_coordinator.recording_service = value

    @property
    def _global_model_defaults(self) -> dict:
        detector_state = self.state_manager.get_detector_state()
        return {
            "active_weight": detector_state.active_weight_name,
            "use_openvino": detector_state.use_openvino,
        }

    @property
    def detector(self) -> Detector | None:
        return self.detector_service.detector

    @detector.setter
    def detector(self, value: Detector | None) -> None:
        self.detector_service.detector = value

    @detector.deleter
    def detector(self) -> None:
        self.detector_service.detector = None

    @property
    def detector_initialized(self) -> bool:
        return self.state_manager.get_detector_state().detector_initialized

    @property
    def is_processing(self) -> bool:
        return self.state_manager.get_processing_state().is_processing

    # ==================== Event Handlers ====================

    def _on_state_change_for_test(self, category, key, old, new):
        if self._test_sync_event is not None:
            self._test_sync_event.set()

    def _on_project_state_changed(self, category, key, old, new):
        if not self.ui_event_bus:
            return
        if key == "active_zone_video" or key == "project_data":
            zone_data = self.project_manager.get_zone_data()
            self.ui_event_bus.publish_event(Events.UI_REDRAW_ZONES, {"zone_data": zone_data})
            self.ui_event_bus.publish_event(Events.UI_UPDATE_ZONE_LIST, {"zone_data": zone_data})

    def _on_detector_state_changed(self, category, key, old, new):
        if not self.ui_event_bus:
            return
        if key == "active_weight_name":
            self.ui_event_bus.publish_event(Events.UI_SET_ACTIVE_WEIGHT, {"weight_name": new})
        elif key == "use_openvino":
            self.ui_event_bus.publish_event(Events.UI_UPDATE_OPENVINO_CHECKBOX, {"is_checked": new})
            self.ui_state_controller.update_openvino_status()

    def _on_processing_state_changed(self, category, key, old, new):
        if key == "is_processing":
            if new:
                self.ui_event_bus.publish_event(Events.UI_NAVIGATE_TO_ANALYSIS_VIEW)
            else:
                # Logic for stopping analysis view is handled by
                # processing worker completion callback
                pass
        elif key == "cancel_requested" and new:
            self.ui_state_controller._show_cancel_feedback()

    def get_openvino_status(self) -> str:
        return self.model_service.get_openvino_status(
            weight_name=self.active_weight_name, use_openvino=self.use_openvino
        )

    def on_close(self):
        if self.dialog_coordinator.confirm_exit():
            self.join_threads()
            self.root.destroy()

    def join_threads(self):
        log.info("controller.shutdown.start")
        self.program_exit_event.set()
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join()

        capture_thread = getattr(self, "capture_thread", None)
        if capture_thread and capture_thread.is_alive():
            capture_thread.join()

        if hasattr(self, "camera") and self.camera:
            self.camera.release()

        self._shutdown_arduino_manager()
        log.info("controller.shutdown.complete")

    def _get_arduino_manager(self) -> ArduinoManager:
        if self.arduino_manager is None:
            self.arduino_manager = ArduinoManager(self)
        return self.arduino_manager

    def _shutdown_arduino_manager(self):
        if self.arduino_manager:
            try:
                self.arduino_manager.shutdown()
            except Exception as e:
                log.warning("controller.arduino.shutdown_failed", error=str(e))
            self.arduino_manager = None
        self.arduino = None

    def _create_event_dispatcher(self, event_name: str):
        if event_name not in self._EVENT_METHOD_MAPPING:
            return lambda data: None

        method_name, param_names, mode = self._EVENT_METHOD_MAPPING[event_name]

        def dispatcher(data: dict) -> None:
            method = getattr(self, method_name, None)
            if not method:
                return

            if mode == "no_params":
                method()
            elif mode == "kwargs_all":
                method(**data)
            elif mode == "kwargs_get":
                kwargs = {param: data.get(param) for param in param_names}
                method(**kwargs)
            elif mode == "positional":
                args = [data[param] for param in param_names]
                method(*args)
            elif mode == "positional_optional":
                args = [data.get(param) for param in param_names]
                method(*args)

        return dispatcher

    def _register_event_handlers(self) -> None:
        if not self.ui_event_bus:
            return

        for event_name in self._EVENT_METHOD_MAPPING.keys():
            dispatcher = self._create_event_dispatcher(event_name)
            self.ui_event_bus.subscribe(event_name, dispatcher)

        self.ui_event_bus.subscribe(
            Events.PROJECT_MANAGER_REPLACED,
            self._handle_project_manager_replaced,
        )

    def _handle_project_manager_replaced(self, data: dict):
        new_manager = data.get("new_manager")
        if not new_manager:
            return

        services_to_update = [
            ("project_workflow_service", self.project_workflow_service),
            ("detector_service", self.detector_service),
            ("video_processing_service", self.video_processing_service),
            ("recording_service", self.recording_service),
            ("video_orchestrator", self.video_orchestrator),
            ("analysis_coordinator", self.analysis_coordinator),
            ("hardware_coordinator", self.hardware_coordinator),
            ("processing_coordinator", self.processing_coordinator),
        ]

        orchestrators_to_update = [
            ("video_processing_orchestrator", self.video_processing_orchestrator),
            ("analysis_orchestrator", self.analysis_orchestrator),
            ("calibration_orchestrator", self.calibration_orchestrator),
            ("recording_session_orchestrator", self.recording_session_orchestrator),
            ("processing_config_orchestrator", self.processing_config_orchestrator),
        ]

        for name, service in services_to_update + orchestrators_to_update:
            if service and hasattr(service, "_on_project_manager_replaced"):
                try:
                    service._on_project_manager_replaced(data)
                except Exception:
                    pass
            elif service and hasattr(service, "project_manager"):
                try:
                    service.project_manager = new_manager
                except Exception:
                    pass

    def log_arduino_event(self, message: str):
        self.hardware_coordinator.log_arduino_event(message)

    def on_arduino_status_change(self, connected: bool, port: str | None):
        self.hardware_coordinator.on_arduino_status_change(connected, port)

    def on_arduino_command_sent(self, command: int, success: bool, source: str):
        self.hardware_coordinator.on_arduino_command_sent(command, success, source)

    def create_project_workflow(self, **wizard_data):
        return self.project_orchestrator.create_project_workflow(**wizard_data)

    def start_single_video_workflow(self, video_path, config):
        video_path = Path(video_path) if isinstance(video_path, str) else video_path

        self.project_manager.set_active_zone_video(str(video_path))

        use_openvino = config.get("use_openvino", self.settings.model_selection.use_openvino)
        self.use_openvino = use_openvino

        if not self.detector:
             temp_animal_method = config.get("animal_method")
             if not self.setup_detector(temp_animal_method):
                 return

        # UI Event dispatched here, listened by EventDispatcher in GUI
        self.ui_event_bus.publish_event(
            "ui:setup_zone_definition_for_single_video",
            {"video_path": video_path, "config": config},
        )

    def cancel_current_analysis(self) -> None:
        worker_running = bool(self.processing_worker and self.processing_worker.is_running)
        thread_running = bool(self.processing_thread and self.processing_thread.is_alive())

        if not worker_running and not thread_running:
            return

        self.cancel_event.set()
        self.state_manager.update_processing_state(
            source="controller.cancel_current_analysis",
            cancel_requested=True,
        )
        # Update status via event
        self.ui_event_bus.publish_event(
            Events.UI_SET_STATUS, {"message": "Cancelando análise em andamento..."}
        )
        self.ui_state_controller._show_cancel_feedback()

        def _await_shutdown():
            if self.processing_worker and self.processing_worker.is_running:
                self.processing_worker.cancel()
            elif self.processing_thread and self.processing_thread.is_alive():
                self.processing_thread.join(timeout=5.0)

        threading.Thread(target=_await_shutdown, daemon=True).start()

    def _process_single_video(self, **kwargs):
        self.video_processing_service.detector = self.detector
        self.video_processing_service.recorder = self.recorder
        self.video_processing_service.cancel_event = self.cancel_event
        return self.video_processing_service.process_single_video(**kwargs)

    def apply_project_settings_to_batch(self, videos: list):
        return self.batch_configuration_service.apply_settings(videos)

    def _prepare_results_directory(self, results_dir: str):
        self.video_processing_service._prepare_results_directory(results_dir)

    def generate_parquet_summaries(self, video_paths: list[str]):
        self.analysis_coordinator.generate_parquet_summaries(
            video_paths, processing_thread_ref=self.processing_thread
        )

    def setup_detector(self, temp_animal_method: str | None = None) -> bool:
        success, _ = self.detector_coordinator.setup_detector(
            animal_method=temp_animal_method,
            use_openvino=self.use_openvino,
            active_weight_name=self.active_weight_name,
        )
        return success

    def setup_arduino(self) -> bool:
        success = self.hardware_coordinator.setup_arduino()
        self.arduino = self.hardware_coordinator.arduino
        self.arduino_manager = self.hardware_coordinator.arduino_manager
        return success

    def _publish_processing_mode(self, source="unknown", force=False):
        return self.ui_state_controller._publish_processing_mode(source, force)

    def _determine_processing_intervals(self, single_video_config):
        p_data = self.project_manager.project_data
        a_int = 10
        d_int = 10
        if single_video_config:
            a_int = single_video_config.get("analysis_interval", 10)
            d_int = single_video_config.get("display_interval", 10)
        elif p_data:
            a_int = p_data.get("analysis_interval_frames", 10)
            d_int = p_data.get("display_interval_frames", 10)
        return a_int, d_int

    @contextmanager
    def _temporary_single_animal_mode(self, single_video_config):
        yield
