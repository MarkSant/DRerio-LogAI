"""Main application view model orchestrating the ZebTrack-AI application.

Coordinates all core services, manages application state, handles user interactions,
and orchestrates video processing workflows with dependency injection.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

import structlog

# Legacy imports kept for type hinting in signatures
from zebtrack.core.application_bootstrapper import BootstrapResult
from zebtrack.core.dependency_container import MainViewModelDependencies
from zebtrack.core.detector import Detector
from zebtrack.core.processing_mode import ProcessingMode
from zebtrack.core.recording_service import RecordingService
from zebtrack.core.state_manager import StateCategory
from zebtrack.core.viewmodels.analysis_control_view_model import AnalysisControlViewModel
from zebtrack.core.viewmodels.hardware_status_view_model import HardwareStatusViewModel

# New ViewModels
from zebtrack.core.viewmodels.project_view_model import ProjectViewModel
from zebtrack.ui.events import Events

if TYPE_CHECKING:
    pass

log = structlog.get_logger()


class MainViewModel:
    """
    Main View Model for ZebTrack-AI application.

    Refactored to follow Single Responsibility Principle by delegating initialization
    to ApplicationBootstrapper and functionality to specialized ViewModels:
    - ProjectViewModel: Project management
    - AnalysisControlViewModel: Analysis control
    - HardwareStatusViewModel: Hardware/Model status
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
        # 1. Extract core dependencies (kept for facade/legacy access if needed)
        self._extract_dependencies(dependencies)

        # 2. Assign bootstrap result components
        self._assign_bootstrap_result(bootstrap_result)

        # Event bus flag
        self.ui_event_bus = self.event_dispatcher.event_bus
        self._use_event_bus = bool(self.ui_event_bus)
        
        # Debug: Log event bus ID for comparison with GUI
        log.info(
            "main_view_model.init.event_bus_setup",
            ui_event_bus_id=id(self.ui_event_bus) if self.ui_event_bus else None,
            deps_event_bus_id=id(dependencies.event_bus) if dependencies.event_bus else None,
            same_bus=self.ui_event_bus is dependencies.event_bus if self.ui_event_bus else "N/A",
        )

        # 3. Initialize Sub-ViewModels
        self.project_vm = ProjectViewModel(dependencies, bootstrap_result, self.ui_event_bus)
        self.analysis_vm = AnalysisControlViewModel(
            dependencies, bootstrap_result, self.ui_event_bus
        )
        self.hardware_vm = HardwareStatusViewModel(
            dependencies, bootstrap_result, self.ui_event_bus
        )

        # 4. Subscribe to state changes
        self._subscribe_to_state()

        # 5. Setup event handlers mapping (Delegating to Sub-VMs)
        self._EVENT_METHOD_MAPPING = {
            Events.RECORDING_START: (self.hardware_vm.start_recording, [], "no_params"),
            Events.RECORDING_STOP: (self.hardware_vm.stop_recording, [], "no_params"),
            Events.RECORDING_TOGGLE: (self.hardware_vm.toggle_recording, [], "no_params"),
            Events.PROJECT_CREATE: (
                self.project_vm.create_project_workflow,
                ["wizard_data"],
                "kwargs_all",
            ),
            Events.PROJECT_OPEN: (
                self.project_vm.open_project_workflow,
                ["project_path"],
                "positional",
            ),
            Events.PROJECT_CLOSE: (self.project_vm.close_project, [], "no_params"),
            Events.PROJECT_PROCESS_VIDEOS: (
                self.analysis_vm.start_project_processing_workflow,
                [],
                "no_params",
            ),
            Events.PROJECT_ADD_VIDEOS: (self.project_vm.add_videos_to_project, [], "no_params"),
            Events.MODEL_SET_OPENVINO: (self.hardware_vm.set_openvino_usage, [], "kwargs_all"),
            Events.MODEL_SET_WEIGHT: (self.hardware_vm.set_active_weight, [], "kwargs_all"),
            Events.MODEL_RUN_DIAGNOSTIC: (
                self.hardware_vm.run_model_diagnostic,
                ["config"],
                "kwargs_all",
            ),
            Events.UI_REQUEST_WEIGHT_FILE: (
                self.hardware_vm.handle_request_weight_file,
                [],
                "no_params",
            ),
            Events.UI_OPEN_MANAGE_WEIGHTS_DIALOG: (
                self.handle_open_manage_weights,
                [],
                "no_params",
            ),  # Kept here or moved? Moved to HW VM but needs root.
            Events.VIDEO_ANALYZE_SINGLE: (
                self.start_single_video_workflow,
                [],
                "kwargs_all",
            ),  # Facade wrapper due to complexity
            # NOTE: VIDEO_START_SINGLE_PROCESSING is handled by ProcessingCoordinator
            # to avoid duplicate execution (removed from here)
            Events.VIDEO_CANCEL_ANALYSIS: (
                self.analysis_vm.cancel_current_analysis,
                [],
                "no_params",
            ),
            Events.MODEL_ADD_WEIGHT: (self.hardware_vm.add_new_weight, [], "kwargs_all"),
            Events.MODEL_DELETE_WEIGHT: (self.hardware_vm.delete_weight, [], "kwargs_all"),
            Events.MODEL_LOAD_NEW_WEIGHT: (self.hardware_vm.load_new_weight, [], "kwargs_all"),
            Events.MODEL_MANAGE_WEIGHTS: (self.hardware_vm.manage_weights, [], "no_params"),
            Events.ZONE_SAVE_MANUAL_ARENA: (
                self.analysis_vm.save_manual_arena,
                ["polygon_points"],
                "kwargs_get",
            ),
            Events.ZONE_AUTO_DETECT: (self.analysis_vm.auto_detect_zones, [], "kwargs_all"),
            Events.PROJECT_DELETE_ASSET: (
                self.project_vm.handle_delete_project_asset,
                [],
                "kwargs_all",
            ),
            Events.CALIBRATION_COPY_TO_PROJECT: (
                self.project_vm.handle_calibration_copy_to_project,
                [],
                "no_params",
            ),
            Events.CALIBRATION_SAVE_TO_PROJECT: (
                self.project_vm.handle_calibration_save_to_project,
                [],
                "no_params",
            ),
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
        # Note: active_weight_name and use_openvino are now properties that delegate to hardware_vm
        # (initialized in hardware_vm from bootstrap_result values)
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
        self.ui_state_controller = result.ui_state_controller
        # Phase 3A/B/C/D: Removed superseded orchestrators (see BootstrapResult)

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
        self.arduino = None  # Will be set when manager is initialized
        self.report_results_paths = {}
        self.timed_recording_job = None
        self._pending_external_trigger = None
        self._using_project_overrides = False  # Model override flag (managed by orchestrators)

        # Set legacy services if needed (for properties)
        self._recording_service = None

    def _subscribe_to_state(self):
        """Subscribe to state manager updates."""
        self.state_manager.subscribe(StateCategory.PROJECT, self._on_project_state_changed)
        self.state_manager.subscribe(StateCategory.DETECTOR, self._on_detector_state_changed)
        self.state_manager.subscribe(StateCategory.PROCESSING, self._on_processing_state_changed)

    # =========================================================================
    # Facade Methods - Delegating to Sub-ViewModels
    # =========================================================================

    def set_active_weight(self, name: str | None, dialog=None):
        return self.hardware_vm.set_active_weight(name, dialog)

    def set_openvino_usage(self, use_openvino: bool, dialog=None):
        return self.hardware_vm.set_openvino_usage(use_openvino, dialog)

    def update_detector_parameters(self, params: dict, **kwargs) -> bool:
        return self.hardware_vm.update_detector_parameters(params, **kwargs)

    def get_current_detector_parameters(self) -> dict:
        return self.hardware_vm.get_current_detector_parameters()

    def update_openvino_status(self, dialog=None):
        return self.hardware_vm.update_openvino_status(dialog)

    def close_project(self):
        return self.project_vm.close_project()

    def open_project_workflow(self, project_path):
        return self.project_vm.open_project_workflow(project_path)

    def start_live_camera_analysis(self, camera_index: int | None = None):
        return self.hardware_vm.start_live_camera_analysis(camera_index)

    def start_live_project_session(self):
        return self.hardware_vm.start_live_project_session()

    def can_remove_project_asset(self, video_path: str, asset: str) -> tuple[bool, str | None]:
        return self.project_vm.can_remove_project_asset(video_path, asset)

    def save_manual_arena(self, polygon: list[tuple[int, int]]):
        return self.analysis_vm.save_manual_arena(polygon)

    def setup_detector_zones(self):
        """Setup detector zones from project data via ProjectLifecycleCoordinator."""

        def _callback():
            # Get active video and zone data
            active_video = self.project_manager.get_active_zone_video()
            zone_data = self.project_manager.get_zone_data(video_path=active_video)

            # Configure detector
            self.detector_service.configure_zones(zones_data=zone_data)

        self.project_lifecycle_coordinator._setup_zones_from_project(
            setup_detector_zones_callback=_callback
        )

    # =========================================================================
    # Event Handlers delegates (kept for backward compat or event mapping)
    # =========================================================================

    def start_recording(self, **kwargs):
        self.hardware_vm.start_recording(**kwargs)

    def stop_recording(self):
        self.hardware_vm.stop_recording()

    def toggle_recording(self):
        self.hardware_vm.toggle_recording()

    def start_project_processing_workflow(self):
        self.analysis_vm.start_project_processing_workflow()

    def add_videos_to_project(self):
        self.project_vm.add_videos_to_project()

    def run_model_diagnostic(self, config: dict):
        self.hardware_vm.run_model_diagnostic(config)

    def handle_request_weight_file(self):
        self.hardware_vm.handle_request_weight_file()

    def handle_open_manage_weights(self):
        # This requires self.root, passing it to VM
        self.hardware_vm.handle_open_manage_weights(self.root)

    def start_single_video_processing(self, **kwargs):
        self.analysis_vm.start_single_video_processing(**kwargs)

    def auto_detect_zones(self, **kwargs):
        self.analysis_vm.auto_detect_zones(**kwargs)

    def manage_weights(self):
        self.hardware_vm.manage_weights()

    def add_new_weight(self, path: str, set_as_default: bool, weight_type: str | None = None):
        self.hardware_vm.add_new_weight(path, set_as_default, weight_type)

    def delete_weight(self, name: str):
        self.hardware_vm.delete_weight(name)

    def load_new_weight(self, **kwargs):
        self.hardware_vm.load_new_weight(**kwargs)

    def handle_delete_project_asset(self, video_path: str, asset: str):
        self.project_vm.handle_delete_project_asset(video_path, asset)

    def handle_calibration_copy_to_project(self):
        self.project_vm.handle_calibration_copy_to_project()

    def handle_calibration_save_to_project(self):
        self.project_vm.handle_calibration_save_to_project()

    # =========================================================================
    # Complex Workflows (Involving multiple VMs)
    # =========================================================================

    def start_single_video_workflow(self, video_path, config):
        """Delegate to AnalysisControlViewModel but inject dependencies from HardwareVM."""
        self.analysis_vm.start_single_video_workflow(
            video_path, config, detector_vm=self.hardware_vm
        )

    def create_project_workflow(self, **wizard_data):
        return self.project_vm.create_project_workflow(**wizard_data)

    def cancel_current_analysis(self) -> None:
        self.analysis_vm.cancel_current_analysis()

    def apply_project_settings_to_batch(self, videos: list):
        return self.project_vm.apply_project_settings_to_batch(videos)

    def generate_parquet_summaries(self, video_paths: list[str]):
        self.analysis_vm.generate_parquet_summaries(video_paths)

    def setup_detector(self, temp_animal_method: str | None = None) -> bool:
        return self.hardware_vm.setup_detector(temp_animal_method)

    def setup_arduino(self) -> bool:
        return self.hardware_vm.setup_arduino()

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
            self.processing_coordinator.register_event_handlers()

    # ==================== Properties ====================

    @property
    def active_weight_name(self) -> str:
        """Active weight name - delegates to hardware_vm for single source of truth."""
        if hasattr(self, "hardware_vm"):
            return self.hardware_vm.active_weight_name
        return getattr(self, "_active_weight_name", "")

    @active_weight_name.setter
    def active_weight_name(self, value: str):
        if hasattr(self, "hardware_vm"):
            self.hardware_vm.active_weight_name = value
        else:
            self._active_weight_name = value

    @property
    def use_openvino(self) -> bool:
        """OpenVINO usage flag - delegates to hardware_vm for single source of truth."""
        if hasattr(self, "hardware_vm"):
            return self.hardware_vm.use_openvino
        return getattr(self, "_use_openvino", False)

    @use_openvino.setter
    def use_openvino(self, value: bool):
        if hasattr(self, "hardware_vm"):
            self.hardware_vm.use_openvino = value
        else:
            self._use_openvino = value

    @property
    def recording_service(self) -> RecordingService | None:
        if hasattr(self, "hardware_vm"):
            return self.hardware_vm.recording_service
        return getattr(self, "_recording_service", None)

    @recording_service.setter
    def recording_service(self, value: RecordingService | None) -> None:
        if hasattr(self, "hardware_vm"):
            self.hardware_vm.recording_service = value
        else:
            self._recording_service = value

    @property
    def _global_model_defaults(self) -> dict:
        detector_state = self.state_manager.get_detector_state()
        return {
            "active_weight": detector_state.active_weight_name,
            "use_openvino": detector_state.use_openvino,
        }

    @property
    def detector(self) -> Detector | None:
        if hasattr(self, "hardware_vm"):
            return self.hardware_vm.detector
        return getattr(self, "_detector", None)

    @detector.setter
    def detector(self, value: Detector | None) -> None:
        if hasattr(self, "hardware_vm"):
            self.hardware_vm.detector = value
        else:
            self._detector = value

    @detector.deleter
    def detector(self) -> None:
        if hasattr(self, "hardware_vm"):
            self.hardware_vm.detector = None
        else:
            self._detector = None

    @property
    def detector_initialized(self) -> bool:
        if hasattr(self, "hardware_vm"):
            return self.hardware_vm.detector_initialized
        return getattr(self, "_detector", None) is not None

    @property
    def is_processing(self) -> bool:
        return self.analysis_vm.is_processing

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
        log.debug(
            "controller.processing_state_changed",
            key=key,
            old=old,
            new=new,
            has_ui_event_bus=bool(self.ui_event_bus),
        )
        if key == "is_processing":
            if new:
                # Navigate to analysis tab when processing starts
                if self.ui_event_bus:
                    event_name = Events.UI_NAVIGATE_TO_ANALYSIS_VIEW
                    log.info(
                        "controller.navigating_to_analysis_view",
                        event_name=event_name,
                        event_bus_id=id(self.ui_event_bus),
                    )
                    result = self.ui_event_bus.publish_event(event_name)
                    log.info("controller.event_published", result=result)
                else:
                    log.warning("controller.ui_event_bus_not_available")
            else:
                # Logic for stopping analysis view is handled by
                # processing worker completion callback
                pass
        elif key == "cancel_requested" and new:
            self.ui_state_controller._show_cancel_feedback()

    def get_openvino_status(self) -> str:
        if hasattr(self, "hardware_vm"):
            return self.hardware_vm.get_openvino_status()
        return "Status Indisponível (Inicializando)"

    @contextmanager
    def global_calibration_session(self):
        """Context manager for global calibration mode. Delegates to ProjectLifecycleCoordinator."""
        with self.project_lifecycle_coordinator.global_calibration_session(
            get_active_weight_name=lambda: self.active_weight_name,
            get_use_openvino=lambda: self.use_openvino,
        ):
            yield

    @contextmanager
    def project_calibration_session(self):
        """Context manager for project calibration mode.

        Phase 3C: Delegates to ProjectLifecycleCoordinator (supersedes ProjectOrchestrator).
        """
        with self.project_lifecycle_coordinator.project_calibration_session():
            yield

    def on_close(self):
        if self.dialog_coordinator.confirm_exit():
            self.join_threads()
            self.root.destroy()

    def join_threads(self):
        log.info("controller.shutdown.start")

        # Signal all threads to exit
        self.program_exit_event.set()

        # Cancel any active processing before shutdown
        # This ensures ProcessingWorker gets the cancel signal
        self.analysis_vm.cancel_current_analysis()

        # Join ProcessingCoordinator threads (Phase 3 architecture)
        if self.processing_coordinator and self.processing_coordinator.processing_thread:
            if self.processing_coordinator.processing_thread.is_alive():
                log.info("controller.shutdown.joining_processing_coordinator_thread")
                self.processing_coordinator.processing_thread.join(timeout=5.0)

        # Legacy thread join for backward compatibility
        if self.processing_thread and self.processing_thread.is_alive():
            log.info("controller.shutdown.joining_legacy_processing_thread")
            self.processing_thread.join(timeout=5.0)

        capture_thread = getattr(self, "capture_thread", None)
        if capture_thread and capture_thread.is_alive():
            log.info("controller.shutdown.joining_capture_thread")
            capture_thread.join(timeout=5.0)

        camera_release_success = True
        # Check hardware_vm for camera
        camera = getattr(self.hardware_vm, "camera", None)
        # Fallback to self.camera if it was set on MainVM (legacy safety)
        if not camera and hasattr(self, "camera"):
            camera = self.camera

        if camera:
            try:
                camera_release_success = bool(camera.release())
            except Exception as exc:
                camera_release_success = False
                log.error("controller.camera.release_failed", error=str(exc))

        if not camera_release_success:
            log.critical(
                "controller.camera.zombie_detected",
                message="Camera thread did not shut down cleanly",
            )
            if self.ui_event_bus:
                from zebtrack.ui.event_bus_v2 import Event, UIEvents

                self.ui_event_bus.publish(
                    Event(
                        UIEvents.ERROR_OCCURRED,
                        {
                            "title": "Erro Crítico",
                            "message": (
                                "A thread da câmera não foi finalizada corretamente. "
                                "O aplicativo será encerrado."
                            ),
                        },
                    )
                )

        self.hardware_vm._shutdown_arduino_manager()
        log.info("controller.shutdown.complete")

    def _create_event_dispatcher(self, event_name: str):
        if event_name not in self._EVENT_METHOD_MAPPING:
            return lambda data: None

        method_ref, param_names, mode = self._EVENT_METHOD_MAPPING[event_name]

        def dispatcher(data: dict) -> None:
            if isinstance(method_ref, str):
                method = getattr(self, method_ref, None)
            else:
                method = method_ref

            if not method:
                return

            # Ensure data is a dict before processing
            if not isinstance(data, dict):
                self.log.warning(
                    "main_view_model.dispatcher.invalid_data_type",
                    event_name=event_name,
                    data_type=type(data).__name__,
                )
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
            else:
                raise NotImplementedError(
                    f"Unknown event dispatcher mode '{mode}' for event '{event_name}'"
                )

        return dispatcher

    def _register_event_handlers(self) -> None:
        if not self.ui_event_bus:
            return

        for event_name in self._EVENT_METHOD_MAPPING.keys():
            dispatcher = self._create_event_dispatcher(event_name)
            self.ui_event_bus.subscribe(event_name, dispatcher)

        # Subscribe to internal event for project manager replacement
        self.ui_event_bus.subscribe(
            Events.PROJECT_MANAGER_REPLACED,
            self._handle_project_manager_replaced,
        )

    def _handle_project_manager_replaced(self, data: dict):
        if not isinstance(data, dict):
            self.log.warning(
                "main_view_model._handle_project_manager_replaced.invalid_data_type",
                data_type=type(data).__name__,
            )
            return
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
            # Phase 3A/B/C/D: Removed superseded orchestrators
        ]

        for name, service in services_to_update + orchestrators_to_update:
            if service and hasattr(service, "_on_project_manager_replaced"):
                try:
                    service._on_project_manager_replaced(data)
                except Exception as e:
                    log.error(
                        "main_view_model.project_manager_replaced.service_update_failed",
                        service=name,
                        error=str(e),
                    )
            elif service and hasattr(service, "project_manager"):
                try:
                    service.project_manager = new_manager
                except Exception as e:
                    log.error(
                        "main_view_model.project_manager_replaced.direct_update_failed",
                        service=name,
                        error=str(e),
                    )

    def log_arduino_event(self, message: str):
        self.hardware_vm.log_arduino_event(message)

    def on_arduino_status_change(self, connected: bool, port: str | None):
        self.hardware_vm.on_arduino_status_change(connected, port)

    def on_arduino_command_sent(self, command: int, success: bool, source: str):
        self.hardware_vm.on_arduino_command_sent(command, success, source)

    # =========================================================================
    # Legacy / Misc Delegates
    # =========================================================================

    def get_calibration_scope_info(self) -> dict:
        return self.project_vm.get_calibration_scope_info()

    def get_all_weight_names(self) -> list[str]:
        return self.hardware_vm.get_all_weight_names()

    def get_global_model_defaults(self) -> dict:
        return self._global_model_defaults

    def resolve_project_model_settings(self, overrides: dict) -> tuple[str | None, bool]:
        return self.project_vm.resolve_project_model_settings(overrides)

    def save_project_model_overrides(
        self, active_weight: str | None, use_openvino: bool | None
    ) -> None:
        self.project_vm.save_project_model_overrides(active_weight, use_openvino)

    def has_project_override_settings(self) -> bool:
        return self.project_vm.has_project_override_settings()

    def restore_detector_defaults(self, scope: str = "global") -> bool:
        return self.hardware_vm.restore_detector_defaults(scope)

    def create_new_project(self, **kwargs):
        return self.project_vm.create_project_workflow(**kwargs)

    def get_openvino_cache_status(self, weight_name: str | None = None) -> dict:
        return self.hardware_vm.get_openvino_cache_status(weight_name)

    def set_main_arena_polygon(self, points: list) -> bool:
        return self.analysis_vm.set_main_arena_polygon(points)

    def add_roi_polygon(self, points: list, name: str, color: tuple) -> bool:
        return self.analysis_vm.add_roi_polygon(points, name, color)

    def get_arena_data(self, arena_id: str | None = None):
        if self.project_manager:
            return self.project_manager.get_zone_data()
        return None

    def _get_project_data_dict(self) -> dict:
        if self.project_manager:
            return self.project_manager.project_data
        return {}
